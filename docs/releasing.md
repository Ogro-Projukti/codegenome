# Release and PyPI publishing

CodeGenome publishes an sdist and wheel through GitHub Actions using PyPI
Trusted Publishing. The workflow does not use repository API-token secrets.

## One-time Trusted Publisher configuration

Create pending publishers on both indexes with these exact identities:

| Field | PyPI | TestPyPI |
|---|---|---|
| Project | `codegenome` | `codegenome` |
| Owner | `Ogro-Projukti` | `Ogro-Projukti` |
| Repository | `codegenome` | `codegenome` |
| Workflow | `publish.yml` | `publish.yml` |
| Environment | `pypi` | `testpypi` |

Configure the GitHub `pypi` environment with required reviewers. Approval is the
production release gate, including the unresolved decision in
[License compliance](license-compliance.md). TestPyPI may remain approval-free.
Remove and revoke any obsolete `PYPI_API_TOKEN` or `TEST_PYPI_API_TOKEN` secrets.

## TestPyPI rehearsal

1. Run the **Publish Python distributions** workflow manually.
2. The build job runs Ruff and pytest, builds both formats, validates metadata,
   installs the wheel outside the source tree, checks both CLI entry points, and
   generates a CycloneDX SBOM from a clean resolved runtime environment.
3. The `testpypi` job publishes the verified artifacts with OIDC and attestations.
4. Install from TestPyPI in a clean environment and run `codegenome --help`.

## Production release

1. Complete the license checklist and obtain approval for the `pypi` environment.
2. Update `src/codegenome/version.py` and convert the changelog's Unreleased
   section to the matching version and release date in a reviewed commit.
3. Create and push the matching tag, for example `v0.2.0`.
4. The workflow rejects a tag that does not exactly match installed package metadata.
5. After publication, install the version from PyPI in a clean environment and
   verify `codegenome --version`, `python -m codegenome --help`, and a small analysis.

Only the publish jobs receive `id-token: write`; the build and test job cannot
request a publishing credential. PyPI's publishing action produces PEP 740
artifact attestations by default, and the workflow leaves that behavior enabled.

## Versioning and deprecation policy

CodeGenome uses semantic versioning. While the project is below 1.0, incompatible
CLI changes require a minor-version bump and must be recorded in the changelog.
After 1.0, a public command or option is deprecated for at least one minor release
before removal unless retaining it would create an active security risk.

The old top-level argparse flags are removed in 0.2.0 because they were an alpha
interface that conflicted with the documented Click commands. Their capabilities
now live under explicit subcommands; see [CLI reference](cli-reference.md).

## References

- [PyPA Trusted Publishing workflow guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
- [PyPI Trusted Publishers](https://docs.pypi.org/trusted-publishers/)
- [PyPA `src/` layout rationale](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/)
