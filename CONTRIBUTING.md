# Contributing to Codegenome

Thank you for your interest in contributing to [Codegenome](https://github.com/Ogro-Projukti/codegenome). This guide explains how to set up a development environment, run checks locally, and submit changes.

Codegenome is an open-source Python CLI that builds local codebase knowledge graphs and exposes them to AI agents via MCP. Contributions of all sizes are welcome—bug fixes, tests, documentation, new export formats, parser improvements, and MCP tooling.

## Table of contents

- [Ways to help](#ways-to-help)
- [Development setup](#development-setup)
- [Project layout](#project-layout)
- [Running tests](#running-tests)
- [Linting and formatting](#linting-and-formatting)
- [Manual verification](#manual-verification)
- [Making changes](#making-changes)
- [Submitting a pull request](#submitting-a-pull-request)
- [Reporting bugs and requesting features](#reporting-bugs-and-requesting-features)
- [Documentation](#documentation)
- [License](#license)

## Ways to help

You do not need to write code to contribute. Useful contributions include:

- **Bug reports** with clear reproduction steps and environment details
- **Documentation** fixes in `README.md`, `docs/`, or this file
- **Tests** for existing behavior or regressions
- **Parser and graph logic** in `src/codegenome/`
- **CLI and TUI** improvements
- **MCP server and installer** changes
- **Export formats** and graph visualization updates

Before starting large features, open a [GitHub issue](https://github.com/Ogro-Projukti/codegenome/issues) to discuss the approach and avoid duplicate work.

## Development setup

### Requirements

- **Python 3.11+** (see `requires-python` in `pyproject.toml`)
- **Git**
- A C compiler may be required on some platforms to build `python-igraph` / `leidenalg`

### Clone and install

From the repository root:

```bash
git clone https://github.com/Ogro-Projukti/codegenome.git
cd codegenome

python -m venv .venv
```

Activate the virtual environment:

```bash
# Windows (PowerShell)
.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Install the package in editable mode with development dependencies:

```bash
pip install -e ".[dev]"
```

Verify the install:

```bash
codegenome --help
python -c "import codegenome; print(codegenome.__version__)"
```

For more installation context (PyPI, MCP setup, troubleshooting), see [docs/installation.md](docs/installation.md).

## Project layout

```text
codegenome/
├── src/codegenome/     # Main Python package
│   ├── cli.py          # Modern Click CLI (`codegenome analyze`, `export`, `tui`, …)
│   ├── __main__.py     # Legacy flag-based CLI (`python -m codegenome --build`)
│   ├── parser.py       # tree-sitter parsing
│   ├── builder.py      # Graph construction
│   ├── mcp_server.py   # MCP server
│   └── …
├── tests/              # pytest test suite
├── docs/               # User-facing documentation
├── extensions/         # Cursor rules and Copilot templates
├── pyproject.toml      # Package metadata and tool config
└── build_cli.py        # Optional PyInstaller binary build
```

Codegenome exposes two CLI surfaces:

| Entry point | Example | Notes |
|-------------|---------|-------|
| `codegenome` | `codegenome analyze .` | Preferred for new work; subcommand-based |
| `python -m codegenome` | `python -m codegenome --workspace . --build` | Legacy flag-based interface; still supported |

When adding or changing CLI behavior, prefer extending the Click CLI in `cli.py` unless you are maintaining legacy compatibility in `__main__.py`.

## Running tests

All tests live under `tests/` and are configured in `pyproject.toml`.

Run the full suite:

```bash
pytest
```

Run a single file or test:

```bash
pytest tests/test_parser.py
pytest tests/test_parser.py::test_some_specific_case -v
```

Run with coverage:

```bash
pytest --cov=codegenome --cov-report=term-missing
```

Please add or update tests when you change behavior. The suite should pass before you open a pull request.

## Linting and formatting

This project uses [Ruff](https://docs.astral.sh/ruff/) (line length **100**, Python **3.11** target).

Check for issues:

```bash
ruff check src tests
```

Auto-fix safe issues:

```bash
ruff check src tests --fix
```

Keep new code consistent with surrounding modules. Avoid drive-by refactors in unrelated files.

## Manual verification

After functional changes, smoke-test the CLI against a small project directory:

```bash
# Build a graph
codegenome analyze .

# Export (requires a prior analyze)
codegenome export --format json --path .

# Optional: TUI or MCP (see docs/)
codegenome tui
```

Graph artifacts are written under `.genome/` in the analyzed workspace. See [docs/cli-reference.md](docs/cli-reference.md) for the full command reference.

### Optional: standalone binary

To build a PyInstaller binary (named `watcher` in `dist/`):

```bash
python build_cli.py
```

This requires the `dev` extra (`pyinstaller`).

## Making changes

1. **Fork** the repository on GitHub (or create a branch if you have write access).
2. **Create a feature branch** from `main`:

   ```bash
   git checkout -b your-topic-branch
   ```

3. **Make focused changes**—one logical change per pull request when possible.
4. **Update tests and docs** if behavior or public APIs change.
5. **Run checks locally**:

   ```bash
   pytest
   ruff check src tests
   ```

6. **Commit** with a clear message describing *why* the change was made.

If you change the package version, update `src/codegenome/version.py`, `pyproject.toml`, `CITATION.cff`, `CHANGELOG.md`, and any version assertions in tests (for example `tests/test_imports.py`).

## Submitting a pull request

1. Push your branch to your fork:

   ```bash
   git push -u origin your-topic-branch
   ```

2. Open a pull request against **`main`** on [Ogro-Projukti/codegenome](https://github.com/Ogro-Projukti/codegenome).

3. Fill in the PR description with:
   - **Summary** — what changed and why
   - **Test plan** — commands you ran (e.g. `pytest`, manual CLI steps)
   - **Related issues** — link with `Fixes #123` when applicable

4. Ensure CI checks pass (when available) and respond to review feedback.

We aim to review pull requests in a timely manner. Smaller, well-tested changes are easier to merge.

### Pull request checklist

- [ ] Tests pass locally (`pytest`)
- [ ] Ruff passes on touched code (`ruff check src tests`)
- [ ] New behavior has tests where practical
- [ ] User-facing changes are reflected in `README.md` or `docs/` if needed
- [ ] Commit messages and PR description explain the motivation

## Reporting bugs and requesting features

Use [GitHub Issues](https://github.com/Ogro-Projukti/codegenome/issues) and include as much detail as possible:

- **Environment** — OS, Python version, install method (`pip`, editable, PyPI)
- **Steps to reproduce** — exact commands and a minimal workspace if relevant
- **Expected vs actual behavior**
- **Logs or stack traces** — redact secrets and private paths

For MCP or client integration problems, also note which client (Cursor, Claude Desktop, etc.) and transport (`stdio` / HTTP).

## Documentation

When updating user-facing docs, use **`codegenome`** as the primary CLI name. Document legacy flag-based usage as `python -m codegenome --…`. The on-disk database file remains `.genome/watcher.db`.

| Document | Purpose |
|----------|---------|
| [README.md](README.md) | Overview and quick start |
| [docs/installation.md](docs/installation.md) | Install and MCP setup |
| [docs/cli-reference.md](docs/cli-reference.md) | Subcommands, legacy flags, workflows |
| [docs/mcp-integration.md](docs/mcp-integration.md) | MCP server and installer |
| [extensions/README.md](extensions/README.md) | Editor rules and templates |

Improvements to documentation are always appreciated and often the fastest way to help new users.

## License

By contributing to Codegenome, you agree that your contributions will be licensed under the [MIT License](LICENSE), the same license that covers the project.

---

Questions? Open an issue or start a discussion on the repository. We appreciate your help making Codegenome better for everyone building with AI-assisted development tools.
