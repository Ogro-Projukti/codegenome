# Phase 2 readiness record

This record maps the Phase 2 work to the Python packaging and PyPI production
standards checklist used for planning.

## Interface consolidation

| Check | Status | Evidence |
|---|---|---|
| One public CLI | Complete | `codegenome` and `python -m codegenome` invoke `codegenome.cli:cli` |
| Legacy feature parity | Complete | Full build, watch, live polling, all exports, metrics, timeline, changes, churn, and MCP installation are Click commands/options |
| Current user documentation | Complete | `docs/cli-reference.md`, installation, MCP, extensions, and README use the unified commands |
| Regression coverage | Complete | Module parity, version source, export choices, query commands, and MCP lifecycle validation are tested |

The argparse parsers remaining in `mcp_server.py`, `installer.py`, and
`build_cli.py` are low-level module/build adapters. They are no longer documented
as competing public front doors.

## Packaging checklist

| Gold-standard item | Status | Phase 2 result |
|---|---|---|
| `src/` layout | Complete | Explicit `package-dir`, discovery from `src`, tests outside the package, and no pytest source-path injection |
| One declared backend | Complete | Setuptools is explicit and requires the PEP 639-capable minimum version |
| Single version source | Complete | Package metadata reads `codegenome.version.__version__`; target version is 0.2.0 |
| Runtime/dev separation | Complete | Runtime and `dev` dependencies are separate in `pyproject.toml`; `requirements.txt` is only a constrained install shim |
| Typed-package marker | Complete | `py.typed` is included in the wheel |
| Cross-platform matrix | Complete | Python 3.11 and 3.13 on Linux, macOS, and Windows |
| Lint/test/coverage gates | Complete | Ruff, full pytest, and the coverage floor run in CI |
| README, LICENSE, changelog | Complete | All present; PEP 639 license files are included in distributions |
| Sdist and wheel verification | Complete | Build, Twine metadata check, clean install, CLI smoke, and package-data check |
| Trusted Publishing | Repository complete | Tag-only PyPI plus manual TestPyPI workflow; external publishers/environments still require owner setup |
| Vulnerability scanning | Complete | CI runs `pip-audit` against the constrained project resolution |
| SBOM and provenance | Complete | Release job archives a resolved CycloneDX SBOM; Trusted Publishing uploads attestations |
| Deprecation policy | Complete | Defined in `docs/releasing.md` |

## Deliberate release gates

These are not code defects and cannot be completed by a repository change alone:

- Repository owners must configure the `pypi` and `testpypi` Trusted Publishers
  and GitHub environments using `docs/releasing.md`.
- Maintainers must record a distribution-license decision for the in-process GPL
  graph dependencies before approving the production environment. See
  `docs/license-compliance.md`.

Static type checking and hosted versioned documentation remain useful follow-up
improvements, but are not part of the Phase 2 interface, `src/`, OIDC, or license
acceptance criteria.
