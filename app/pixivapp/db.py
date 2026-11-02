"""SQLite storage for the bookmark index and local favorites."""

import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS works (
    id              INTEGER PRIMARY KEY,
    title           TEXT    NOT NULL DEFAULT '',
    artist_id       INTEGER,
    artist_name     TEXT    NOT NULL DEFAULT '',
    artist_account  TEXT    NOT NULL DEFAULT '',
    create_date     TEXT,
    create_ts       INTEGER NOT NULL DEFAULT 0,
    x_restrict      INTEGER NOT NULL DEFAULT 0,
    sanity_level    INTEGER NOT NULL DEFAULT 0,
    total_bookmarks INTEGER NOT NULL DEFAULT 0,
    page_count      INTEGER NOT NULL DEFAULT 0,
    tags_json       TEXT    NOT NULL DEFAULT '[]',
    description     TEXT    NOT NULL DEFAULT '',
    added_ts        INTEGER NOT NULL DEFAULT 0,
    updated_ts      INTEGER NOT NULL DEFAULT 0,
    missing         INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_works_create  ON works(create_ts DESC);
CREATE INDEX IF NOT EXISTS idx_works_added   ON works(added_ts DESC);
CREATE INDEX IF NOT EXISTS idx_works_artist  ON works(artist_id);
CREATE INDEX IF NOT EXISTS idx_works_missing ON works(missing);

CREATE TABLE IF NOT EXISTS pages (
    work_id    INTEGER NOT NULL,
    num        INTEGER NOT NULL,
    rel_path   TEXT    NOT NULL,
    extension  TEXT    NOT NULL DEFAULT '',
    is_video   INTEGER NOT NULL DEFAULT 0,
    width      INTEGER NOT NULL DEFAULT 0,
    height     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (work_id, num),
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pages_work ON pages(work_id);

CREATE TABLE IF NOT EXISTS tags (
    work_id INTEGER NOT NULL,
    tag     TEXT    NOT NULL,
    PRIMARY KEY (work_id, tag)
);

CREATE INDEX IF NOT EXISTS idx_tags_tag ON tags(tag);

CREATE TABLE IF NOT EXISTS favorites (
    work_id    INTEGER PRIMARY KEY,
    created_ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id           INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL DEFAULT '',
    account      TEXT    NOT NULL DEFAULT '',
    enabled      INTEGER NOT NULL DEFAULT 1,
    initialized  INTEGER NOT NULL DEFAULT 0,
    added_ts     INTEGER NOT NULL DEFAULT 0,
    last_sync_ts INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT
);

CREATE TABLE IF NOT EXISTS bookmarks (
    account_id    INTEGER NOT NULL,
    work_id       INTEGER NOT NULL,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    first_seen_ts INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (account_id, work_id)
);

CREATE INDEX IF NOT EXISTS idx_bookmarks_work
    ON bookmarks(work_id);
CREATE INDEX IF NOT EXISTS idx_bookmarks_account
    ON bookmarks(account_id, sort_order);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db(path: Path | str = DB_PATH) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def session(path: Path | str = DB_PATH) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def counts(path: Path | str = DB_PATH) -> dict:
    """Return visible work/image counts, tolerating a not-yet-created DB."""
    try:
        with connect(path) as conn:
            works = conn.execute(
                "SELECT COUNT(*) FROM works WHERE missing = 0"
            ).fetchone()[0]
            images = conn.execute(
                "SELECT COUNT(*) FROM pages p JOIN works w ON w.id = p.work_id "
                "WHERE w.missing = 0"
            ).fetchone()[0]
            favorites = conn.execute(
                "SELECT COUNT(*) FROM favorites f JOIN works w ON w.id = f.work_id "
                "WHERE w.missing = 0"
            ).fetchone()[0]
    except sqlite3.Error:
        return {"works": 0, "images": 0, "favorites": 0}
    return {"works": works, "images": images, "favorites": favorites}


def _account_added_ts(account: dict, default: int) -> int:
    raw = str(account.get("obtained_at") or "").strip()
    if not raw:
        return default
    try:
        value = int(
            datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        )
    except (ValueError, OSError, OverflowError):
        return default
    return value if value > 0 else default


def upsert_accounts(accounts: list[dict], path: Path | str = DB_PATH) -> None:
    """Store the accounts found in secrets/accounts and disable removed ones."""
    now = int(time.time())
    ids = [int(account["id"]) for account in accounts]
    with session(path) as conn:
        for account in accounts:
            conn.execute(
                """
                INSERT INTO accounts (
                    id, name, account, enabled, added_ts
                ) VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name    = excluded.name,
                    account = excluded.account,
                    enabled = 1
                """,
                (
                    int(account["id"]),
                    account.get("name") or "",
                    account.get("account") or "",
                    _account_added_ts(account, now),
                ),
            )
        if ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"UPDATE accounts SET enabled = 0 "
                f"WHERE id NOT IN ({placeholders})",
                ids,
            )
        else:
            conn.execute("UPDATE accounts SET enabled = 0")


def list_accounts(path: Path | str = DB_PATH) -> list[dict]:
    """Return enabled accounts with their visible work counts."""
    try:
        with connect(path) as conn:
            rows = conn.execute(
                """
                SELECT
                    a.id, a.name, a.account, a.enabled, a.initialized,
                    a.added_ts, a.last_sync_ts, a.last_error,
                    (
                        SELECT COUNT(*)
                        FROM bookmarks b
                        JOIN works w ON w.id = b.work_id
                        WHERE b.account_id = a.id AND w.missing = 0
                    ) AS works,
                    (
                        SELECT COUNT(*)
                        FROM bookmarks b
                        JOIN works w ON w.id = b.work_id
                        WHERE b.account_id = a.id AND w.missing = 0
                          AND w.x_restrict = 0
                    ) AS works_safe
                FROM accounts a
                WHERE a.enabled = 1
                ORDER BY a.added_ts ASC, a.id ASC
                """
            ).fetchall()
    except sqlite3.Error:
        return []
    return [dict(row) for row in rows]


def account_initialized(account_id: int, path: Path | str = DB_PATH) -> bool:
    try:
        with connect(path) as conn:
            row = conn.execute(
                "SELECT initialized FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
    except sqlite3.Error:
        return False
    return bool(row and row[0])


def replace_bookmarks(account_id: int, work_ids: list[int],
                      path: Path | str = DB_PATH) -> None:
    """Replace one account's bookmark set, preserving first-seen times."""
    ordered: list[int] = []
    seen: set[int] = set()
    for value in work_ids:
        try:
            work_id = int(value)
        except (TypeError, ValueError):
            continue
        if work_id not in seen:
            seen.add(work_id)
            ordered.append(work_id)

    now = int(time.time())
    with session(path) as conn:
        old = {
            row[0]: row[1]
            for row in conn.execute(
                "SELECT work_id, first_seen_ts FROM bookmarks "
                "WHERE account_id = ?",
                (account_id,),
            )
        }
        conn.execute(
            "DELETE FROM bookmarks WHERE account_id = ?", (account_id,)
        )
        conn.executemany(
            """
            INSERT INTO bookmarks (
                account_id, work_id, sort_order, first_seen_ts
            ) VALUES (?, ?, ?, ?)
            """,
            (
                (account_id, work_id, order, old.get(work_id, now))
                for order, work_id in enumerate(ordered)
            ),
        )


def mark_account_synced(account_id: int, path: Path | str = DB_PATH) -> None:
    with session(path) as conn:
        conn.execute(
            """
            UPDATE accounts
            SET last_sync_ts = ?, initialized = 1, last_error = NULL
            WHERE id = ?
            """,
            (int(time.time()), account_id),
        )


def mark_account_error(account_id: int, message: str,
                       path: Path | str = DB_PATH) -> None:
    with session(path) as conn:
        conn.execute(
            "UPDATE accounts SET last_error = ? WHERE id = ?",
            ((message or "")[-4000:], account_id),
        )

