"""Long-running pixiv bookmark synchronizer."""

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import db
from .accounts import load_accounts, public_account
from .config import (
    ARCHIVE_PATH,
    COOKIES_PATH,
    IMAGES_DIR,
    LOGS_DIR,
    SECRETS_DIR,
    STATE_DIR,
    STATUS_PATH,
    SYNC_INTERVAL_MINUTES,
    SYNC_LOG_PATH,
    SYNC_REQUEST_PATH,
    ensure_dirs,
)
from .indexer import index_all
from .pixiv_api import PixivAPIError, fetch_bookmark_ids

log = logging.getLogger("pixiv.sync")
STOP = False
_CURRENT_PROC = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime | None = None) -> str:
    return (moment or _utcnow()).isoformat(timespec="seconds")


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
        fp.write("\n")
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def read_status() -> dict:
    try:
        with STATUS_PATH.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_status(**updates) -> dict:
    data = read_status()
    data.update(updates)
    data["updated_at"] = _iso()
    _atomic_json(STATUS_PATH, data)
    return data


def _account_cookies(account_id: int) -> Path | None:
    per_account = SECRETS_DIR / f"cookies_{account_id}.txt"
    if per_account.is_file():
        return per_account
    if COOKIES_PATH.is_file():
        return COOKIES_PATH
    return None


def _build_config(auth: dict, skip_mode) -> dict:
    pixiv = {
        "refresh-token": auth["refresh_token"],
        "directory": ["{user[id]} {user[account]}"],
        "filename": "{id}_p{num:02}.{extension}",
        "tags": "original",
        "ugoira": True,
        "archive": str(ARCHIVE_PATH),
        "skip": skip_mode,
        "postprocessors": [
            {"name": "metadata", "mode": "json", "event": "file"},
            {
                "name": "ugoira",
                "extension": "mp4",
                "keep-files": True,
            },
        ],
    }
    cookies = _account_cookies(int(auth["id"]))
    if cookies is not None:
        pixiv["cookies"] = str(cookies)

    return {
        "extractor": {
            "base-directory": str(IMAGES_DIR),
            "path-restrict": "windows+",
            "path-strip": "auto",
            "sleep-request": "0.8-1.6",
            "retries": 5,
            "timeout": 45,
            "pixiv": pixiv,
        },
        "downloader": {
            "part": True,
            "part-directory": str(STATE_DIR / "parts"),
        },
    }


def _write_config(config: dict) -> Path:
    path = STATE_DIR / "gallery-dl.json"
    _atomic_json(path, config)
    os.chmod(path, 0o600)
    return path


def _is_auth_error(output: str) -> bool:
    lowered = output.lower()
    return (
        "invalid refresh token" in lowered
        or "invalid_grant" in lowered
        or "'refresh-token' required" in lowered
        or "authenticationerror" in lowered
    )


def _run_gallery_dl(config_path: Path, url: str) -> tuple[int, str]:
    global _CURRENT_PROC
    cmd = [
        "gallery-dl",
        "--config", str(config_path),
        "--no-colors",
        url,
    ]
    tail: deque[str] = deque(maxlen=60)
    log.info("gallery-dl start: %s", url)
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(STATE_DIR / "tmp"),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError as exc:
        log.error("failed to start gallery-dl: %s", exc)
        return 127, str(exc)

    _CURRENT_PROC = proc
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\r\n")
            if not line.strip():
                continue
            tail.append(line)
            log.info("%s", line)
            if STOP and proc.poll() is None:
                proc.terminate()
        code = proc.wait()
    finally:
        _CURRENT_PROC = None

    log.info("gallery-dl exit: %s", code)
    return code, "\n".join(tail)


def _prepare_full_resync() -> None:
    """Remove the archive so gallery-dl re-checks existing files.

    Media files themselves are never deleted.  The archive is shared by all
    accounts, and its keys include the bookmark owner, so it is safe to rebuild.
    """
    if ARCHIVE_PATH.exists():
        backup = ARCHIVE_PATH.with_name("archive.sqlite3.bak")
        try:
            os.replace(ARCHIVE_PATH, backup)
            log.info("full resync: moved old archive to %s", backup)
        except OSError as exc:
            log.warning("full resync: could not move archive: %s", exc)


def _sync_one(auth: dict, full: bool) -> dict:
    account_id = int(auth["id"])
    public = public_account(auth)
    initialized = db.account_initialized(account_id)
    skip_mode = True if (full or not initialized) else "abort:80"
    config_path = _write_config(_build_config(auth, skip_mode))

    urls = [
        (f"https://www.pixiv.net/users/{account_id}/bookmarks/artworks",
         "public"),
        (f"https://www.pixiv.net/users/{account_id}/bookmarks/artworks"
         "?rest=hide", "private"),
    ]

    codes: list[int] = []
    combined_output: list[str] = []
    completed = 0
    auth_error = False
    error_text = None
    bookmarks = None
    started = _utcnow()

    try:
        for url, label in urls:
            if STOP:
                break
            log.info("syncing %s bookmarks for %s", label, account_id)
            code, output = _run_gallery_dl(config_path, url)
            codes.append(code)
            if output:
                combined_output.append(output)
            if _is_auth_error(output):
                auth_error = True
                break
            if code != 0:
                log.warning(
                    "%s bookmark sync failed for %s with exit code %s",
                    label, account_id, code,
                )
                break
            completed += 1

        download_ok = (
            not STOP
            and not auth_error
            and completed == len(urls)
            and all(code == 0 for code in codes)
        )

        if download_ok:
            try:
                ids = fetch_bookmark_ids(auth["refresh_token"], account_id)
            except PixivAPIError as exc:
                error_text = f"ブックマーク一覧の取得に失敗しました: {exc}"
                if _is_auth_error(str(exc)):
                    auth_error = True
                log.error("%s (%s)", error_text, account_id)
            except Exception as exc:
                error_text = f"ブックマーク一覧の取得に失敗しました: {exc}"
                log.exception("bookmark list failed for %s", account_id)
            else:
                db.replace_bookmarks(account_id, ids)
                db.mark_account_synced(account_id)
                bookmarks = len(ids)
                log.info(
                    "bookmarks stored for %s: %d works", account_id, bookmarks
                )
        else:
            if STOP:
                error_text = "停止しました"
            elif auth_error:
                error_text = "pixivの認証が無効になりました。再認証してください。"
            else:
                error_text = (
                    "\n".join(combined_output)[-4000:]
                    or "gallery-dlでの同期に失敗しました"
                )

        ok = download_ok and error_text is None
        if not ok:
            db.mark_account_error(account_id, error_text or "同期に失敗しました")
            log.warning(
                "account %s sync failed: %s", account_id, error_text
            )
    finally:
        try:
            config_path.unlink()
        except OSError:
            pass

    finished = _utcnow()
    return {
        **public,
        "ok": ok,
        "auth_error": auth_error,
        "codes": codes,
        "completed": completed,
        "bookmarks": bookmarks,
        "error": error_text,
        "started_at": _iso(started),
        "finished_at": _iso(finished),
        "duration_sec": max(0, int((finished - started).total_seconds())),
    }


def _account_message(results: list[dict]) -> str:
    if len(results) == 1:
        result = results[0]
        return str(result.get("name") or result.get("account") or result["id"])
    names = [
        str(result.get("name") or result.get("account") or result["id"])
        for result in results
    ]
    return "、".join(names)


def run_once(full: bool = False, account_id: int | None = None) -> int:
    """Run one sync pass. Return seconds to wait before the next attempt."""
    ensure_dirs()
    accounts = load_accounts()
    if not accounts:
        db.upsert_accounts([])
        write_status(
            state="auth_required",
            message="pixivの認証が未設定です。OAuth認証を完了してください。",
            next_run=None,
            account=None,
            accounts=[],
        )
        log.warning("pixiv auth is not configured")
        return 60

    if account_id is not None:
        selected = [
            account for account in accounts if int(account["id"]) == int(account_id)
        ]
        if not selected:
            write_status(
                state="error",
                message=f"指定されたアカウント {account_id} が見つかりません。",
                next_run=None,
                accounts=db.list_accounts(),
            )
            log.warning("requested account %s is not configured", account_id)
            return SYNC_INTERVAL_MINUTES * 60
        accounts = selected

    if full:
        _prepare_full_resync()

    started = _utcnow()
    write_status(
        state="running",
        message=f"{len(accounts)}アカウントのブックマークを同期中です…",
        started_at=_iso(started),
        next_run=None,
        account=None,
        accounts=db.list_accounts(),
        last_error=None,
        full_sync=bool(full),
    )

    results: list[dict] = []
    for auth in accounts:
        if STOP:
            break
        log.info(
            "syncing account %s (@%s)", auth["id"], auth.get("account") or ""
        )
        results.append(_sync_one(auth, full=full))

    try:
        index_result = index_all()
    except Exception as exc:
        log.exception("indexing failed")
        index_result = {
            "works": 0, "images": 0, "new_works": 0, "elapsed_sec": 0
        }
        results.append({
            "id": 0,
            "name": "",
            "account": "",
            "ok": False,
            "auth_error": False,
            "codes": [],
            "completed": 0,
            "bookmarks": None,
            "error": f"インデックス作成に失敗しました: {exc}",
            "started_at": _iso(started),
            "finished_at": _iso(),
            "duration_sec": 0,
        })

    counts = db.counts()
    account_rows = db.list_accounts()
    finished = _utcnow()
    duration = max(0, int((finished - started).total_seconds()))

    success = (
        not STOP
        and len(results) == len(accounts)
        and all(result["ok"] for result in results)
    )
    auth_errors = [
        result for result in results if result.get("auth_error")
    ]
    errors = [
        f"[{result.get('name') or result.get('account') or result['id']}] "
        f"{result.get('error')}"
        for result in results
        if result.get("error")
    ]

    if success:
        state = "idle"
        message = (
            f"同期完了: 新規 {index_result['new_works']} 作品 / "
            f"全 {counts['works']} 作品"
            f"（{len(accounts)}アカウント）"
        )
        wait = SYNC_INTERVAL_MINUTES * 60
    elif auth_errors and len(auth_errors) == len(results):
        state = "auth_required"
        message = "pixivの認証が無効になりました。再認証してください。"
        wait = 300
    else:
        state = "error"
        message = "一部のアカウントで同期エラーが発生しました。ログを確認してください。"
        wait = SYNC_INTERVAL_MINUTES * 60

    error_text = "\n\n".join(errors)[-4000:] if errors else None
    write_status(
        state=state,
        message=message,
        finished_at=_iso(finished),
        next_run=_iso(finished + timedelta(seconds=wait)),
        last_exit_code=(
            results[0]["codes"][0]
            if results and results[0].get("codes") else None
        ),
        last_exit_codes=[
            code for result in results for code in result.get("codes", [])
        ],
        last_duration_sec=duration,
        last_new_works=index_result["new_works"],
        last_index_sec=index_result.get("elapsed_sec"),
        total_works=counts["works"],
        total_images=counts["images"],
        total_favorites=counts["favorites"],
        last_error=error_text,
        account=None,
        accounts=account_rows,
        account_results=results,
        full_sync=bool(full),
    )

    log.info(
        "sync finished: state=%s accounts=%s works=%s images=%s new=%s",
        state, len(accounts), counts["works"], counts["images"],
        index_result["new_works"],
    )
    return wait


def _take_request() -> dict:
    try:
        value = SYNC_REQUEST_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return {}
    try:
        SYNC_REQUEST_PATH.unlink()
    except OSError:
        pass
    if not value:
        return {"mode": "normal"}
    try:
        data = json.loads(value)
    except ValueError:
        return {"mode": value}
    if isinstance(data, str):
        return {"mode": data}
    if isinstance(data, dict):
        return data
    return {"mode": "normal"}


def _setup_logging() -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    file_handler = RotatingFileHandler(
        SYNC_LOG_PATH, maxBytes=20 * 1024 * 1024, backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def _handle_stop(_signum, _frame) -> None:
    global STOP
    STOP = True
    log.info("stop requested")
    if _CURRENT_PROC is not None and _CURRENT_PROC.poll() is None:
        try:
            _CURRENT_PROC.terminate()
        except OSError:
            pass


def _index_loop() -> None:
    """Index downloaded files periodically during long initial syncs."""
    while not STOP:
        time.sleep(120)
        if STOP:
            break
        try:
            if read_status().get("state") == "running":
                index_all()
        except Exception:
            log.exception("background indexing failed")


def _requested_account_id(request: dict) -> int | None:
    value = request.get("account_id") or request.get("account")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        log.warning("invalid account id in sync request: %r", value)
        return None


def main() -> None:
    ensure_dirs()
    os.environ.setdefault("HOME", str(STATE_DIR / "home"))
    os.environ.setdefault("XDG_CACHE_HOME", str(STATE_DIR / "cache"))
    os.environ.setdefault("TMPDIR", str(STATE_DIR / "tmp"))
    (STATE_DIR / "parts").mkdir(parents=True, exist_ok=True)

    _setup_logging()
    db.init_db()
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    threading.Thread(
        target=_index_loop, name="pixiv-indexer", daemon=True
    ).start()

    accounts = load_accounts()
    log.info(
        "pixiv sync starting (interval=%s min, accounts=%s)",
        SYNC_INTERVAL_MINUTES, len(accounts),
    )
    write_status(
        state="idle" if accounts else "auth_required",
        message="起動しました" if accounts else "pixivの認証待ちです",
        next_run=_iso(_utcnow()) if accounts else None,
        account=None,
        accounts=db.list_accounts(),
    )

    next_run = time.monotonic()
    while not STOP:
        request = _take_request()
        now = time.monotonic()
        if not request and now < next_run:
            time.sleep(min(5.0, max(0.2, next_run - now)))
            continue

        mode = str(request.get("mode") or "normal")
        wait = run_once(
            full=(mode == "full"),
            account_id=_requested_account_id(request),
        )
        next_run = time.monotonic() + wait

    write_status(state="stopped", message="停止しました", next_run=None)
    log.info("pixiv sync stopped")


if __name__ == "__main__":
    main()
