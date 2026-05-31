# Release 0.1.4 (draft)

> Final publish steps (tag, PyPI, GitHub Release) are pending further work.

## Highlights

- **LAN live graph** — share the evolving graph with devices on the same network
- **Ignore rules** — scans respect `.gitignore` and `.genomeignore`
- **TUI** — workspace info view and buttons for local/LAN live evolve

## CLI

```bash
# LAN live graph
codegenome evolve --live --lan .

# TUI
codegenome tui
```

## Upgrade

```bash
pip install --upgrade codegenome
python -c "import codegenome; print(codegenome.__version__)"
```

## Checklist before publishing

- [ ] Remaining features merged
- [ ] Tests pass (`pytest`)
- [ ] Version bumped in `pyproject.toml` and `src/codegenome/version.py`
- [ ] Tag `v0.1.4` and create GitHub Release
- [ ] Publish to PyPI
