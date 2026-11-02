"""SQLite storage for the bookmark index and local favorites."""

import json
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

CREATE TABLE IF NOT EXISTS deleted_works (
    work_id    INTEGER PRIMARY KEY,
    deleted_ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS collections (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL COLLATE NOCASE UNIQUE,
    created_ts INTEGER NOT NULL,
    updated_ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS collection_works (
    collection_id INTEGER NOT NULL,
    work_id       INTEGER NOT NULL,
    added_ts      INTEGER NOT NULL,
    PRIMARY KEY (collection_id, work_id),
    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
    FOREIGN KEY (work_id) REFERENCES works(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_collection_works_work
    ON collection_works(work_id);

CREATE TABLE IF NOT EXISTS tag_sets (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL COLLATE NOCASE UNIQUE,
    tags_json  TEXT    NOT NULL DEFAULT '[]',
    match_mode TEXT    NOT NULL DEFAULT 'and',
    created_ts INTEGER NOT NULL,
    updated_ts INTEGER NOT NULL
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
        deleted_ids = {
            int(row[0])
            for row in conn.execute("SELECT work_id FROM deleted_works")
        }
        if deleted_ids:
            ordered = [
                work_id for work_id in ordered if work_id not in deleted_ids
            ]
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


def _normalize_ids(values) -> list[int]:
    """Return unique positive integers from an arbitrary iterable."""
    ids: list[int] = []
    seen: set[int] = set()
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number <= 0 or number in seen:
            continue
        seen.add(number)
        ids.append(number)
    return ids


def deleted_work_ids(path: Path | str = DB_PATH) -> set[int]:
    try:
        with connect(path) as conn:
            return {
                int(row[0])
                for row in conn.execute("SELECT work_id FROM deleted_works")
            }
    except sqlite3.Error:
        return set()


def delete_works(work_ids, path: Path | str = DB_PATH) -> list[int]:
    """Forget local works and keep tombstones so later syncs cannot restore them."""
    ids = _normalize_ids(work_ids)
    if not ids:
        return []

    with session(path) as conn:
        placeholders = ",".join("?" for _ in ids)
        existing = [
            int(row[0])
            for row in conn.execute(
                f"SELECT id FROM works WHERE id IN ({placeholders})", ids
            )
        ]
        if not existing:
            return []

        now = int(time.time())
        conn.executemany(
            "INSERT OR REPLACE INTO deleted_works (work_id, deleted_ts) "
            "VALUES (?, ?)",
            ((work_id, now) for work_id in existing),
        )
        work_placeholders = ",".join("?" for _ in existing)
        for table in (
            "collection_works", "favorites", "bookmarks", "tags", "pages"
        ):
            conn.execute(
                f"DELETE FROM {table} WHERE work_id IN ({work_placeholders})",
                existing,
            )
        conn.execute(
            f"DELETE FROM works WHERE id IN ({work_placeholders})", existing
        )

    return existing


def list_collections(path: Path | str = DB_PATH) -> list[dict]:
    try:
        with connect(path) as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.name, c.created_ts, c.updated_ts,
                       COUNT(cw.work_id) AS works
                FROM collections c
                LEFT JOIN collection_works cw ON cw.collection_id = c.id
                GROUP BY c.id
                ORDER BY c.created_ts ASC, c.id ASC
                """
            ).fetchall()
    except sqlite3.Error:
        return []
    return [dict(row) for row in rows]


def get_collection(collection_id: int,
                   path: Path | str = DB_PATH) -> dict | None:
    try:
        with connect(path) as conn:
            row = conn.execute(
                """
                SELECT c.id, c.name, c.created_ts, c.updated_ts,
                       COUNT(cw.work_id) AS works
                FROM collections c
                LEFT JOIN collection_works cw ON cw.collection_id = c.id
                WHERE c.id = ?
                GROUP BY c.id
                """,
                (int(collection_id),),
            ).fetchone()
    except (sqlite3.Error, TypeError, ValueError):
        return None
    return dict(row) if row else None


def create_collection(name: str, path: Path | str = DB_PATH) -> dict:
    now = int(time.time())
    with session(path) as conn:
        cursor = conn.execute(
            "INSERT INTO collections (name, created_ts, updated_ts) "
            "VALUES (?, ?, ?)",
            (name, now, now),
        )
        collection_id = int(cursor.lastrowid)
    return {
        "id": collection_id,
        "name": name,
        "created_ts": now,
        "updated_ts": now,
        "works": 0,
    }


def rename_collection(collection_id: int, name: str,
                      path: Path | str = DB_PATH) -> bool:
    with session(path) as conn:
        cursor = conn.execute(
            "UPDATE collections SET name = ?, updated_ts = ? WHERE id = ?",
            (name, int(time.time()), int(collection_id)),
        )
    return cursor.rowcount > 0


def delete_collection(collection_id: int,
                      path: Path | str = DB_PATH) -> bool:
    with session(path) as conn:
        cursor = conn.execute(
            "DELETE FROM collections WHERE id = ?", (int(collection_id),)
        )
    return cursor.rowcount > 0


def add_collection_works(collection_id: int, work_ids,
                         path: Path | str = DB_PATH) -> int:
    ids = _normalize_ids(work_ids)
    if not ids:
        return 0

    with session(path) as conn:
        placeholders = ",".join("?" for _ in ids)
        existing = {
            int(row[0])
            for row in conn.execute(
                f"SELECT id FROM works WHERE missing = 0 "
                f"AND id IN ({placeholders})",
                ids,
            )
        }
        if not existing:
            return 0

        already = {
            int(row[0])
            for row in conn.execute(
                f"SELECT work_id FROM collection_works "
                f"WHERE collection_id = ? AND work_id IN ({placeholders})",
                [int(collection_id), *ids],
            )
        }
        new_ids = sorted(existing - already)
        if not new_ids:
            return 0

        now = int(time.time())
        conn.executemany(
            "INSERT OR IGNORE INTO collection_works "
            "(collection_id, work_id, added_ts) VALUES (?, ?, ?)",
            ((int(collection_id), work_id, now) for work_id in new_ids),
        )
        conn.execute(
            "UPDATE collections SET updated_ts = ? WHERE id = ?",
            (now, int(collection_id)),
        )
    return len(new_ids)


def remove_collection_works(collection_id: int, work_ids,
                            path: Path | str = DB_PATH) -> int:
    ids = _normalize_ids(work_ids)
    if not ids:
        return 0

    placeholders = ",".join("?" for _ in ids)
    with session(path) as conn:
        cursor = conn.execute(
            f"DELETE FROM collection_works WHERE collection_id = ? "
            f"AND work_id IN ({placeholders})",
            [int(collection_id), *ids],
        )
        if cursor.rowcount:
            conn.execute(
                "UPDATE collections SET updated_ts = ? WHERE id = ?",
                (int(time.time()), int(collection_id)),
            )
    return max(0, cursor.rowcount)


def list_tag_sets(path: Path | str = DB_PATH) -> list[dict]:
    try:
        with connect(path) as conn:
            rows = conn.execute(
                "SELECT id, name, tags_json, match_mode, created_ts, updated_ts "
                "FROM tag_sets ORDER BY created_ts ASC, id ASC"
            ).fetchall()
    except sqlite3.Error:
        return []

    result: list[dict] = []
    for row in rows:
        try:
            tags = json.loads(row["tags_json"] or "[]")
        except ValueError:
            tags = []
        if not isinstance(tags, list):
            tags = []
        result.append({
            "id": row["id"],
            "name": row["name"],
            "tags": [str(tag) for tag in tags],
            "match_mode": row["match_mode"],
            "created_ts": row["created_ts"],
            "updated_ts": row["updated_ts"],
        })
    return result


def create_tag_set(name: str, tags: list[str], match_mode: str,
                   path: Path | str = DB_PATH) -> dict:
    now = int(time.time())
    with session(path) as conn:
        cursor = conn.execute(
            "INSERT INTO tag_sets "
            "(name, tags_json, match_mode, created_ts, updated_ts) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                name,
                json.dumps(tags, ensure_ascii=False),
                match_mode,
                now,
                now,
            ),
        )
        tag_set_id = int(cursor.lastrowid)
    return {
        "id": tag_set_id,
        "name": name,
        "tags": tags,
        "match_mode": match_mode,
        "created_ts": now,
        "updated_ts": now,
    }


def delete_tag_set(tag_set_id: int, path: Path | str = DB_PATH) -> bool:
    with session(path) as conn:
        cursor = conn.execute(
            "DELETE FROM tag_sets WHERE id = ?", (int(tag_set_id),)
        )
    return cursor.rowcount > 0

