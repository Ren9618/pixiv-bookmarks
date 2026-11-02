#!/usr/bin/env python3
"""Command-line helper for pixiv OAuth.

The viewer can add accounts entirely in the browser.  This script is the
fallback for headless installs.  It reuses ``app/pixivapp/oauth.py`` so the
CLI and the viewer share the same PKCE, credential storage and sync-queue
behaviour.  Only the Python standard library is required on the host.

Usage:
    python3 setup_auth.py init
    python3 setup_auth.py exchange --code '<code or callback URL>'
    python3 setup_auth.py exchange --code -     # read from stdin
    python3 setup_auth.py status
    python3 setup_auth.py remove --user-id 123456
"""

import argparse
import os
import sys
from pathlib import Path

if sys.version_info < (3, 10):
    raise SystemExit(
        "Python 3.10 or newer is required (3.12 recommended)."
    )

APP_DIR = Path(__file__).resolve().parent / "app"


def _read_dotenv(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE lines so the .env defaults match compose."""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _default_data_dir() -> str:
    env = _read_dotenv(Path(__file__).resolve().with_name(".env"))
    return (
        os.environ.get("DATA_DIR")
        or os.environ.get("PIXIV_DATA_DIR")
        or env.get("PIXIV_DATA_DIR")
        or "./data"
    )


def _load_modules(data_dir: str):
    root = Path(__file__).resolve().parent
    path = Path(data_dir).expanduser()
    if not path.is_absolute():
        path = root / path
    os.environ["DATA_DIR"] = str(path.resolve())
    if str(APP_DIR) not in sys.path:
        sys.path.insert(0, str(APP_DIR))

    from pixivapp import oauth
    from pixivapp.accounts import load_accounts, remove_account

    return oauth, load_accounts, remove_account


def cmd_init(_args, oauth, load_accounts, _remove_account) -> int:
    existing = load_accounts()
    info = oauth.create_login_url()
    if existing:
        print(f"現在 {len(existing)} アカウント登録済みです。")
        print("この認証を完了すると、別アカウントとして追加されます。")
        print()
    print("pixiv OAuth ログインURL:")
    print(info["login_url"])
    print()
    print("1. 上のURLをブラウザで開き、pixivにログインしてください。")
    print("2. ログイン後、開発者ツール（Network）で")
    print("   callback?…code=… のURLをコピーします（白いページは正常です）。")
    print("3. できるだけ早く次を実行します:")
    print(f"   python3 {Path(__file__).name} exchange --code '<code>'")
    print()
    print(
        "code は一度だけ・短時間だけ有効です。"
        "失敗したら init からやり直してください。"
    )
    return 0


def cmd_exchange(args, oauth, _load_accounts, _remove_account) -> int:
    raw = sys.stdin.read() if args.code == "-" else args.code
    try:
        result = oauth.exchange_code(raw)
    except oauth.OAuthError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    account = result["account"]
    print("認証に成功しました。")
    print(
        f"  user: {account['name'] or '(名前なし)'} "
        f"(@{account['account'] or '-'})"
    )
    print(f"  user_id: {account['id']}")
    print(f"  登録アカウント数: {result['accounts']}")
    print("  このアカウントの同期リクエストをキューに追加しました。")
    return 0


def cmd_status(_args, _oauth, load_accounts, _remove_account) -> int:
    accounts = load_accounts()
    if not accounts:
        print("未認証です。`python3 setup_auth.py init` から始めてください。")
        return 1
    print(f"認証済みアカウント: {len(accounts)}件")
    for account in accounts:
        print(
            f"- {account['name'] or '(名前なし)'} "
            f"(@{account['account'] or '-'}) user_id={account['id']}"
        )
        if account.get("obtained_at"):
            print(f"    取得日時: {account['obtained_at']}")
        print(f"    ファイル: {account['source']}")
    return 0


def cmd_remove(args, oauth, load_accounts, remove_account) -> int:
    accounts = {int(account["id"]): account for account in load_accounts()}
    account = accounts.get(int(args.user_id))
    if account is None:
        print(
            f"user_id {args.user_id} のアカウントは見つかりません。",
            file=sys.stderr,
        )
        return 1

    if not args.yes:
        label = f"{account['name'] or ''} (@{account['account'] or '-'})"
        answer = input(
            f"{label} user_id={args.user_id} の認証情報を削除しますか? "
            "[y/N]: "
        )
        if answer.strip().lower() not in {"y", "yes"}:
            print("中止しました。")
            return 1

    removed = remove_account(int(args.user_id))
    if not removed:
        print("削除対象のファイルがありませんでした。", file=sys.stderr)
        return 1
    for path in removed:
        print(f"削除: {path}")
    oauth.queue_sync(None)
    print("同期リクエストをキューに追加しました（アカウント一覧が更新されます）。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="pixiv OAuth helper")
    parser.add_argument(
        "--data-dir",
        default=_default_data_dir(),
        help="data directory (default: DATA_DIR / PIXIV_DATA_DIR / ./data)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create a login URL")
    exchange = sub.add_parser("exchange", help="exchange the callback code")
    exchange.add_argument(
        "--code",
        required=True,
        help="code value, full callback URL, or - for stdin",
    )
    sub.add_parser("status", help="show the stored accounts")
    remove = sub.add_parser("remove", help="remove one account's credentials")
    remove.add_argument("--user-id", type=int, required=True)
    remove.add_argument(
        "--yes", action="store_true", help="do not ask for confirmation"
    )
    args = parser.parse_args()

    oauth, load_accounts, remove_account = _load_modules(args.data_dir)
    handlers = {
        "init": cmd_init,
        "exchange": cmd_exchange,
        "status": cmd_status,
        "remove": cmd_remove,
    }
    return handlers[args.command](
        args, oauth, load_accounts, remove_account
    )


if __name__ == "__main__":
    raise SystemExit(main())
