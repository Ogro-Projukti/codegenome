# Dependencies

> **TL;DR:** Runtime dependencies fit the architecture, but `pyproject.toml` and `requirements.txt` are incompatible sources of truth and neither is a reproducible lock. The requirements resolution selected 11 known advisory records, while installed GPL graph packages also require a deliberate distribution-license review for this MIT project.

## Direct dependency inventory

| Group | Direct packages | Version policy |
|---|---|---|
| Parsing | `tree-sitter` and Python/JavaScript/TypeScript/Go/Rust grammar packages | environment markers; exact 0.21.x below Python 3.12, `>=0.23,<0.26` otherwise (`pyproject.toml:26-38`) |
| Watch/API | `watchdog`, `fastmcp`, `websockets` | unbounded in package metadata; bounded in requirements |
| Graph | `leidenalg`, `python-igraph`, `networkx` | first two unbounded in package metadata; NetworkX `>=3.2,<4` |
| UI/templates | `click`, `jinja2`, `textual` | unbounded in package metadata |
| Models/files | `pydantic>=2,<3`, `pathspec>=0.12,<2` | bounded |
| Development | `pytest`, `pytest-cov`, `ruff`, `pyinstaller>=6,<7` | three unbounded in optional extras (`pyproject.toml:52-53`) |

## Manifest inconsistency

`requirements.txt:13-24` bounds most dependencies and includes pytest/coverage/Ruff, but it omits direct runtime dependencies `click` and `pydantic`. Conversely, `pyproject.toml:39-46` leaves watchdog, FastMCP, Leiden, igraph, Click, Jinja, WebSockets, and Textual unbounded.

This is not cosmetic: the project environment contained FastMCP 3.4.2 and WebSockets 16 under package metadata, while isolated resolution of `requirements.txt` selected FastMCP 2.12.5 and WebSockets `<15`. Features and security posture therefore depend on installation route. **Severity: high; confidence: high.**

Recommended policy:

1. make `pyproject.toml` the single declared dependency source;
2. generate a hashed constraints/lock artifact per supported Python range for reproducible CI/releases;
3. keep runtime and development groups separate;
4. test minimum and latest allowed dependencies;
5. add `pytest-asyncio` explicitly because three tests require it (`tests/test_live_server.py:39`, `:56`, `:102`).

## Vulnerability audit

An isolated `pip-audit -r requirements.txt` run on 2026-07-20 reported 11 advisory records across three resolved packages. This is resolution evidence, not proof that every deployed install contains those exact versions; the current project environment had FastMCP 3.4.2, MCP 1.27.2, and pytest 9.0.3.

| Resolved package | Advisory themes | Fixed versions reported by advisory/audit | Relevance |
|---|---|---|---|
| FastMCP 2.12.5 | Windows command injection, reflected XSS, OAuth proxy consent/token weaknesses | 2.13.0, 2.14.0/2.14.2, or 3.2.0 depending on issue | Several fixes conflict with `<3` or require newer 2.x |
| MCP 1.16.0 | DNS rebinding/local HTTP, session principal verification, WebSocket host/origin | 1.23.0, 1.27.2, 1.28.1 | Directly relevant to unauthenticated local network servers |
| pytest 8.4.2 | unsafe temporary-directory handling on Unix | 9.0.3 | Development/CI exposure |

Primary advisory references: [FastMCP command injection](https://osv.dev/vulnerability/PYSEC-2026-1365), [FastMCP XSS](https://osv.dev/vulnerability/PYSEC-2026-1364), [OAuth token reuse](https://osv.dev/vulnerability/PYSEC-2026-2474), [CLI command injection](https://osv.dev/vulnerability/PYSEC-2026-2475), [OAuth consent bypass](https://osv.dev/vulnerability/PYSEC-2026-2476), [MCP DNS rebinding](https://osv.dev/vulnerability/PYSEC-2026-1617), [MCP principal verification](https://osv.dev/vulnerability/CVE-2026-52869), [MCP WebSocket validation](https://osv.dev/vulnerability/CVE-2026-59950), and [pytest temporary-directory issue](https://osv.dev/vulnerability/PYSEC-2026-1845).

**Action:** reconcile manifests first, then upgrade/verify the chosen resolution. At minimum, use a FastMCP release containing all relevant fixes, MCP `>=1.28.1`, and pytest `>=9.0.3`, subject to compatibility testing and the project’s Python support policy.

## Integrity, automation, and provenance

- `pip check` in the existing project environment found no broken installed requirements.
- There is no lockfile for Python, Dependabot/Renovate configuration, dependency-review workflow, SBOM, signing/provenance setup, or automated `pip-audit` gate.
- `package-lock.json:1-6` contains no packages and does not provide useful provenance for browser assets.
- Package URLs in `pyproject.toml:55-59` name a different GitHub owner than the actual remote; release metadata should be corrected before publishing.

## License inventory and compatibility signal

Installed metadata reported MIT/BSD/Apache/MPL licensing for most direct dependencies. `leidenalg` reports GPL-3.0-or-later and `python-igraph` reports GNU GPL; the project itself declares MIT (`pyproject.toml:10`, `LICENSE`).

**Judgment, not legal advice:** importing/distributing GPL libraries with a bundled executable or binary distribution may create copyleft obligations that are not captured by an MIT-only notice. Have release counsel/maintainers decide whether source distribution, dynamic dependency installation, notices, or dependency substitution meets the intended distribution model. **Confidence: high** that review is required; no legal compatibility conclusion is asserted.

## Maintenance recommendations

- Add a scheduled and pull-request dependency audit with an explicit triage/SLA policy.
- Produce CycloneDX/SPDX SBOMs for published artifacts.
- Test Python 3.11–3.13 with both lower bounds and locked release bounds; current local Python 3.14 is outside the declared classifier set (`pyproject.toml:19-22`).
- Record dependency rationale and removal candidates; NetworkX plus igraph is justified by adapters, but dual backends expand semantic test obligations.
