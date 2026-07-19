# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and uses semantic versioning for published releases.

## [Unreleased]

Target release: 0.2.0.

### Added

- Click commands for workspace metrics, timeline history, snapshot changes, churn,
  and MCP client configuration.
- Full and multi-format analysis options covering all supported export formats.
- A tag-validated Trusted Publishing workflow for TestPyPI and PyPI.
- PEP 639 license metadata, a typed-package marker, and third-party notices.

### Changed

- `python -m codegenome` now invokes the same Click command group as the
  `codegenome` console script.
- Package metadata now uses `src/` discovery explicitly and reads the version
  from `codegenome.version`.
- Project URLs now point to the canonical `Ogro-Projukti/codegenome` repository.

### Removed

- The parallel top-level argparse interface and its legacy flag combinations.
  Use explicit subcommands such as `analyze`, `timeline`, `changes`, and `churn`.

## [0.1.4] - 2026-06-01

### Added

- **Copyable TUI console outputs** — users can select text in log panes and press `Ctrl+C` to copy it.
- **LAN live graph sharing** — `codegenome evolve --live --lan` exposes the live graph on a trusted local network.
- **TUI MCP HTTP mode controls** — separate local and LAN server actions.
- **Git-aware file filtering** — scanner support for `.gitignore`, `.genomeignore`, negation, and anchored patterns.
- **TUI workspace info and live-evolve controls**.
- **Live graph AI chat** with selectable context profiles.
- **MCP `query_graph` tool** and CLI transport/port options.
- **`pathspec` dependency** for gitignore-compatible matching.

### Changed

- Runtime artifacts and common generated directories are excluded from scans by default.
- MCP reads refresh to the latest timeline snapshot.
- Remote HTTP exposure requires explicit opt-in.
- Agent templates direct clients to native MCP tools.

### Fixed

- Graph intelligence filtering and MCP tool result quality.
- Release lint blockers and tree-sitter compatibility across supported Python versions.

### Documentation

- Added LAN, TUI, ignore-rule, and MCP transport guidance.
- Added `docs/release-0.1.4.md`.

[Unreleased]: https://github.com/Ogro-Projukti/codegenome/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/Ogro-Projukti/codegenome/releases/tag/v0.1.4
