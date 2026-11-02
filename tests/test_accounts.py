import json
import stat

from pixivapp import accounts
from pixivapp.config import ACCOUNT_PATH, ACCOUNTS_DIR, SECRETS_DIR


def _write_account(user_id: int, **overrides) -> dict:
    payload = {
        "user_id": user_id,
        "name": f"User {user_id}",
        "account": f"user_{user_id}",
        "refresh_token": f"token-{user_id}",
        "obtained_at": f"2026-01-0{user_id}T00:00:00+00:00",
    }
    payload.update(overrides)
    ACCOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ACCOUNTS_DIR / f"{user_id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)
    return payload


def test_load_accounts_discovers_every_valid_account():
    _write_account(2)
    _write_account(1)

    loaded = accounts.load_accounts()

    assert [account["id"] for account in loaded] == [1, 2]
    assert loaded[0]["refresh_token"] == "token-1"
    assert loaded[1]["name"] == "User 2"


def test_load_accounts_skips_malformed_and_incomplete_files():
    _write_account(1)
    (ACCOUNTS_DIR / "broken.json").write_text("{not json", encoding="utf-8")
    _write_account(2, refresh_token="")
    (ACCOUNTS_DIR / "no-id.json").write_text(
        json.dumps({"refresh_token": "token"}), encoding="utf-8"
    )

    loaded = accounts.load_accounts()

    assert [account["id"] for account in loaded] == [1]


def test_load_accounts_migrates_legacy_single_account():
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    ACCOUNT_PATH.write_text(
        json.dumps({
            "user_id": 777,
            "name": "Legacy",
            "account": "legacy_user",
            "obtained_at": "2025-12-01T00:00:00+00:00",
        }),
        encoding="utf-8",
    )
    (SECRETS_DIR / "refresh_token").write_text(
        "legacy-token\n", encoding="utf-8"
    )

    loaded = accounts.load_accounts()

    assert [account["id"] for account in loaded] == [777]
    assert loaded[0]["refresh_token"] == "legacy-token"
    target = ACCOUNTS_DIR / "777.json"
    assert target.exists()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert json.loads(target.read_text(encoding="utf-8"))["refresh_token"] == (
        "legacy-token"
    )


def test_public_account_never_exposes_the_refresh_token():
    public = accounts.public_account({
        "id": 1,
        "name": "User",
        "account": "user",
        "refresh_token": "super-secret",
        "source": "/data/secrets/accounts/1.json",
    })

    assert public == {"id": 1, "name": "User", "account": "user"}


def test_remove_account_only_removes_the_requested_account():
    _write_account(1)
    _write_account(2)

    removed = accounts.remove_account(1)

    assert removed == [ACCOUNTS_DIR / "1.json"]
    assert not (ACCOUNTS_DIR / "1.json").exists()
    assert (ACCOUNTS_DIR / "2.json").exists()


def test_remove_account_removes_legacy_files_too():
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    ACCOUNT_PATH.write_text(
        json.dumps({"user_id": 777, "refresh_token": "legacy-token"}),
        encoding="utf-8",
    )
    token_path = SECRETS_DIR / "refresh_token"
    token_path.write_text("legacy-token\n", encoding="utf-8")

    removed = accounts.remove_account(777)

    assert set(removed) == {ACCOUNT_PATH, token_path}
    assert not ACCOUNT_PATH.exists()
    assert not token_path.exists()


def test_remove_unknown_account_is_a_noop():
    _write_account(1)

    assert accounts.remove_account(999) == []
    assert (ACCOUNTS_DIR / "1.json").exists()
