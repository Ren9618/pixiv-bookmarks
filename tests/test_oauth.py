import base64
import hashlib
import io
import json
import stat
import urllib.error
import urllib.parse

import pytest

from pixivapp import oauth
from pixivapp.config import ACCOUNTS_DIR, OAUTH_PENDING_PATH, SYNC_REQUEST_PATH


class FakeResponse:
    def __init__(self, body: str):
        self.body = body

    def read(self) -> bytes:
        return self.body.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False


def _fake_token_response(**overrides) -> FakeResponse:
    payload = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "user": {"id": 12345, "name": "Test User", "account": "test_user"},
    }
    payload.update(overrides)
    return FakeResponse(json.dumps(payload))


def _pending() -> dict:
    return json.loads(OAUTH_PENDING_PATH.read_text(encoding="utf-8"))


def test_extract_code_accepts_callback_url():
    code = oauth._extract_code(
        "https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback"
        "?code=abc123&state=xyz"
    )
    assert code == "abc123"


def test_extract_code_handles_html_escaped_ampersands_and_encoding():
    code = oauth._extract_code(
        "https://example.test/callback?state=1&amp;code=a%2Fb%2Bc&amp;x=2"
    )
    assert code == "a/b+c"


def test_extract_code_accepts_code_prefix_and_bare_code():
    assert oauth._extract_code("code=xyz&state=1") == "xyz"
    assert oauth._extract_code("  bare-code  ") == "bare-code"
    assert oauth._extract_code("") == ""


def test_extract_code_limits_input_length():
    raw = "a" * (oauth.MAX_CODE_LENGTH * 2)
    assert len(oauth._extract_code(raw)) == oauth.MAX_CODE_LENGTH


def test_create_login_url_stores_private_pkce_verifier():
    info = oauth.create_login_url()

    assert info["login_url"].startswith(oauth.LOGIN_URL)
    assert info["expires_in"] == oauth.PENDING_TTL_SECONDS
    query = urllib.parse.parse_qs(
        urllib.parse.urlsplit(info["login_url"]).query
    )
    assert query["code_challenge_method"] == ["S256"]

    pending = _pending()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(pending["verifier"].encode()).digest()
    ).rstrip(b"=").decode()
    assert query["code_challenge"] == [expected]
    assert pending["challenge"] == expected
    assert stat.S_IMODE(OAUTH_PENDING_PATH.stat().st_mode) == 0o600


def test_pending_info_returns_issued_url():
    assert oauth.pending_info() == {"pending": False}

    info = oauth.create_login_url()
    pending = oauth.pending_info()

    assert pending["pending"] is True
    assert pending["login_url"] == info["login_url"]


def test_pending_info_expires_and_removes_file(monkeypatch):
    oauth.create_login_url()
    monkeypatch.setattr(oauth, "PENDING_TTL_SECONDS", 0)

    info = oauth.pending_info()

    assert info["pending"] is False
    assert info["expired"] is True
    assert not OAUTH_PENDING_PATH.exists()


def test_save_account_is_private_and_reports_replacement():
    payload = {
        "user_id": 12345,
        "name": "Test User",
        "account": "test_user",
        "refresh_token": "secret-token",
        "obtained_at": "2026-01-01T00:00:00+00:00",
    }

    assert oauth._save_account(payload) is False

    target = ACCOUNTS_DIR / "12345.json"
    assert json.loads(target.read_text(encoding="utf-8")) == payload
    assert stat.S_IMODE(target.stat().st_mode) == 0o600

    payload["refresh_token"] = "new-token"
    assert oauth._save_account(payload) is True
    assert json.loads(target.read_text(encoding="utf-8"))["refresh_token"] == (
        "new-token"
    )
    assert not list(ACCOUNTS_DIR.glob("*.tmp"))


def test_exchange_code_saves_account_and_queues_sync(monkeypatch):
    oauth.create_login_url()
    verifier = _pending()["verifier"]
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = request.data.decode("utf-8")
        captured["timeout"] = timeout
        return _fake_token_response()

    monkeypatch.setattr(oauth.urllib.request, "urlopen", fake_urlopen)

    result = oauth.exchange_code("https://example.test/callback?code=good-code")

    assert result["ok"] is True
    assert result["account"] == {
        "id": 12345,
        "name": "Test User",
        "account": "test_user",
    }
    assert result["replaced"] is False
    assert result["queued"] is True
    assert result["accounts"] == 1

    form = urllib.parse.parse_qs(captured["body"])
    assert form["code"] == ["good-code"]
    assert form["code_verifier"] == [verifier]
    assert captured["url"] == oauth.TOKEN_URL

    saved = json.loads(
        (ACCOUNTS_DIR / "12345.json").read_text(encoding="utf-8")
    )
    assert saved["refresh_token"] == "refresh-token"
    assert stat.S_IMODE((ACCOUNTS_DIR / "12345.json").stat().st_mode) == 0o600
    assert not OAUTH_PENDING_PATH.exists()

    request = json.loads(SYNC_REQUEST_PATH.read_text(encoding="utf-8"))
    assert request == {"mode": "normal", "account_id": 12345}


def test_exchange_code_rejects_http_error_without_saving(monkeypatch):
    oauth.create_login_url()
    error_body = json.dumps({
        "errors": {"system": {"message": "invalid_grant"}}
    }).encode("utf-8")

    def fake_urlopen(_request, timeout):
        raise urllib.error.HTTPError(
            oauth.TOKEN_URL,
            400,
            "Bad Request",
            {},
            io.BytesIO(error_body),
        )

    monkeypatch.setattr(oauth.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(oauth.OAuthError) as excinfo:
        oauth.exchange_code("used-code")

    message = str(excinfo.value)
    assert "HTTP 400" in message
    assert "invalid_grant" in message
    assert not list(ACCOUNTS_DIR.glob("*.json"))
    assert OAUTH_PENDING_PATH.exists()
    assert not SYNC_REQUEST_PATH.exists()


def test_exchange_code_requires_pending_challenge():
    with pytest.raises(oauth.OAuthError, match="ログインURL"):
        oauth.exchange_code("some-code")


def test_exchange_code_requires_non_empty_code():
    with pytest.raises(oauth.OAuthError, match="貼り付けて"):
        oauth.exchange_code("   ")


def test_exchange_code_rejects_response_without_refresh_token(monkeypatch):
    oauth.create_login_url()

    def fake_urlopen(_request, timeout):
        return FakeResponse(json.dumps({
            "user": {"id": 12345},
            "error": "invalid request",
        }))

    monkeypatch.setattr(oauth.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(oauth.OAuthError, match="refresh_token"):
        oauth.exchange_code("some-code")

    assert OAUTH_PENDING_PATH.exists()
