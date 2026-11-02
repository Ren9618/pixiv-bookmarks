"""FastAPI viewer for downloaded pixiv bookmarks."""

import asyncio
import json
import logging
import mimetypes
import os
import secrets as pysecrets
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageDraw
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from . import db, oauth
from .accounts import load_accounts
from .config import (
    APP_NAME,
    DB_PATH,
    IMAGES_DIR,
    STATUS_PATH,
    SYNC_INTERVAL_MINUTES,
    SYNC_LOG_PATH,
    SYNC_REQUEST_PATH,
    THUMBS_DIR,
    VIEWER_PASSWORD,
    VIEWER_SECRET,
    ensure_dirs,
)
from .indexer import index_all

log = logging.getLogger("pixiv.viewer")
Image.MAX_IMAGE_PIXELS = None

if not VIEWER_PASSWORD:
    log.warning(
        "VIEWER_PASSWORD is empty: the viewer is reachable without a password"
    )
elif VIEWER_PASSWORD == "change-me":
    log.warning(
        "VIEWER_PASSWORD is still the example value; set a real password"
    )
viewer_secret_env = os.environ.get("VIEWER_SECRET", "")
if not viewer_secret_env:
    log.warning(
        "VIEWER_SECRET is empty: sessions will be invalidated on restart"
    )
elif viewer_secret_env == "change-me-too":
    log.warning(
        "VIEWER_SECRET is still the example value; set a random secret"
    )

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def _read_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _parse_account_id(value: Optional[str]) -> Optional[int]:
    """Return a numeric account id, treating empty/all as "no filter"."""
    if value is None:
        return None
    value = str(value).strip()
    if not value or value == "all":
        return None
    try:
        account_id = int(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid account")
    if account_id <= 0:
        raise HTTPException(status_code=400, detail="invalid account")
    return account_id


def _iso_from_ts(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp).astimezone().isoformat(
        timespec="seconds"
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_dirs()
    db.init_db()
    try:
        await run_in_threadpool(index_all)
    except Exception:
        log.exception("initial index failed")
    yield


app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _safe_next(value: str) -> str:
    if (
        not value
        or not value.startswith("/")
        or value.startswith("//")
        or "\\" in value
        or len(value) > 2048
        or any(character in value for character in "\r\n\0")
    ):
        return "/"
    return value


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    public = (
        path == "/login"
        or path == "/healthz"
        or path == "/manifest.webmanifest"
        or path == "/favicon.ico"
        or path.startswith("/static/")
    )
    if not VIEWER_PASSWORD or public or request.session.get("auth"):
        return await call_next(request)

    if path.startswith("/api/"):
        return JSONResponse({"detail": "unauthorized"}, status_code=401)
    next_value = path
    if request.url.query:
        next_value += "?" + request.url.query
    next_url = quote(next_value, safe="/")
    return RedirectResponse(f"/login?next={next_url}", status_code=303)


# SessionMiddleware must wrap the auth middleware, so add it after the
# middleware above has been registered.
app.add_middleware(
    SessionMiddleware,
    secret_key=VIEWER_SECRET,
    session_cookie="pixiv_viewer_session",
    max_age=60 * 60 * 24 * 30,
    same_site="lax",
    https_only=False,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; media-src 'self'; "
        "style-src 'self' 'unsafe-inline'; script-src 'self'; "
        "connect-src 'self'; form-action 'self'; frame-ancestors 'none'; "
        "base-uri 'none'",
    )
    return response


@app.get("/healthz")
async def healthz():
    return {"ok": True, "auth": bool(VIEWER_PASSWORD)}


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)


@app.get("/manifest.webmanifest")
async def manifest():
    return FileResponse(
        STATIC_DIR / "manifest.webmanifest",
        media_type="application/manifest+json",
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    if not VIEWER_PASSWORD or request.session.get("auth"):
        return RedirectResponse(_safe_next(next), status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {"app_name": APP_NAME, "next": _safe_next(next), "error": None},
    )


@app.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request):
    form = await request.form()
    password = str(form.get("password") or "")
    next_url = _safe_next(str(form.get("next") or "/"))
    if VIEWER_PASSWORD and pysecrets.compare_digest(password, VIEWER_PASSWORD):
        request.session["auth"] = True
        return RedirectResponse(next_url, status_code=303)

    await asyncio.sleep(0.7)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "app_name": APP_NAME,
            "next": next_url,
            "error": "パスワードが違います。",
        },
        status_code=401,
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "app_name": APP_NAME,
            "auth_enabled": bool(VIEWER_PASSWORD),
        },
    )


def _where_clause(
    q: str,
    tag: str,
    artist: Optional[int],
    favorites: bool,
    include_r18: bool,
    account_id: Optional[int] = None,
) -> tuple[str, list]:
    clauses = ["w.missing = 0"]
    params: list = []

    if not include_r18:
        clauses.append("w.x_restrict = 0")
    if account_id is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM bookmarks b "
            "WHERE b.work_id = w.id AND b.account_id = ?)"
        )
        params.append(account_id)
    if favorites:
        clauses.append(
            "EXISTS (SELECT 1 FROM favorites f WHERE f.work_id = w.id)"
        )
    if tag:
        clauses.append(
            "EXISTS (SELECT 1 FROM tags t WHERE t.work_id = w.id AND t.tag = ?)"
        )
        params.append(tag)
    if artist is not None:
        clauses.append("w.artist_id = ?")
        params.append(artist)
    if q:
        like = f"%{q}%"
        clauses.append(
            "(w.title LIKE ? OR w.artist_name LIKE ? OR "
            "w.artist_account LIKE ? OR EXISTS ("
            "SELECT 1 FROM tags t WHERE t.work_id = w.id AND t.tag LIKE ?))"
        )
        params.extend([like, like, like, like])

    return " AND ".join(clauses), params


def _sort_clause(sort: str) -> str:
    return {
        "added_desc": "w.added_ts DESC, w.id DESC",
        "create_desc": "w.create_ts DESC, w.id DESC",
        "popular_desc": "w.total_bookmarks DESC, w.id DESC",
        "title_asc": "w.title COLLATE NOCASE ASC, w.id ASC",
    }.get(sort, "w.added_ts DESC, w.id DESC")


def _row_to_item(row, pages: list[dict], favorited: bool) -> dict:
    try:
        tags = json.loads(row["tags_json"] or "[]")
    except ValueError:
        tags = []
    if not isinstance(tags, list):
        tags = []

    page_list = []
    for page in pages:
        page_list.append({
            "num": page["num"],
            "extension": page["extension"],
            "is_video": bool(page["is_video"]),
            "width": page["width"],
            "height": page["height"],
            "media_url": f"/media/{row['id']}/{page['num']}",
            "thumb_url": f"/thumb/{row['id']}/{page['num']}",
        })
    cover = next((p for p in page_list if p["num"] == 0), page_list[0])
    return {
        "id": row["id"],
        "title": row["title"],
        "artist_id": row["artist_id"],
        "artist_name": row["artist_name"],
        "artist_account": row["artist_account"],
        "create_date": row["create_date"],
        "create_ts": row["create_ts"],
        "added_ts": row["added_ts"],
        "x_restrict": row["x_restrict"],
        "sanity_level": row["sanity_level"],
        "total_bookmarks": row["total_bookmarks"],
        "page_count": len(page_list),
        "pages": page_list,
        "cover": cover["num"],
        "thumb_url": cover["thumb_url"],
        "is_video": any(p["is_video"] for p in page_list),
        "tags": tags,
        "favorited": favorited,
        "pixiv_url": f"https://www.pixiv.net/artworks/{row['id']}",
    }


@app.get("/api/items")
async def api_items(
    q: str = "",
    tag: str = "",
    artist: Optional[str] = None,
    account: Optional[str] = None,
    favorites: int = 0,
    r18: int = 0,
    sort: str = "added_desc",
    offset: int = Query(0, ge=0),
    limit: int = Query(60, ge=1, le=100),
):
    q = q.strip()[:200]
    tag = tag.strip()[:200]
    artist_id = None
    if artist:
        try:
            artist_id = int(artist)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid artist")
    account_id = _parse_account_id(account)
    where_sql, where_params = _where_clause(
        q, tag, artist_id, bool(favorites), bool(r18), account_id
    )
    order_sql = _sort_clause(sort)

    with db.session(DB_PATH) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM works w WHERE {where_sql}",
            where_params,
        ).fetchone()[0]
        rows = conn.execute(
            f"SELECT w.* FROM works w WHERE {where_sql} "
            f"ORDER BY {order_sql} LIMIT ? OFFSET ?",
            [*where_params, limit, offset],
        ).fetchall()

        ids = [row["id"] for row in rows]
        pages_by_work: dict[int, list[dict]] = {work_id: [] for work_id in ids}
        favorite_ids: set[int] = set()
        if ids:
            placeholders = ",".join("?" for _ in ids)
            for page in conn.execute(
                f"SELECT work_id, num, extension, is_video, width, height "
                f"FROM pages WHERE work_id IN ({placeholders}) "
                f"ORDER BY work_id, num",
                ids,
            ):
                pages_by_work[page["work_id"]].append({
                    "num": page["num"],
                    "extension": page["extension"],
                    "is_video": page["is_video"],
                    "width": page["width"],
                    "height": page["height"],
                })
            for row in conn.execute(
                f"SELECT work_id FROM favorites "
                f"WHERE work_id IN ({placeholders})",
                ids,
            ):
                favorite_ids.add(row["work_id"])

    items = []
    for row in rows:
        pages = pages_by_work.get(row["id"]) or []
        if not pages:
            continue
        items.append(_row_to_item(row, pages, row["id"] in favorite_ids))

    return {
        "items": items,
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@app.get("/api/tags")
async def api_tags(
    r18: int = 0,
    account: Optional[str] = None,
    limit: int = Query(60, ge=1, le=200),
):
    clauses = ["w.missing = 0"]
    params: list = []
    if not r18:
        clauses.append("w.x_restrict = 0")
    account_id = _parse_account_id(account)
    if account_id is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM bookmarks b "
            "WHERE b.work_id = w.id AND b.account_id = ?)"
        )
        params.append(account_id)
    where_sql = " AND ".join(clauses)
    with db.session(DB_PATH) as conn:
        rows = conn.execute(
            f"SELECT t.tag AS tag, COUNT(*) AS count FROM tags t "
            f"JOIN works w ON w.id = t.work_id WHERE {where_sql} "
            f"GROUP BY t.tag ORDER BY count DESC, t.tag ASC LIMIT ?",
            [*params, limit],
        ).fetchall()
    return {"tags": [{"tag": row["tag"], "count": row["count"]} for row in rows]}


@app.get("/api/artists")
async def api_artists(
    r18: int = 0,
    account: Optional[str] = None,
    limit: int = Query(100, ge=1, le=300),
):
    clauses = ["w.missing = 0", "w.artist_id IS NOT NULL", "w.artist_id != 0"]
    params: list = []
    if not r18:
        clauses.append("w.x_restrict = 0")
    account_id = _parse_account_id(account)
    if account_id is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM bookmarks b "
            "WHERE b.work_id = w.id AND b.account_id = ?)"
        )
        params.append(account_id)
    where_sql = " AND ".join(clauses)
    with db.session(DB_PATH) as conn:
        rows = conn.execute(
            f"SELECT w.artist_id, MAX(w.artist_name) AS artist_name, "
            f"COUNT(*) AS count FROM works w WHERE {where_sql} "
            f"GROUP BY w.artist_id ORDER BY count DESC, artist_name ASC "
            f"LIMIT ?",
            [*params, limit],
        ).fetchall()
    return {
        "artists": [
            {
                "id": row["artist_id"],
                "name": row["artist_name"] or str(row["artist_id"]),
                "count": row["count"],
            }
            for row in rows
        ]
    }


@app.get("/api/accounts")
async def api_accounts():
    return {"accounts": db.list_accounts()}


@app.post("/api/accounts/oauth/start")
async def api_oauth_start():
    """Issue a fresh pixiv login URL for the add-account form."""
    try:
        return await run_in_threadpool(oauth.create_login_url)
    except OSError as exc:
        log.exception("could not store the OAuth challenge")
        raise HTTPException(
            status_code=500,
            detail=f"ログインURLを保存できませんでした: {exc}",
        )


@app.get("/api/accounts/oauth/pending")
async def api_oauth_pending():
    """Return the login URL that is still usable, if any."""
    return await run_in_threadpool(oauth.pending_info)


@app.post("/api/accounts/oauth/exchange")
async def api_oauth_exchange(request: Request):
    """Exchange a pasted callback URL/code and add the pixiv account."""
    body: dict = {}
    try:
        parsed = await request.json()
        if isinstance(parsed, dict):
            body = parsed
    except Exception:
        pass

    raw_code = body.get("code")
    if not isinstance(raw_code, str) or not raw_code.strip():
        raise HTTPException(
            status_code=400,
            detail="コールバックURLまたは code を貼り付けてください。",
        )

    try:
        result = await run_in_threadpool(oauth.exchange_code, raw_code)
    except oauth.OAuthError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Make the new account visible in /api/status immediately instead of
    # waiting for the sync container to run its indexer.
    try:
        await run_in_threadpool(
            db.upsert_accounts, load_accounts()
        )
    except Exception:
        log.exception("could not refresh the account table")

    return result


@app.post("/api/favorite/{work_id}")
async def api_favorite(work_id: int, request: Request):
    body: dict = {}
    try:
        parsed = await request.json()
        if isinstance(parsed, dict):
            body = parsed
    except Exception:
        pass

    with db.session(DB_PATH) as conn:
        exists = conn.execute(
            "SELECT 1 FROM works WHERE id = ? AND missing = 0", (work_id,)
        ).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="work not found")

        current = conn.execute(
            "SELECT 1 FROM favorites WHERE work_id = ?", (work_id,)
        ).fetchone() is not None
        if "favorited" in body:
            desired = bool(body["favorited"])
        else:
            desired = not current

        if desired and not current:
            conn.execute(
                "INSERT OR IGNORE INTO favorites (work_id, created_ts) "
                "VALUES (?, ?)",
                (work_id, int(datetime.now().timestamp())),
            )
        elif not desired and current:
            conn.execute(
                "DELETE FROM favorites WHERE work_id = ?", (work_id,)
            )

    return {"work_id": work_id, "favorited": desired}


@app.post("/api/reindex")
async def api_reindex():
    try:
        result = await run_in_threadpool(index_all)
    except Exception as exc:
        log.exception("manual reindex failed")
        raise HTTPException(status_code=500, detail=f"reindex failed: {exc}")
    return {"ok": True, **result, **db.counts()}


@app.post("/api/sync")
async def api_sync(request: Request, full: int = 0):
    body: dict = {}
    try:
        parsed = await request.json()
        if isinstance(parsed, dict):
            body = parsed
    except Exception:
        pass

    mode = "full" if full else str(body.get("mode") or "normal")
    if mode not in {"normal", "full"}:
        raise HTTPException(status_code=400, detail="invalid sync mode")

    raw_account = body.get("account_id", body.get("account"))
    account_id = _parse_account_id(
        None if raw_account in (None, "") else str(raw_account)
    )
    if account_id is not None:
        known = {int(account["id"]) for account in load_accounts()}
        if account_id not in known:
            raise HTTPException(status_code=404, detail="account not found")

    payload: dict = {"mode": mode}
    if account_id is not None:
        payload["account_id"] = account_id

    SYNC_REQUEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    SYNC_REQUEST_PATH.write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    try:
        os.chmod(SYNC_REQUEST_PATH, 0o644)
    except OSError:
        pass
    return {"queued": True, "full": mode == "full", "account_id": account_id}


@app.get("/api/status")
async def api_status():
    status = _read_json(STATUS_PATH)
    counts = db.counts()
    accounts = db.list_accounts()
    enabled_ids = {int(account["id"]) for account in accounts}
    account_results = [
        result
        for result in (status.get("account_results") or [])
        if isinstance(result, dict) and result.get("id") in enabled_ids
    ]
    try:
        db_updated = _iso_from_ts(DB_PATH.stat().st_mtime)
    except OSError:
        db_updated = None

    result = {
        "state": status.get("state", "unknown"),
        "message": status.get("message", ""),
        "started_at": status.get("started_at"),
        "finished_at": status.get("finished_at"),
        "updated_at": status.get("updated_at"),
        "next_run": status.get("next_run"),
        "last_exit_code": status.get("last_exit_code"),
        "last_exit_codes": status.get("last_exit_codes"),
        "last_duration_sec": status.get("last_duration_sec"),
        "last_new_works": status.get("last_new_works"),
        "last_error": status.get("last_error"),
        "full_sync": status.get("full_sync"),
        "account": accounts[0] if accounts else status.get("account"),
        "accounts": accounts,
        "account_results": account_results,
        "auth_required": status.get("state") == "auth_required"
                         or not accounts,
        "sync_queued": SYNC_REQUEST_PATH.exists(),
        "interval_minutes": SYNC_INTERVAL_MINUTES,
        "db_updated_at": db_updated,
        "counts": counts,
    }
    return result


@app.post("/api/log")
async def api_log_post():
    return await api_log()


@app.get("/api/log")
async def api_log(lines: int = Query(120, ge=1, le=500)):
    try:
        with SYNC_LOG_PATH.open("r", encoding="utf-8", errors="replace") as fp:
            content = fp.readlines()
    except OSError:
        return {"lines": []}
    return {"lines": [line.rstrip("\n") for line in content[-lines:]]}


def _page_row(work_id: int, num: int):
    with db.session(DB_PATH) as conn:
        return conn.execute(
            "SELECT p.* FROM pages p JOIN works w ON w.id = p.work_id "
            "WHERE p.work_id = ? AND p.num = ? AND w.missing = 0",
            (work_id, num),
        ).fetchone()


def _media_path(work_id: int, num: int) -> tuple[Path, str]:
    row = _page_row(work_id, num)
    if row is None:
        raise HTTPException(status_code=404, detail="page not found")

    root = IMAGES_DIR.resolve()
    path = (IMAGES_DIR / row["rel_path"]).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        raise HTTPException(status_code=404, detail="invalid path")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file missing")
    return path, row["extension"]


def _placeholder(path: Path, label: str = "NO IMAGE") -> None:
    image = Image.new("RGB", (640, 640), (25, 26, 34))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 639, 639), outline=(55, 57, 72), width=3)
    draw.polygon([(280, 220), (280, 420), (430, 320)], fill=(255, 107, 157))
    draw.text((20, 600), label, fill=(160, 163, 177))
    image.save(path, "JPEG", quality=82)


def _video_thumb(source: Path, target: Path) -> None:
    tmp = target.with_name(target.name + f".{os.getpid()}.tmp.jpg")
    try:
        for seek in ("0.8", "0"):
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-hide_banner", "-loglevel", "error",
                        "-ss", seek, "-i", str(source),
                        "-frames:v", "1",
                        "-vf", "scale='min(640,iw)':-2",
                        "-y", str(tmp),
                    ],
                    check=True,
                    timeout=45,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if tmp.is_file() and tmp.stat().st_size > 0:
                os.replace(tmp, target)
                return
        raise RuntimeError("ffmpeg produced no frame")
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _ensure_thumb(work_id: int, num: int) -> Path:
    source, extension = _media_path(work_id, num)
    target = THUMBS_DIR / f"{work_id}_{num}.jpg"
    try:
        if target.is_file() and target.stat().st_mtime >= source.stat().st_mtime:
            return target
    except OSError:
        pass

    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        if extension in {"mp4", "webm", "mkv", "m4v"}:
            _video_thumb(source, target)
        else:
            tmp = target.with_name(target.name + f".{os.getpid()}.tmp.jpg")
            try:
                with Image.open(source) as image:
                    try:
                        image.seek(0)
                    except EOFError:
                        pass
                    image.thumbnail((640, 640), Image.Resampling.LANCZOS)
                    if image.mode in ("RGBA", "LA") or (
                        image.mode == "P" and "transparency" in image.info
                    ):
                        rgba = image.convert("RGBA")
                        background = Image.new("RGB", rgba.size, (255, 255, 255))
                        background.paste(rgba, mask=rgba.split()[-1])
                        output = background
                    else:
                        output = image.convert("RGB")
                    output.save(tmp, "JPEG", quality=82, optimize=True)
                os.replace(tmp, target)
            finally:
                try:
                    tmp.unlink()
                except OSError:
                    pass
    except Exception:
        log.exception("thumbnail failed for %s/%s", work_id, num)
        _placeholder(target, "NO IMAGE")
    return target


@app.get("/thumb/{work_id}/{num}")
async def thumb(work_id: int, num: int):
    target = await run_in_threadpool(_ensure_thumb, work_id, num)
    return FileResponse(
        target,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@app.get("/media/{work_id}/{num}")
async def media(work_id: int, num: int, download: int = 0):
    path, _extension = _media_path(work_id, num)
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    headers = {"Cache-Control": "private, max-age=86400"}
    if download:
        return FileResponse(
            path,
            media_type=media_type,
            filename=path.name,
            content_disposition_type="attachment",
            headers=headers,
        )
    return FileResponse(path, media_type=media_type, headers=headers)
