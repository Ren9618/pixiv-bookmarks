"""Shared paths and settings for the pixiv bookmark stack."""

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("DATA_DIR", "/data"))

IMAGES_DIR = DATA_DIR / "images"
STATE_DIR = DATA_DIR / "state"
SECRETS_DIR = DATA_DIR / "secrets"
ACCOUNTS_DIR = SECRETS_DIR / "accounts"
THUMBS_DIR = DATA_DIR / "thumbs"
LOGS_DIR = DATA_DIR / "logs"

DB_PATH = STATE_DIR / "gallery.db"
STATUS_PATH = STATE_DIR / "status.json"
SYNC_REQUEST_PATH = STATE_DIR / "sync.request"
OAUTH_PENDING_PATH = STATE_DIR / "oauth_pending.json"
FULL_SYNC_MARKER = STATE_DIR / "full_sync_done"
ARCHIVE_PATH = STATE_DIR / "archive.sqlite3"
INDEX_LOCK_PATH = STATE_DIR / "index.lock"
ACCOUNT_PATH = SECRETS_DIR / "account.json"
COOKIES_PATH = SECRETS_DIR / "cookies.txt"
SYNC_LOG_PATH = LOGS_DIR / "sync.log"

SYNC_INTERVAL_MINUTES = max(1, int(os.environ.get("SYNC_INTERVAL_MINUTES", "15")))
VIEWER_PASSWORD = os.environ.get("VIEWER_PASSWORD", "")
VIEWER_SECRET = os.environ.get("VIEWER_SECRET", "") or os.urandom(32).hex()
PIXIV_USER_ID = os.environ.get("PIXIV_USER_ID", "").strip()

APP_NAME = "Pixiv Bookmarks"


def ensure_dirs() -> None:
    """Create the data directory tree without ever touching existing media."""
    for path in (
        DATA_DIR,
        IMAGES_DIR,
        STATE_DIR,
        SECRETS_DIR,
        ACCOUNTS_DIR,
        THUMBS_DIR,
        LOGS_DIR,
        STATE_DIR / "home",
        STATE_DIR / "cache",
        STATE_DIR / "tmp",
    ):
        path.mkdir(parents=True, exist_ok=True)

    try:
        SECRETS_DIR.chmod(0o700)
    except OSError:
        pass
    try:
        ACCOUNTS_DIR.chmod(0o700)
    except OSError:
        pass
