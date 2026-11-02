# Pixiv Bookmarks

pixivのブックマーク（公開・非公開の両方）を定期的にダウンロードし、自分専用のWebビューワーで閲覧するためのセルフホスト型スタックです。複数アカウントに対応しています。

[English README](README.md)

> 非公式プロジェクトです。pixivとは一切関係ありません。自己責任で利用し、pixivの利用規約とレート制限を守ってください。

## 主な機能

- 複数pixivアカウントの**公開・非公開ブックマーク**をダウンロード
- 15分ごとの差分同期、手動同期、全件再同期
- ビューワー上で**pixivアカウントを追加**（OAuth + PKCE、SSH不要）
- 検索、タグ、作者、アカウント絞り込み、R-18表示切替、ローカルお気に入り
- ライトボックス、キーボード操作、スワイプ、スマホの左右タップ操作
- SQLiteインデックス、サムネイル自動生成、PWAマニフェスト
- Docker Composeで完結。データはすべて自分のディスク上に保存

ビューワーのUIは日本語です。

## 構成

```text
┌──────────────────────────────┐
│ pixiv-sync                   │
│  gallery-dl + pixiv API      │
└──────────────┬───────────────┘
               │ 書き込み
               ▼
     /data/images/          作品画像
     /data/state/gallery.db SQLiteインデックス
     /data/secrets/         OAuthリフレッシュトークン（0600）
               ▲
               │ 読み込み + state/sync.request
┌──────────────┴───────────────┐
│ pixiv-viewer                 │
│  FastAPI + バニラJS          │
└──────────────────────────────┘
```

- **sync** — [gallery-dl](https://github.com/mikf/gallery-dl) で画像を取得し、pixiv APIでブックマーク順を保存します。
- **viewer** — ギャラリー表示、アカウント追加、オンデマンド同期を行います。
- 認証情報は `secrets/accounts/<user_id>.json` に `0600` で保存されます。

## 必要なもの

- Docker Engine + Compose v2
- pixivアカウント
- Python 3.10以上（3.12推奨）— CLIフォールバックとテストで使用
- Linuxを推奨（バインドマウントの所有者管理が簡単です）。macOS/WindowsのDocker Desktopでも動作しますが、`PUID`/`PGID`の扱いが異なります。

## クイックスタート

```bash
git clone https://github.com/Ren9618/pixiv-bookmarks.git
cd pixiv-bookmarks
cp .env.example .env
```

`.env` を最低限編集します。

```dotenv
VIEWER_PASSWORD=あなたのパスワード
VIEWER_SECRET=<openssl rand -hex 32 の出力>
PIXIV_DATA_DIR=/absolute/path/to/pixiv-data
PUID=1000
PGID=1000
```

`PUID`/`PGID` は `PIXIV_DATA_DIR` に書き込めるユーザーにしてください（`id -u` / `id -g` で確認できます）。起動:

```bash
docker compose up -d --build
```

<http://127.0.0.1:8899> を開きます。

別端末から見る場合は `VIEWER_BIND=0.0.0.0`（LAN/Tailscale）にするか、リバースプロキシや `tailscale serve` を `127.0.0.1:8899` に向けてください。外部から到達できる場合は必ず `VIEWER_PASSWORD` を設定してください。

アカウント追加後、初回同期が自動で始まります。ブックマークが多い場合は時間がかかります。

## pixivアカウントの追加

pixivのAPIアクセスにはOAuthのリフレッシュトークンが必要です。Cookieだけではgallery-dlのAPI認証は通りません。

### ビューワーから追加（推奨）

1. ビューワー右上の**同期ステータス** → **＋ pixivアカウントを追加** を開く
2. **ログインURLを発行** を押し、表示されたリンクを開く
3. **ログインする前に** 開発者ツール（`F12`、Macは `⌘⌥I`）→ **Network** を開き、**Preserve log** を有効にする
4. 追加したいアカウントでログインする（白いページや `pixiv://` への遷移は正常）
5. Network一覧の `callback?…code=…` を右クリック → **Copy link address**（Firefoxは**URLをコピー**）
6. ビューワーの欄に貼り付けて **このアカウントを追加** を押す

認証コードの有効期限は数十秒です。ログイン後すぐに貼り付けてください。

**なぜDevToolsが必要？** pixivはコールバック後に `pixiv://`（ネイティブアプリ）へリダイレクトするため、codeがアドレスバーに残りません。Networkタブの `callback` リクエストが確実な取得場所です。交換はサーバー側で行い、トークンは `0600` で保存されます。同じpixivユーザーで再認証しない限り、既存アカウントが置き換わることはありません。

### コマンドラインから追加（予備）

```bash
python3 setup_auth.py init
# 表示されたURLでログインし、コールバックURLまたはcodeをコピー
python3 setup_auth.py exchange --code '<コールバックURLまたはcode>'
python3 setup_auth.py status
python3 setup_auth.py remove --user-id 123456
```

`setup_auth.py` は `.env` の `PIXIV_DATA_DIR` を読みます。変更する場合は `--data-dir /path/to/data` を指定してください。`exchange --code -` で標準入力から読み込めます。

## 設定

| 変数 | 既定値 | 説明 |
| --- | --- | --- |
| `PIXIV_DATA_DIR` | `./data` | `/data` にマウントするホスト側ディレクトリ |
| `PUID` / `PGID` | `1000` | 両コンテナの実行UID/GID |
| `VIEWER_BIND` | `127.0.0.1` | ビューワーのバインド先 |
| `VIEWER_PORT` | `8899` | ビューワーのホスト側ポート |
| `VIEWER_PASSWORD` | 空 | ビューワーのパスワード。空だと認証なし |
| `VIEWER_SECRET` | ランダム | セッション署名鍵。再起動後もログインを維持するため設定 |
| `SYNC_INTERVAL_MINUTES` | `15` | 自動同期の間隔 |
| `TZ` | `Asia/Tokyo` | ログとタイムスタンプのタイムゾーン |

`PIXIV_DATA_DIR` の中身:

```text
images/<artist_id> <artist_account>/<work_id>_p00.jpg
state/gallery.db       SQLiteインデックス・お気に入り
state/status.json      同期ステータス
state/sync.request     オンデマンド同期キュー
secrets/accounts/      OAuthトークン（0600）
thumbs/                生成済みサムネイル
logs/sync.log          ローテーションされる同期ログ
```

## ビューワーの操作

- 画像の**左40%をタップ**で前へ、**右側または中央をタップ**で次へ
- 左右スワイプで作品移動、下スワイプで閉じる
- `←` / `→` で移動、`Esc` で閉じる
- ツールバーからアカウント・タグ・作者・R-18・お気に入りで絞り込み
- 同期ステータスでアカウントごとの作品数・最終同期・エラーを確認し、個別に同期可能

## 開発

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

ruff check .
pytest -q
docker compose build
```

ディレクトリ構成:

```text
app/pixivapp/          FastAPIアプリ、同期ワーカー、インデクサー、OAuth
app/pixivapp/static/   JS、CSS、アイコン
app/pixivapp/templates Jinjaテンプレート
tests/                 pytest
setup_auth.py          CLI用OAuthフォールバック
compose.yml            sync + viewer
```

テストは一時的な `DATA_DIR` を使い、実際の認証情報には触れません。

## トラブルシューティング

### コールバックが白いページになる / codeが見つからない

正常です。pixivは `pixiv://` へリダイレクトするため、codeはアドレスバーに残りません。上記のとおりNetworkタブから取得してください。Networkの記録が空の場合は **Preserve log** を有効にしてログインURLを開き直してください（ログイン済みなら新しいcodeが発行されます）。

### `/data` に書き込めない

`PUID`/`PGID` を `PIXIV_DATA_DIR` の所有者に合わせ、書き込み権限を確認します。

```bash
id -u
id -g
sudo chown -R "$(id -u):$(id -g)" /path/to/pixiv-data
```

### アカウント追加後も `auth_required` になる

ビューワーとsyncのログを確認してください。codeの期限切れか、pixivがリフレッシュトークンを拒否したケースがほとんどです。再認証してください。

### レート制限 / R-18作品が取得できない

同期はもともと控えめな間隔で動作します。R-18の取得が不安定な場合は、任意で `secrets/cookies.txt`（Netscape形式）を置くとgallery-dlが読みます。アカウント別にする場合は `secrets/cookies_<user_id>.txt` を置くと優先されます。

## セキュリティ

- ビューワーのパスワードが唯一の入口です。強力なパスワードを設定し、localhostかTailscaleなどのプライベートネットワークにバインドしてください。
- `secrets/` にはアカウント全体にアクセスできるリフレッシュトークンがあります。`.env` と `secrets/` は絶対にコミットせず、他人と共有するバックアップにも含めないでください。
- テレメトリーは送信しません。
- 脆弱性の報告は [SECURITY.md](SECURITY.md) を参照してください。

## ライセンス

MIT — [LICENSE](LICENSE) を参照してください。

## 謝辞

- [gallery-dl](https://github.com/mikf/gallery-dl) — ダウンロードとpixiv OAuthフローの参考
- pixiv AndroidアプリのOAuthクライアント定数はgallery-dlでも使われている公開値です
- FastAPI、uvicorn、Pillow、Jinja2
