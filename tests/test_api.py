import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from pixivapp import db, main
from pixivapp.config import ACCOUNTS_DIR


def test_healthz():
    with TestClient(main.app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "auth": False}


def test_auth_middleware_blocks_api_and_accepts_login(monkeypatch):
    monkeypatch.setattr(main, "VIEWER_PASSWORD", "correct-password")

    with TestClient(main.app) as client:
        response = client.get("/api/items", follow_redirects=False)
        assert response.status_code == 401
        assert response.json() == {"detail": "unauthorized"}

        response = client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("/login?next=")

        response = client.post(
            "/login",
            data={"password": "wrong", "next": "/"},
            follow_redirects=False,
        )
        assert response.status_code == 401

        response = client.post(
            "/login",
            data={"password": "correct-password", "next": "/"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/"

        response = client.get("/api/items")
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total"] == 0


def test_safe_next_rejects_open_redirects():
    assert main._safe_next("/tags?name=x") == "/tags?name=x"
    assert main._safe_next("") == "/"
    assert main._safe_next("https://evil.example/") == "/"
    assert main._safe_next("//evil.example/") == "/"
    assert main._safe_next("/\\evil.example/") == "/"
    assert main._safe_next("/ok\nSet-Cookie: x=1") == "/"
    assert main._safe_next("/" + ("a" * 3000)) == "/"


def test_parse_account_id():
    assert main._parse_account_id(None) is None
    assert main._parse_account_id("") is None
    assert main._parse_account_id("all") is None
    assert main._parse_account_id("42") == 42

    for value in ("nope", "0", "-1"):
        with pytest.raises(HTTPException) as excinfo:
            main._parse_account_id(value)
        assert excinfo.value.status_code == 400


def test_api_items_rejects_invalid_account():
    with TestClient(main.app) as client:
        response = client.get("/api/items?account=nope")

    assert response.status_code == 400


def test_api_accounts_returns_enabled_accounts():
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    (ACCOUNTS_DIR / "123.json").write_text(
        json.dumps({
            "user_id": 123,
            "name": "User",
            "account": "user_123",
            "refresh_token": "token",
            "obtained_at": "2026-01-01T00:00:00+00:00",
        }),
        encoding="utf-8",
    )

    with TestClient(main.app) as client:
        db.upsert_accounts([{
            "id": 123,
            "name": "User",
            "account": "user_123",
            "obtained_at": "2026-01-01T00:00:00+00:00",
        }])
        response = client.get("/api/accounts")

    assert response.status_code == 200
    accounts = response.json()["accounts"]
    assert len(accounts) == 1
    assert accounts[0]["id"] == 123
    assert accounts[0]["name"] == "User"
    assert "refresh_token" not in json.dumps(accounts)


def test_oauth_start_and_pending_endpoints():
    with TestClient(main.app) as client:
        response = client.post("/api/accounts/oauth/start")
        assert response.status_code == 200
        started = response.json()
        assert started["login_url"].startswith(main.oauth.LOGIN_URL)

        response = client.get("/api/accounts/oauth/pending")
        assert response.status_code == 200
        pending = response.json()
        assert pending["pending"] is True
        assert pending["login_url"] == started["login_url"]


def test_oauth_exchange_endpoint(monkeypatch):
    seen = {}

    def fake_exchange(code):
        seen["code"] = code
        return {
            "ok": True,
            "account": {"id": 123, "name": "User", "account": "user_123"},
            "replaced": False,
            "queued": True,
            "accounts": 1,
        }

    monkeypatch.setattr(main.oauth, "exchange_code", fake_exchange)

    with TestClient(main.app) as client:
        response = client.post(
            "/api/accounts/oauth/exchange", json={"code": "callback-code"}
        )

    assert response.status_code == 200
    assert response.json()["account"]["id"] == 123
    assert seen == {"code": "callback-code"}


def test_oauth_exchange_endpoint_validates_input(monkeypatch):
    with TestClient(main.app) as client:
        for body in ({}, {"code": ""}, {"code": "   "}, {"code": 123}):
            response = client.post(
                "/api/accounts/oauth/exchange", json=body
            )
            assert response.status_code == 400
            assert response.headers["X-Error-Code"] == "missing_code"
            assert "貼り付けて" in response.json()["detail"]

        def fail(_code):
            raise main.oauth.OAuthError("codeが失効しました")

        monkeypatch.setattr(main.oauth, "exchange_code", fail)
        response = client.post(
            "/api/accounts/oauth/exchange", json={"code": "expired"}
        )

    assert response.status_code == 400
    assert response.headers["X-Error-Code"] == "oauth_error"
    assert response.json()["detail"] == "codeが失効しました"
