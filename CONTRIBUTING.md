# Contributing

Thanks for taking a look! Issues and pull requests are welcome.

## Before you start

- This project is a small, dependency-light stack. The viewer uses vanilla
  JavaScript with no build step; please keep it that way unless there is a
  strong reason not to.
- Do not commit `.env`, `secrets/`, `data/`, `images/`, `thumbs/`, `logs/`,
  `state/`, or backups. They are ignored by `.gitignore`; keep it that way.
- Never paste refresh tokens, cookies, viewer passwords, or callback URLs
  containing `code=` into an issue or PR.

## Development setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

Run the checks:

```bash
ruff check .
pytest -q
```

Build the image:

```bash
docker compose build
```

The tests use a temporary `DATA_DIR` and do not touch real credentials.

## Style

- Python: 4-space indentation, `ruff` with the repository configuration.
- JavaScript/CSS/HTML: match the existing style; no framework or bundler.
- UI strings are currently Japanese. Keep new user-facing text consistent.
- Keep commits focused and describe the user-visible change.

## Pull requests

Please include:

- what changed and why,
- how you tested it (commands or a short manual scenario),
- screenshots or a short clip for viewer changes when possible.

For OAuth changes, describe how you verified that no token is logged or
written with a permissive mode.
