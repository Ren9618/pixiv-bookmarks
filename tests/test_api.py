import json

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from pixivapp import db, main
from pixivapp.config import ACCOUNTS_DIR, IMAGES_DIR, THUMBS_DIR


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


def _seed_works(works: list[tuple[int, list[str], int]]):
    """Insert visible works with one page each for filter tests."""
    with db.session() as conn:
        for work_id, tags, x_restrict in works:
            conn.execute(
                """
                INSERT INTO works (
                    id, title, artist_id, artist_name, page_count,
                    tags_json, x_restrict, added_ts
                ) VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                """,
                (
                    work_id,
                    f"Work {work_id}",
                    work_id,
                    f"Artist {work_id}",
                    json.dumps(tags, ensure_ascii=False),
                    x_restrict,
                    work_id,
                ),
            )
            conn.execute(
                "INSERT INTO pages (work_id, num, rel_path, extension) "
                "VALUES (?, 0, ?, 'jpg')",
                (work_id, f"{work_id}/0.jpg"),
            )
            for tag in tags:
                conn.execute(
                    "INSERT INTO tags (work_id, tag) VALUES (?, ?)",
                    (work_id, tag),
                )


def test_api_items_supports_multiple_tags_with_and_or():
    with TestClient(main.app) as client:
        _seed_works([
            (1, ["blue", "sky"], 0),
            (2, ["blue"], 0),
            (3, ["red", "sky"], 0),
        ])

        response = client.get("/api/items?tag=blue&tag=sky&tag_mode=and")
        assert response.status_code == 200
        assert [item["id"] for item in response.json()["items"]] == [1]

        response = client.get("/api/items?tag=blue&tag=sky&tag_mode=or")
        assert response.status_code == 200
        assert {item["id"] for item in response.json()["items"]} == {1, 2, 3}

        response = client.get("/api/items?tag=blue")
        assert response.status_code == 200
        assert {item["id"] for item in response.json()["items"]} == {1, 2}

        response = client.get("/api/items?tag=blue&tag_mode=nope")
        assert response.status_code == 400


def test_collections_add_selected_and_by_tag():
    with TestClient(main.app) as client:
        _seed_works([
            (1, ["blue", "sky"], 0),
            (2, ["blue"], 0),
            (3, ["red"], 0),
        ])

        response = client.post("/api/collections", json={"name": "Favorites"})
        assert response.status_code == 200
        collection = response.json()["collection"]
        collection_id = collection["id"]

        response = client.post("/api/collections", json={"name": "favorites"})
        assert response.status_code == 409
        assert response.headers["X-Error-Code"] == "name_exists"

        response = client.post(
            f"/api/collections/{collection_id}/works",
            json={"ids": [1, 2]},
        )
        assert response.status_code == 200
        assert response.json()["added"] == 2

        response = client.get(f"/api/items?collection={collection_id}")
        assert response.status_code == 200
        assert {item["id"] for item in response.json()["items"]} == {1, 2}

        response = client.post(
            f"/api/collections/{collection_id}/works",
            json={"tags": ["blue", "sky"], "tag_mode": "and"},
        )
        assert response.status_code == 200
        assert response.json()["matched"] == 1
        assert response.json()["added"] == 0

        response = client.request(
            "DELETE",
            f"/api/collections/{collection_id}/works",
            json={"ids": [1]},
        )
        assert response.status_code == 200
        assert response.json()["removed"] == 1

        response = client.get("/api/collections")
        assert response.json()["collections"][0]["works"] == 1

        assert client.delete(f"/api/collections/{collection_id}").status_code == 200
        assert client.get("/api/collections").json()["collections"] == []


def test_tag_sets_create_list_and_delete():
    with TestClient(main.app) as client:
        response = client.post(
            "/api/tag-sets",
            json={"name": "Scenery", "tags": ["sky", "blue"], "match_mode": "or"},
        )
        assert response.status_code == 200
        tag_set = response.json()["tag_set"]

        response = client.post(
            "/api/tag-sets",
            json={"name": "scenery", "tags": ["sky"], "match_mode": "and"},
        )
        assert response.status_code == 409

        response = client.get("/api/tag-sets")
        assert response.status_code == 200
        assert response.json()["tag_sets"] == [tag_set]

        assert client.delete(f"/api/tag-sets/{tag_set['id']}").status_code == 200
        assert client.get("/api/tag-sets").json()["tag_sets"] == []


def test_deleting_works_removes_files_and_blocks_reindex():
    work_id = 9001
    image_dir = IMAGES_DIR / "12345 artist"
    image_dir.mkdir(parents=True, exist_ok=True)
    sidecar = image_dir / f"{work_id}_p00.jpg.json"
    media = image_dir / f"{work_id}_p00.jpg"
    sidecar.write_text(
        json.dumps({
            "id": work_id,
            "type": "illust",
            "title": "Delete me",
            "user": {"id": 12345, "name": "Artist", "account": "artist"},
            "width": 100,
            "height": 100,
        }),
        encoding="utf-8",
    )
    media.write_bytes(b"image")
    thumb = THUMBS_DIR / f"{work_id}_0.jpg"
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    thumb.write_bytes(b"thumb")

    with TestClient(main.app) as client:
        main.index_all()
        assert db.deleted_work_ids() == set()

        response = client.post("/api/works/delete", json={"ids": [work_id]})
        assert response.status_code == 200
        assert response.json()["deleted"] == 1
        assert not sidecar.exists()
        assert not media.exists()
        assert not thumb.exists()
        assert work_id in db.deleted_work_ids()

        # A full resync can download the artwork again.  The tombstone must
        # remain authoritative and the indexer must clean the files.
        sidecar.write_text(
            json.dumps({
                "id": work_id,
                "type": "illust",
                "title": "Delete me",
                "user": {"id": 12345, "name": "Artist", "account": "artist"},
            }),
            encoding="utf-8",
        )
        media.write_bytes(b"image")
        main.index_all()

        with db.connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM works WHERE id = ?", (work_id,)
            ).fetchone()[0] == 0
        assert not sidecar.exists()
        assert not media.exists()
        assert client.get("/api/items").json()["total"] == 0


def test_deleting_work_removes_collection_membership_and_bookmarks():
    with TestClient(main.app) as client:
        _seed_works([(42, ["tag"], 0)])
        with db.session() as conn:
            conn.execute(
                "INSERT INTO bookmarks (account_id, work_id) VALUES (7, 42)"
            )
        collection = client.post(
            "/api/collections", json={"name": "Temp"}
        ).json()["collection"]
        client.post(
            f"/api/collections/{collection['id']}/works",
            json={"ids": [42]},
        )

        response = client.post("/api/works/delete", json={"ids": [42]})
        assert response.status_code == 200
        with db.connect() as conn:
            assert conn.execute(
                "SELECT COUNT(*) FROM bookmarks WHERE work_id = 42"
            ).fetchone()[0] == 0
            assert conn.execute(
                "SELECT COUNT(*) FROM collection_works WHERE work_id = 42"
            ).fetchone()[0] == 0


def test_delete_waits_for_index_lock(monkeypatch):
    import threading

    from pixivapp import indexer

    with TestClient(main.app):
        _seed_works([(77, ["tag"], 0)])
    entered = threading.Event()
    finished = threading.Event()
    result = {}
    original_delete = indexer.db.delete_works

    def tracked_delete(ids):
        entered.set()
        return original_delete(ids)

    def worker():
        result["value"] = indexer.delete_works_and_purge([77])
        finished.set()

    monkeypatch.setattr(indexer.db, "delete_works", tracked_delete)
    lock_fp = indexer._acquire_index_lock()
    thread = threading.Thread(target=worker)
    try:
        thread.start()
        assert not entered.wait(0.2)
    finally:
        indexer._release_index_lock(lock_fp)

    assert entered.wait(2)
    thread.join(2)
    assert finished.is_set()
    assert result["value"][0] == [77]
    assert 77 in db.deleted_work_ids()
