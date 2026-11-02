"""Build the viewer database from gallery-dl metadata sidecar files."""

import fcntl
import html
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import db
from .accounts import load_accounts
from .config import (
    DB_PATH,
    IMAGES_DIR,
    INDEX_LOCK_PATH,
    ensure_dirs,
)

log = logging.getLogger("pixiv.indexer")

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"[ \t\r\f\v]+")
_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mkv", ".m4v"}
_MEDIA_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif",
    ".mp4", ".webm", ".mkv", ".m4v",
)


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _clean_text(value) -> str:
    if not value:
        return ""
    value = html.unescape(str(value))
    value = _TAG_RE.sub(" ", value)
    value = _SPACE_RE.sub(" ", value)
    return value.strip()[:20000]


def _tag_list(value) -> list[str]:
    tags: list[str] = []
    if not isinstance(value, list):
        return tags
    for entry in value:
        if isinstance(entry, str):
            tag = entry
        elif isinstance(entry, dict):
            tag = entry.get("name") or entry.get("translated_name") or ""
        else:
            tag = ""
        tag = html.unescape(str(tag)).strip()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _parse_created(value) -> tuple[str, int]:
    if not value:
        return "", 0
    text = str(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return text, int(parsed.timestamp())
    except (ValueError, OSError, OverflowError):
        return text, 0


def _resolve_media(json_path: Path) -> Optional[Path]:
    """Find the media file belonging to a metadata sidecar.

    gallery-dl writes ``<media filename>.json``.  Ugoira is downloaded as a
    zip, converted to mp4, and the zip is kept, so prefer the converted video
    when a sidecar points at a zip archive.
    """
    base = Path(str(json_path)[:-5])  # strip ".json"

    if base.suffix.lower() == ".zip":
        stem = base.with_suffix("")
        for extension in (".mp4", ".webm", ".mkv", ".m4v"):
            candidate = Path(str(stem) + extension)
            if candidate.is_file():
                return candidate
        return None

    if base.is_file():
        return base

    stem = base.with_suffix("")
    for extension in _MEDIA_EXTENSIONS:
        candidate = Path(str(stem) + extension)
        if candidate.is_file():
            return candidate
    return None


def _collect() -> tuple[
    dict[int, dict], dict[tuple[int, int], dict],
    dict[tuple[int, int], int],
]:
    works: dict[int, dict] = {}
    pages: dict[tuple[int, int], dict] = {}
    bookmark_seeds: dict[tuple[int, int], int] = {}
    scanned = 0

    if not IMAGES_DIR.is_dir():
        return works, pages, bookmark_seeds

    for root, _dirs, files in os.walk(IMAGES_DIR):
        for filename in files:
            if not filename.endswith(".json"):
                continue
            json_path = Path(root) / filename
            scanned += 1
            try:
                with json_path.open("r", encoding="utf-8") as fp:
                    data = json.load(fp)
            except (OSError, ValueError, UnicodeDecodeError):
                continue

            if not isinstance(data, dict):
                continue
            work_id = _as_int(data.get("id"))
            user = data.get("user")
            if not work_id or not isinstance(user, dict):
                continue
            if data.get("type") in {"avatar", "background"}:
                continue

            media_path = _resolve_media(json_path)
            if media_path is None:
                continue

            try:
                rel_path = media_path.relative_to(IMAGES_DIR).as_posix()
            except ValueError:
                continue

            try:
                added_ts = int(json_path.stat().st_mtime)
            except OSError:
                added_ts = 0

            owner = data.get("user_bookmark")
            if isinstance(owner, dict):
                owner_id = _as_int(owner.get("id"))
                if owner_id:
                    key = (owner_id, work_id)
                    previous_ts = bookmark_seeds.get(key)
                    if previous_ts is None or added_ts < previous_ts:
                        bookmark_seeds[key] = added_ts

            num = _as_int(data.get("num"), 0)
            extension = media_path.suffix.lower().lstrip(".")
            is_video = media_path.suffix.lower() in _VIDEO_EXTENSIONS

            page = {
                "num": num,
                "rel_path": rel_path,
                "extension": extension,
                "is_video": 1 if is_video else 0,
                "width": _as_int(data.get("width")),
                "height": _as_int(data.get("height")),
            }
            key = (work_id, num)
            previous = pages.get(key)
            if previous is None or (is_video and not previous["is_video"]):
                pages[key] = page

            if work_id in works:
                continue

            create_date, create_ts = _parse_created(data.get("create_date"))
            works[work_id] = {
                "id": work_id,
                "title": _clean_text(data.get("title")),
                "artist_id": _as_int(user.get("id")),
                "artist_name": _clean_text(user.get("name")),
                "artist_account": _clean_text(user.get("account")),
                "create_date": create_date,
                "create_ts": create_ts,
                "x_restrict": _as_int(data.get("x_restrict")),
                "sanity_level": _as_int(data.get("sanity_level")),
                "total_bookmarks": _as_int(data.get("total_bookmarks")),
                "tags_json": json.dumps(
                    _tag_list(data.get("tags")), ensure_ascii=False
                ),
                "description": _clean_text(
                    data.get("description") or data.get("caption")
                ),
                # gallery-dl preserves the artwork's original mtime on media
                # files, so use the metadata sidecar's time as the local
                # "downloaded/added" timestamp instead.
                "added_ts": added_ts,
            }

    log.info("scanned %d metadata files, found %d works / %d pages",
             scanned, len(works), len(pages))
    return works, pages, bookmark_seeds


def index_all() -> dict:
    """Rebuild pages/tags and upsert work metadata.  Safe to call repeatedly."""
    ensure_dirs()
    started = time.time()
    accounts = load_accounts()

    lock_fp = open(INDEX_LOCK_PATH, "w")
    try:
        fcntl.flock(lock_fp, fcntl.LOCK_EX)
        db.upsert_accounts(accounts)
        works, pages, bookmark_seeds = _collect()

        with db.session(DB_PATH) as conn:
            existing = {
                row[0] for row in conn.execute("SELECT id FROM works")
            }
            new_ids = [work_id for work_id in works if work_id not in existing]
            now = int(time.time())

            conn.execute("DELETE FROM pages")
            conn.execute("DELETE FROM tags")

            page_counts: dict[int, int] = {}
            for work_id, _num in pages:
                page_counts[work_id] = page_counts.get(work_id, 0) + 1

            for work in works.values():
                page_count = page_counts.get(work["id"], 0)
                conn.execute(
                    """
                    INSERT INTO works (
                        id, title, artist_id, artist_name, artist_account,
                        create_date, create_ts, x_restrict, sanity_level,
                        total_bookmarks, page_count, tags_json, description,
                        added_ts, updated_ts, missing
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                    ON CONFLICT(id) DO UPDATE SET
                        title           = excluded.title,
                        artist_id       = excluded.artist_id,
                        artist_name     = excluded.artist_name,
                        artist_account  = excluded.artist_account,
                        create_date     = excluded.create_date,
                        create_ts       = excluded.create_ts,
                        x_restrict      = excluded.x_restrict,
                        sanity_level    = excluded.sanity_level,
                        total_bookmarks = excluded.total_bookmarks,
                        page_count      = excluded.page_count,
                        tags_json       = excluded.tags_json,
                        description     = excluded.description,
                        updated_ts      = excluded.updated_ts,
                        missing         = 0
                    """,
                    (
                        work["id"], work["title"], work["artist_id"],
                        work["artist_name"], work["artist_account"],
                        work["create_date"], work["create_ts"],
                        work["x_restrict"], work["sanity_level"],
                        work["total_bookmarks"], page_count,
                        work["tags_json"], work["description"],
                        work["added_ts"], now,
                    ),
                )
                for tag in json.loads(work["tags_json"]):
                    conn.execute(
                        "INSERT OR IGNORE INTO tags (work_id, tag) VALUES (?, ?)",
                        (work["id"], tag),
                    )

            for (work_id, num), page in pages.items():
                conn.execute(
                    """
                    INSERT INTO pages (
                        work_id, num, rel_path, extension, is_video,
                        width, height
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(work_id, num) DO UPDATE SET
                        rel_path  = excluded.rel_path,
                        extension = excluded.extension,
                        is_video  = excluded.is_video,
                        width     = excluded.width,
                        height    = excluded.height
                    """,
                    (
                        work_id, num, page["rel_path"], page["extension"],
                        page["is_video"], page["width"], page["height"],
                    ),
                )

            conn.execute("CREATE TEMP TABLE IF NOT EXISTS seen_ids "
                         "(id INTEGER PRIMARY KEY)")

            initialized_ids = {
                int(row[0])
                for row in conn.execute(
                    "SELECT id FROM accounts WHERE initialized = 1"
                )
            }
            bookmarked_ids = {
                int(row[0])
                for row in conn.execute(
                    "SELECT DISTINCT account_id FROM bookmarks"
                )
            }
            valid_accounts = {int(account["id"]) for account in accounts}
            seed_accounts = valid_accounts - initialized_ids - bookmarked_ids

            if seed_accounts and bookmark_seeds:
                grouped: dict[int, list[tuple[int, int]]] = {}
                for (account_id, work_id), seen_ts in bookmark_seeds.items():
                    if account_id in seed_accounts:
                        grouped.setdefault(account_id, []).append(
                            (seen_ts or now, work_id)
                        )
                seeded_ids: set[int] = set()
                for account_id, entries in grouped.items():
                    entries.sort(key=lambda item: (-item[0], -item[1]))
                    conn.executemany(
                        """
                        INSERT OR IGNORE INTO bookmarks (
                            account_id, work_id, sort_order, first_seen_ts
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (
                            (account_id, work_id, order, seen_ts)
                            for order, (seen_ts, work_id) in enumerate(entries)
                        ),
                    )
                    seeded_ids.add(account_id)
                if seeded_ids:
                    placeholders = ",".join("?" for _ in seeded_ids)
                    conn.execute(
                        f"UPDATE accounts SET initialized = 1 "
                        f"WHERE id IN ({placeholders})",
                        list(seeded_ids),
                    )

            conn.execute("DELETE FROM seen_ids")
            conn.executemany(
                "INSERT OR IGNORE INTO seen_ids (id) VALUES (?)",
                ((work_id,) for work_id in works),
            )
            conn.execute(
                """
                UPDATE works
                SET missing = CASE
                    WHEN EXISTS (SELECT 1 FROM seen_ids s WHERE s.id = works.id)
                    THEN 0 ELSE 1 END
                """
            )

        elapsed = time.time() - started
        result = {
            "works": len(works),
            "images": len(pages),
            "new_works": len(new_ids),
            "accounts": len(accounts),
            "elapsed_sec": round(elapsed, 2),
        }
        log.info(
            "indexed %(works)d works / %(images)d images "
            "(%(new_works)d new, %(accounts)d accounts) "
            "in %(elapsed_sec).2fs", result
        )
        return result
    finally:
        try:
            fcntl.flock(lock_fp, fcntl.LOCK_UN)
        finally:
            lock_fp.close()
