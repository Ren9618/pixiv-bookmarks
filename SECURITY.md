# Security Policy

## Supported versions

The `main` branch is the supported version. Older commits may contain
unfixed issues.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Use GitHub's private vulnerability reporting on the repository's **Security**
tab, or contact the maintainer through GitHub. Include:

- a short description of the issue and its impact,
- steps to reproduce,
- the affected version/commit,
- any suggested fix.

Do not include real refresh tokens, cookies, `.env` values, or callback URLs
containing `code=` in the report. If a token may have leaked, revoke it by
re-authenticating that pixiv account and removing the old credential file.

## Sensitive data

`secrets/accounts/<user_id>.json` contains refresh tokens that grant full
access to the corresponding pixiv account. Treat the whole `secrets/`
directory as confidential. The viewer password, `.env`, cookies, and the
SQLite database can also contain private information.

The application does not send telemetry.
