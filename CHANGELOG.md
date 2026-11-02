# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Multi-tag filtering with an AND/OR match switch.
- Selection mode for adding works to collections, removing them, and deleting
  several local works at once.
- Work collections with create, rename, delete, selected-work add, tag-based
  bulk add, and collection filtering.
- Tag sets that save a tag combination and its AND/OR mode for reuse.
- Local deletion for single works and selections, with tombstones that keep
  deleted works out of later index and sync passes. pixiv bookmarks are not
  changed.
- Japanese/English UI with a persistent language switch on the viewer and
  login screen.
- English translations for sync statuses and OAuth errors.

### Changed

- Quieter, flatter dark theme with a solid pixiv-blue accent.
- Removed the top-left brand marks from the viewer and login screen, and
  replaced the logout glyph with an inline SVG that does not depend on system
  emoji fonts.
- Added primary navigation for All, Groups, Favorites, Search, and Settings.
  It appears on the side on desktop and at the bottom on mobile.
- On mobile, the header and bottom navigation hide while scrolling down and
  return when scrolling up or reaching the top of the page.

## [1.0.0] - 2026-11-03

### Added

- Multi-account support with one credential file per pixiv user.
- Add-account flow in the viewer using OAuth 2.0 + PKCE, including pending
  login URL reuse and clear Japanese error messages.
- CLI fallback (`setup_auth.py`) that shares the viewer's OAuth code.
- Per-account sync requests and sync status.
- Mobile tap zones: the left 40% of the lightbox goes back, the centre and
  right side advance.
- Search, tags, artists, account filter, R-18 toggle, local favorites,
  keyboard shortcuts, swipe navigation, and thumbnails.
- Docker Compose stack with generic `PIXIV_DATA_DIR`, `PUID`/`PGID`,
  `VIEWER_BIND`, and `VIEWER_PORT` settings.
- English and Japanese documentation, security policy, contribution guide,
  tests, and GitHub Actions CI.

### Security

- Credential files are written atomically with mode `0600`.
- The viewer warns when `VIEWER_PASSWORD` is empty or still `change-me`, and
  when `VIEWER_SECRET` is unset.
- No telemetry is sent.

[Unreleased]: https://github.com/Ren9618/pixiv-bookmarks/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Ren9618/pixiv-bookmarks/releases/tag/v1.0.0
