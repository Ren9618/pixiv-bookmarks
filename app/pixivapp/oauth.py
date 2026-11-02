"""pixiv OAuth (PKCE) support for the viewer's add-account form.

The flow is intentionally human operated:

1. ``create_login_url`` generates a PKCE challenge and stores the verifier in
   ``state/oauth_pending.json``.
2. The person logs in with their own browser and copies the callback URL (or
   only the ``code`` value) from the browser's developer tools.
3. ``exchange_code`` swaps the code for a refresh token, saves it under
   ``secrets/accounts/<user_id>.json`` (mode 0600) and queues a sync.

No token is ever written to the application log.
"""

import base64
import hashlib
import json
import logging
import os
import re
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .accounts import load_accounts
from .config import (
    ACCOUNTS_DIR,
    OAUTH_PENDING_PATH,
    SECRETS_DIR,
    SYNC_REQUEST_PATH,
)

log = logging.getLogger("pixiv.oauth")

CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"
REDIRECT_URI = "https://app-api.pixiv.net/web/v1/users/auth/pixiv/callback"
LOGIN_URL = "https://app-api.pixiv.net/web/v1/login"
TOKEN_URL = "https://oauth.secure.pixiv.net/auth/token"
USER_AGENT = "PixivAndroidApp/5.0.234 (Android 11; Pixel 5)"

# How long the issued login URL is worth re-showing in the viewer.  The PKCE
# challenge itself does not expire on pixiv's side; this only keeps stale
# links from lingering in the UI.
PENDING_TTL_SECONDS = 60 * 30
MAX_CODE_LENGTH = 4096

_lock = threading.Lock()


class OAuthError(Exception):
    """An error whose message can be shown to the person using the viewer."""

    def __init__(self, message: str, code: str = "oauth_error"):
        super().__init__(message)
        self.code = code


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _read_pending() -> dict | None:
    try:
        with OAUTH_PENDING_PATH.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("verifier"):
        return None
    return data


def _write_pending(data: dict) -> None:
    OAUTH_PENDING_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OAUTH_PENDING_PATH.with_name(
        f"{OAUTH_PENDING_PATH.name}.{os.getpid()}.tmp"
    )
    with tmp.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, OAUTH_PENDING_PATH)


def _delete_pending() -> None:
    try:
        OAUTH_PENDING_PATH.unlink()
    except OSError:
        pass


def _login_url(challenge: str) -> str:
    params = urllib.parse.urlencode({
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "client": "pixiv-android",
    })
    return f"{LOGIN_URL}?{params}"


def _pending_age(pending: dict) -> float | None:
    raw = str(pending.get("created_at") or "")
    try:
        created = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(0.0, (_utcnow() - created).total_seconds())


def create_login_url() -> dict:
    """Create a fresh PKCE challenge and return its login URL."""
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    created = _utcnow()

    with _lock:
        _write_pending({
            "verifier": verifier,
            "challenge": challenge,
            "created_at": created.isoformat(timespec="seconds"),
        })
    log.info("issued a new pixiv OAuth login URL")

    return {
        "login_url": _login_url(challenge),
        "created_at": created.isoformat(timespec="seconds"),
        "expires_in": PENDING_TTL_SECONDS,
    }


def pending_info() -> dict:
    """Return the still-usable login URL, if one was issued recently."""
    pending = _read_pending()
    if pending is None:
        return {"pending": False}

    age = _pending_age(pending)
    if age is not None and age >= PENDING_TTL_SECONDS:
        with _lock:
            _delete_pending()
        return {"pending": False, "expired": True}

    created_at = pending.get("created_at")
    return {
        "pending": True,
        "login_url": _login_url(str(pending["challenge"])),
        "created_at": created_at,
        "expires_in": (
            PENDING_TTL_SECONDS if age is None else max(
                0, int(PENDING_TTL_SECONDS - age)
            )
        ),
    }


def _extract_code(raw: str) -> str:
    """Accept a callback URL, a ``code=...`` fragment, or a bare code."""
    value = (raw or "").strip().replace("&amp;", "&")
    if not value:
        return ""
    if len(value) > MAX_CODE_LENGTH:
        value = value[:MAX_CODE_LENGTH]

    match = re.search(r"[?&]code=([^&\s#]+)", value)
    if match:
        return urllib.parse.unquote(match.group(1)).strip()
    if value.startswith("code="):
        return urllib.parse.unquote(value.split("=", 1)[1].split("&")[0]).strip()
    return value.split()[0].strip()


def _pixiv_error(body: str) -> str:
    """Pull a short, human readable message out of a pixiv error body."""
    try:
        data = json.loads(body)
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    errors = data.get("errors")
    if isinstance(errors, dict):
        system = errors.get("system")
        if isinstance(system, dict) and system.get("message"):
            return str(system["message"])[:300]
    for key in ("message", "error"):
        if data.get(key):
            return str(data[key])[:300]
    return ""


def _save_account(payload: dict) -> bool:
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    for path in (SECRETS_DIR, ACCOUNTS_DIR):
        try:
            path.chmod(0o700)
        except OSError:
            pass

    target = ACCOUNTS_DIR / f"{payload['user_id']}.json"
    replaced = target.is_file()
    tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, target)
    return replaced


def queue_sync(account_id: int | None = None, mode: str = "normal") -> None:
    """Ask the sync service to run, optionally for one account only."""
    payload: dict = {"mode": mode}
    if account_id is not None:
        payload["account_id"] = int(account_id)
    SYNC_REQUEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYNC_REQUEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    try:
        os.chmod(SYNC_REQUEST_PATH, 0o644)
    except OSError:
        pass


def exchange_code(raw_code: str) -> dict:
    """Exchange a pasted authorization code and store the new account."""
    code = _extract_code(raw_code)
    if not code:
        raise OAuthError(
            "コールバックURLまたは code を貼り付けてください。",
            code="missing_code",
        )

    pending = _read_pending()
    if pending is None:
        raise OAuthError(
            "ログインURLの準備データがありません。"
            "「ログインURLを発行」からやり直してください。",
            code="pending_missing",
        )
    verifier = str(pending.get("verifier") or "")
    if not verifier:
        raise OAuthError(
            "ログインURLの準備データが壊れています。"
            "「ログインURLを発行」からやり直してください。",
            code="pending_corrupt",
        )

    form = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "code_verifier": verifier,
        "grant_type": "authorization_code",
        "include_policy": "true",
        "redirect_uri": REDIRECT_URI,
    }).encode()
    request = urllib.request.Request(
        TOKEN_URL,
        data=form,
        method="POST",
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        detail = _pixiv_error(body)
        message = (
            f"pixivがcodeを受け付けませんでした（HTTP {exc.code}）。"
            "codeは発行から数十秒で失効します。"
            "「ログインURLを発行」からやり直し、ログイン後すぐに貼り付けてください。"
        )
        if detail:
            message += f"\npixivからの応答: {detail}"
        raise OAuthError(message, code="code_rejected")
    except (urllib.error.URLError, OSError) as exc:
        raise OAuthError(
            f"pixivへの通信に失敗しました: {exc}",
            code="network_error",
        )

    try:
        data = json.loads(body)
    except ValueError:
        raise OAuthError(
            "pixivからJSON以外の応答が返りました。時間をおいてやり直してください。",
            code="invalid_response",
        )
    if isinstance(data, dict) and isinstance(data.get("response"), dict):
        data = data["response"]
    if not isinstance(data, dict) or not data.get("refresh_token"):
        detail = _pixiv_error(body)
        raise OAuthError(
            "refresh_token を取得できませんでした。"
            + (f"\npixivからの応答: {detail}" if detail else ""),
            code="refresh_token_missing",
        )

    user = data.get("user") or {}
    try:
        user_id = int(user.get("id") or 0)
    except (TypeError, ValueError):
        user_id = 0
    if not user_id:
        raise OAuthError(
            "pixivのユーザーIDを取得できませんでした。",
            code="user_id_missing",
        )

    payload = {
        "user_id": user_id,
        "name": str(user.get("name") or ""),
        "account": str(user.get("account") or ""),
        "refresh_token": str(data["refresh_token"]),
        "obtained_at": _utcnow().isoformat(timespec="seconds"),
    }

    with _lock:
        replaced = _save_account(payload)
        _delete_pending()

    queue_sync(user_id)
    log.info("saved pixiv account %s (%s)", user_id, payload["account"] or "-")

    known = load_accounts()
    return {
        "ok": True,
        "account": {
            "id": user_id,
            "name": payload["name"],
            "account": payload["account"],
        },
        "replaced": replaced,
        "queued": True,
        "accounts": len(known),
    }
