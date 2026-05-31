# Changelog

All notable changes to Codegenome are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4] - 2026-05-31

### Added

- **LAN live graph sharing** — `codegenome evolve --live --lan` binds HTTP and WebSocket to `0.0.0.0` so other devices on the same network can open the live graph. The CLI prints a shareable LAN URL (for example `http://192.168.1.42:8000/graph.html?live=1`).
- **Git-aware file filtering** — the scanner respects workspace `.gitignore` and `.genomeignore` files, including nested ignore files in subdirectories, negation rules (`!pattern`), and anchored patterns.
- **TUI workspace info page** — after setting a workspace, the TUI shows tracked folders, file extensions, and discovered `.gitignore` files before you run analyze or evolve.
- **TUI live-evolve controls** — buttons for **Live Evolve (Local)**, **Live Evolve (LAN)**, and **Quit** to start or stop background processes from the dashboard.
- **`pathspec` dependency** — powers gitignore-compatible pattern matching.

### Changed

- Default ignore list always excludes `.git/`, `.venv/`, `node_modules/`, `__pycache__/`, `*.pyc`, `.genome/`, and `.genomeignore` in addition to workspace ignore files.

### Documentation

- CLI reference covers `--lan`, TUI live modes, and ignore-rule behavior.
- README quick start includes the LAN evolve example.

[0.1.4]: https://github.com/Ogro-Projukti/codegenome/releases/tag/v0.1.4
