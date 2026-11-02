"""Discover pixiv account credentials stored in the data directory.

The stack supports multiple pixiv accounts.  Credentials live in
``secrets/accounts/<user_id>.json``.  The original single-account files
(``secrets/account.json`` / ``secrets/refresh_token``) are still accepted and
are copied into the new location on first use.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from .config import ACCOUNT_PATH, ACCOUNTS_DIR, SECRETS_DIR

log = logging.getLogger("pixiv.accounts")


def _iso_from_timestamp(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(
        timespec="seconds"
    )


def _read_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_private_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _normalize(data: dict, source: Path) -> dict | None:
    try:
        user_id = int(data.get("user_id") or 0)
    except (TypeError, ValueError):
        user_id = 0
    token = str(data.get("refresh_token") or "").strip()
    if not token and source == ACCOUNT_PATH:
        try:
            token = (SECRETS_DIR / "refresh_token").read_text(
                encoding="utf-8"
            ).strip()
        except OSError:
            token = ""
    if not user_id or not token:
        return None

    obtained_at = str(data.get("obtained_at") or "").strip()
    if not obtained_at:
        try:
            obtained_at = _iso_from_timestamp(source.stat().st_mtime)
        except OSError:
            obtained_at = ""

    return {
        "id": user_id,
        "name": str(data.get("name") or "").strip(),
        "account": str(data.get("account") or "").strip(),
        "refresh_token": token,
        "obtained_at": obtained_at,
        "source": str(source),
    }


def migrate_legacy_account() -> None:
    """Copy the old single-account credentials into the accounts directory."""
    if not ACCOUNT_PATH.is_file():
        return
    data = _read_json(ACCOUNT_PATH)
    account = _normalize(data, ACCOUNT_PATH)
    if account is None:
        return

    target = ACCOUNTS_DIR / f"{account['id']}.json"
    if target.exists():
        return

    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        ACCOUNTS_DIR.chmod(0o700)
    except OSError:
        pass
    payload = {
        "user_id": account["id"],
        "name": account["name"],
        "account": account["account"],
        "refresh_token": account["refresh_token"],
        "obtained_at": account["obtained_at"],
    }
    try:
        _write_private_json(target, payload)
    except OSError as exc:
        log.warning("could not migrate legacy pixiv account: %s", exc)
        return
    log.info("migrated legacy pixiv account %s to %s", account["id"], target)


def load_accounts() -> list[dict]:
    """Return all usable pixiv accounts, newest authentication last."""
    migrate_legacy_account()
    accounts: dict[int, dict] = {}

    legacy = _normalize(_read_json(ACCOUNT_PATH), ACCOUNT_PATH)
    if legacy is not None:
        accounts[legacy["id"]] = legacy

    try:
        paths = sorted(ACCOUNTS_DIR.glob("*.json"))
    except OSError:
        paths = []
    for path in paths:
        account = _normalize(_read_json(path), path)
        if account is not None:
            accounts[account["id"]] = account

    return sorted(
        accounts.values(),
        key=lambda item: (item.get("obtained_at") or "", item["id"]),
    )


def remove_account(user_id: int) -> list[Path]:
    """Delete one account's credentials, including the legacy layout."""
    removed: list[Path] = []

    target = ACCOUNTS_DIR / f"{user_id}.json"
    try:
        if target.is_file():
            target.unlink()
            removed.append(target)
    except OSError as exc:
        log.warning("could not remove %s: %s", target, exc)

    if ACCOUNT_PATH.is_file():
        legacy = _read_json(ACCOUNT_PATH)
        try:
            legacy_id = int(legacy.get("user_id") or 0)
        except (TypeError, ValueError):
            legacy_id = 0
        if legacy_id == user_id:
            try:
                ACCOUNT_PATH.unlink()
                removed.append(ACCOUNT_PATH)
            except OSError as exc:
                log.warning("could not remove %s: %s", ACCOUNT_PATH, exc)
            token_path = SECRETS_DIR / "refresh_token"
            try:
                if token_path.is_file():
                    token_path.unlink()
                    removed.append(token_path)
            except OSError as exc:
                log.warning("could not remove %s: %s", token_path, exc)

    return removed


def public_account(account: dict) -> dict:
    return {
        "id": account.get("id"),
        "name": account.get("name") or "",
        "account": account.get("account") or "",
    }
