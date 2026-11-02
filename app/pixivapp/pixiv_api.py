"""Minimal Pixiv App API client used to record bookmark ownership.

gallery-dl handles the actual downloads.  This module only asks the App API
which bookmark IDs belong to an account so the viewer can show per-account
bookmark sets even when several accounts bookmark the same artwork.
"""

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

CLIENT_ID = "MOBrBDS8blbauoSck0ZfDbtuzpyT"
CLIENT_SECRET = "lsACyCD94FhDUtGTXi3QzcFE2uU1hqtDaKeqrdwj"
HASH_SECRET = (
    "28c1fdd170a5204386cb1313c7077b34"
    "f83e4aaf4aa829ce78c231e05b0bae2c"
)
USER_AGENT = "PixivIOSApp/7.19.1 (iOS 16.7.2; iPhone12,8)"
API_BASE = "https://app-api.pixiv.net"
TOKEN_URL = "https://oauth.secure.pixiv.net/auth/token"
TIMEOUT = 45


class PixivAPIError(RuntimeError):
    """Raised when the Pixiv API cannot be used."""


def _read_json(response):
    body = response.read().decode("utf-8", "replace")
    try:
        data = json.loads(body)
    except ValueError as exc:
        raise PixivAPIError(f"pixiv API returned non-JSON: {body[:200]}") from exc
    if not isinstance(data, dict):
        raise PixivAPIError("pixiv API returned an unexpected response")
    return data


def _request(request, attempts: int = 3):
    last_error = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return _read_json(response)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            last_error = f"HTTP {exc.code}: {body[:500]}"
            if exc.code == 429 and attempt + 1 < attempts:
                time.sleep(10 * (attempt + 1))
                continue
            raise PixivAPIError(last_error) from exc
        except (urllib.error.URLError, OSError) as exc:
            last_error = str(exc)
            if attempt + 1 < attempts:
                time.sleep(2 * (attempt + 1))
                continue
            raise PixivAPIError(last_error) from exc
    raise PixivAPIError(last_error or "pixiv API request failed")


def get_access_token(refresh_token: str) -> str:
    token = (refresh_token or "").strip()
    if not token:
        raise PixivAPIError("refresh token is empty")

    client_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    client_hash = hashlib.md5(
        (client_time + HASH_SECRET).encode()
    ).hexdigest()
    form = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": token,
        "get_secure_url": "1",
    }).encode()
    request = urllib.request.Request(
        TOKEN_URL,
        data=form,
        method="POST",
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": API_BASE + "/",
            "X-Client-Time": client_time,
            "X-Client-Hash": client_hash,
        },
    )
    data = _request(request)
    response = data.get("response")
    if not isinstance(response, dict) or not response.get("access_token"):
        raise PixivAPIError("pixiv did not return an access token")
    return str(response["access_token"])


def _bookmark_ids_for_restrict(access_token: str, user_id: int,
                               restrict: str) -> list[int]:
    query = urllib.parse.urlencode({
        "user_id": user_id,
        "restrict": restrict,
    })
    url = f"{API_BASE}/v1/user/bookmarks/illust?{query}"
    ids: list[int] = []

    while url:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Authorization": "Bearer " + access_token,
                "Referer": API_BASE + "/",
            },
        )
        data = _request(request)
        error = data.get("error")
        if isinstance(error, dict):
            message = error.get("user_message") or error.get("message") or error
            raise PixivAPIError(f"pixiv API error: {message}")
        for illust in data.get("illusts") or []:
            try:
                ids.append(int(illust["id"]))
            except (KeyError, TypeError, ValueError):
                continue

        next_url = data.get("next_url")
        if not next_url:
            break
        url = str(next_url)
        if url.startswith("/"):
            url = API_BASE + url
        time.sleep(0.4)

    return ids


def fetch_bookmark_ids(refresh_token: str, user_id: int) -> list[int]:
    """Return public and private bookmark IDs, newest bookmarks first."""
    access_token = get_access_token(refresh_token)
    ordered: list[int] = []
    seen: set[int] = set()
    for restrict in ("public", "private"):
        for work_id in _bookmark_ids_for_restrict(
                access_token, int(user_id), restrict):
            if work_id not in seen:
                seen.add(work_id)
                ordered.append(work_id)
    return ordered
