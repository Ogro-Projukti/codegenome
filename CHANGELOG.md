# Changelog

## [0.1.4] - 2026-05-31

### Added

- LAN live graph sharing via `codegenome evolve --live --lan`
- Git-aware scanning (`.gitignore`, `.genomeignore`, nested rules)
- TUI workspace info page and Live Evolve (Local / LAN) controls

### Changed

- Scanner skips default paths (`.git/`, `.venv/`, `node_modules/`, etc.) plus workspace ignore files
