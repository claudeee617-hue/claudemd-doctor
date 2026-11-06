# Changelog

All notable changes to this project are documented here.

## [0.1.1] - 2026-11-06

### Fixed
- `stale-path`: Windows-style paths (`src\utils\helpers.ts`) are now normalized to `/` before
  the check, so backslash paths are caught like forward-slash ones.

## [0.1.0] - 2026-11-06

### Added
- `generate`: scan a repo (Node, Python, Make, Rust, Go, PlatformIO) and write a lean starter `CLAUDE.md`.
- `lint`: check an existing `CLAUDE.md` against the real repo.
- Rules: `secret`, `stale-command`, `stale-path`, `too-long`, `vague-rule`, `no-commands`,
  `no-headings`, `shouting`, `style-in-claude-md`, `duplicate`, `placeholder`.
- 0-100 score, `--fail-under`, `--format json`, CI-friendly exit codes.
- Reusable GitHub Action (`action.yml`).
