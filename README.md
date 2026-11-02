# Pixiv Bookmarks

A self-hosted, multi-account pixiv bookmark downloader and web viewer.

[日本語版 README はこちら](README.ja.md)

[![CI](https://github.com/Ren9618/pixiv-bookmarks/actions/workflows/ci.yml/badge.svg)](https://github.com/Ren9618/pixiv-bookmarks/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> This is an unofficial project. It is not affiliated with pixiv. Use it at
> your own risk, respect pixiv's terms of service, and keep the request rate
> reasonable.

## Features

- Download **public and private** bookmarks for one or more pixiv accounts.
- Incremental sync every 15 minutes, plus manual and full resync from the UI.
- Add additional accounts from the viewer with OAuth + PKCE — no SSH or
  browser automation required.
- FastAPI viewer with a Japanese/English UI, search, multi-tag filters
  (AND/OR), artists, account filter, R-18 toggle, local favorites, lightbox,
  keyboard shortcuts, swipe and tap navigation.
- Work collections and saved tag sets for organizing local views, plus a
  selection mode for adding, removing, or deleting several works at once.
- Local deletion of individual or selected works. Tombstones keep deleted
  works out of later index and sync passes without changing pixiv bookmarks.
- Primary navigation on the side for desktop and at the bottom for mobile,
  with All, Groups, Favorites, Search, and Settings.
- SQLite index, on-demand thumbnails, and a responsive PWA manifest.
- Docker Compose stack; all data stays on your own disk.

The viewer and login screen are available in Japanese and English. Use the
**EN/日本語** button in the header (or on the login screen) to switch; the choice
is saved in the browser.

## Architecture

```text
┌──────────────────────────────┐
│ pixiv-sync                   │
│  gallery-dl + pixiv API      │
└──────────────┬───────────────┘
               │ writes
               ▼
     /data/images/          media files
     /data/state/gallery.db SQLite index
     /data/secrets/         OAuth refresh tokens (0600)
               ▲
               │ reads + writes state/sync.request
┌──────────────┴───────────────┐
│ pixiv-viewer                 │
│  FastAPI + vanilla JS        │
└──────────────────────────────┘
```

- **sync** downloads bookmarks with
  [gallery-dl](https://github.com/mikf/gallery-dl) and stores the exact
  bookmark order through the pixiv API.
- **viewer** serves the gallery, adds accounts, and queues on-demand syncs.
- Credentials live in `secrets/accounts/<user_id>.json` with mode `0600`.

## Requirements

- Docker Engine with Compose v2
- A pixiv account
- Python 3.10 or newer (3.12 recommended) for the CLI fallback and tests
- Linux is recommended for bind mounts and file ownership. Docker Desktop on
  macOS/Windows also works, but `PUID`/`PGID` are ignored differently.

## Quick start

```bash
git clone https://github.com/Ren9618/pixiv-bookmarks.git
cd pixiv-bookmarks
cp .env.example .env
```

Edit `.env` at minimum:

```dotenv
VIEWER_PASSWORD=your-password
VIEWER_SECRET=<openssl rand -hex 32>
PIXIV_DATA_DIR=/absolute/path/to/pixiv-data
PUID=1000
PGID=1000
```

`PUID`/`PGID` must be able to write to `PIXIV_DATA_DIR` (check with `id -u`
and `id -g`). Then start the stack:

```bash
docker compose up -d --build
```

Open <http://127.0.0.1:8899>.

To access the viewer from another device, set `VIEWER_BIND=0.0.0.0` (LAN or
Tailscale) or point a reverse proxy / `tailscale serve` at
`127.0.0.1:8899`. Keep `VIEWER_PASSWORD` set whenever the port is reachable
from another machine.

The first sync starts automatically after an account is added and can take a
while for large bookmark collections.

## Adding a pixiv account

pixiv requires an OAuth refresh token for API access. Cookies alone are not
enough for gallery-dl's API authentication.

### From the viewer (recommended)

1. Open the viewer → **Sync status** → **+ Add pixiv account**.
2. Press **Generate login URL** and open the displayed link.
3. **Before logging in**, open DevTools (`F12`, or `⌘⌥I` on macOS) →
   **Network** and enable **Preserve log**.
4. Log in with the account you want to add. A white page or a `pixiv://`
   redirect is expected.
5. In the Network list, right-click the `callback?…code=…` request →
   **Copy link address** (Firefox: **Copy URL**).
6. Paste it into the viewer and press **Add this account**.

The authorization code is valid for only a short time, so paste it
immediately after logging in.

Why DevTools? pixiv redirects to the native app (`pixiv://`) after the
callback, so the code never appears in the address bar. The callback request
is the reliable place to read it. The viewer exchanges the code server-side
and stores the refresh token at `0600`. Existing accounts are never replaced
unless you authenticate the same pixiv user again.

### From the CLI (fallback)

```bash
python3 setup_auth.py init
# open the printed URL, log in, copy the callback URL/code
python3 setup_auth.py exchange --code '<callback URL or code>'
python3 setup_auth.py status
python3 setup_auth.py remove --user-id 123456
```

`setup_auth.py` reads `PIXIV_DATA_DIR` from `.env`. Use
`--data-dir /path/to/data` to override it. `exchange --code -` reads the code
from stdin.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `PIXIV_DATA_DIR` | `./data` | Host directory mounted at `/data`. |
| `PUID` / `PGID` | `1000` | UID/GID used by both containers. |
| `VIEWER_BIND` | `127.0.0.1` | Host interface for the viewer. |
| `VIEWER_PORT` | `8899` | Host port for the viewer. |
| `VIEWER_PASSWORD` | empty | Viewer password. Empty disables auth. |
| `VIEWER_SECRET` | random | Session signing key. Set it to keep sessions across restarts. |
| `SYNC_INTERVAL_MINUTES` | `15` | Automatic sync interval. |
| `TZ` | `Asia/Tokyo` | Timezone for logs and timestamps. |

Data layout inside `PIXIV_DATA_DIR`:

```text
images/<artist_id> <artist_account>/<work_id>_p00.jpg
state/gallery.db       SQLite index, favorites, collections, tag sets, tombstones
state/status.json      last sync status
state/sync.request     on-demand sync queue
secrets/accounts/      OAuth tokens (0600)
thumbs/                generated thumbnails
logs/sync.log          rotated sync log
```

## Viewer controls

- **Tap the left 40%** of the image to go back, **tap the right side or
  centre** to advance.
- Swipe left/right to move between works, swipe down to close.
- `←` / `→` to move, `Esc` to close.
- Account selector, multiple tags with an AND/OR match switch, artists, R-18
  toggle, and local favorites in the toolbar.
- **Selection** selects loaded works for collection changes or local deletion.
  **Select all loaded** only covers works currently loaded in the grid.
- **Groups** manages work collections and tag sets. Collections can be
  created, renamed, deleted, filled from selected works, filled from tags, or
  shown as a filter. Deleting a collection keeps the works themselves.
  Tag-based bulk add searches all indexed works, regardless of the current
  account, collection, or R-18 filter.
- Tag sets save the current tags and AND/OR mode. Applying one restores that
  combination, together with any active collection filter.
- **Local delete** is available in the lightbox and for selected works. It
  removes the database row and attempts to remove media, sidecars, archives,
  and thumbnails. pixiv bookmarks are not changed.
- **Navigation** sits on the left on desktop and at the bottom on mobile, with
  All, Groups, Favorites, Search, and Settings. On mobile, scrolling down hides
  the header and bottom navigation; scrolling up or returning to the top shows
  them again.
- Sync status shows per-account counts, last sync, errors, and per-account
  sync buttons.

### Local deletion

Deletion records a tombstone in `state/gallery.db`, so a later index or sync
pass removes the work again instead of restoring it. A full resync can
re-download an archived work before the next indexing pass; the tombstone then
removes it and its files. File removal errors are logged, and the pixiv side
is never modified.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

ruff check .
pytest -q
docker compose build
```

Project layout:

```text
app/pixivapp/          FastAPI app, sync worker, indexer, OAuth
app/pixivapp/static/   vanilla JS, CSS, icons
app/pixivapp/templates Jinja templates
tests/                 pytest suite
setup_auth.py          CLI fallback for OAuth
compose.yml            sync + viewer stack
```

Tests use a temporary `DATA_DIR` and never touch real credentials.

## Troubleshooting

### The callback page is white / the code is missing

That is expected. pixiv redirects to `pixiv://`; read the code from the
Network tab as described above. If the Network log is empty, enable
**Preserve log** and open the login URL again (a logged-in browser issues a
new code).

### `permission denied` writing to `/data`

Set `PUID`/`PGID` to the owner of `PIXIV_DATA_DIR` and make sure the directory
is writable:

```bash
id -u
id -g
sudo chown -R "$(id -u):$(id -g)" /path/to/pixiv-data
```

### `auth_required` after adding an account

Check the viewer/sync logs. The most common cause is an expired authorization
code or a refresh token that pixiv rejected. Re-authenticate the account.

### Rate limits or missing R-18 works

The sync already uses conservative delays. If R-18 retrieval is unstable, you
can optionally place a Netscape-format cookie file at
`secrets/cookies.txt`; per-account cookies can be placed at
`secrets/cookies_<user_id>.txt` and take precedence.

## Security

- The viewer password is the only gate. Use a strong password and bind to
  localhost or a private network such as Tailscale.
- `secrets/` contains refresh tokens that grant full account access. Never
  commit `.env` or `secrets/`, and exclude them from backups shared with
  others.
- The app does not send telemetry.
- To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Support

This project is free and maintained by a single developer. If it is useful to
you, donations toward continued development and server costs are appreciated:

- [Stripe donation page](https://buy.stripe.com/5kQ9AU8Xva8T7tAbnj67S00)
  (one-time, any amount from ¥100)

Donations are voluntary and do not entitle the donor to features or support.

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

- [gallery-dl](https://github.com/mikf/gallery-dl) for downloading and the
  pixiv OAuth flow reference.
- The pixiv Android OAuth client constants are the public values also used by
  gallery-dl.
- FastAPI, uvicorn, Pillow, and Jinja2.
