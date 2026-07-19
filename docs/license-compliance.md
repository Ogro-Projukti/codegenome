# License compliance review

Status: **maintainer decision required before the first production PyPI release**.
This review is an engineering inventory, not legal advice.

## Finding

CodeGenome's original source is MIT-licensed. Two required graph dependencies
are GPL-licensed:

| Component | Evidence | Integration boundary |
|---|---|---|
| CodeGenome | `LICENSE`; `project.license = "MIT"` | Original project source |
| `python-igraph` / igraph | Project documentation states GPL 2 or later | Imported directly by `graph_api.py`; default graph backend |
| `leidenalg` | Project license is GPL version 3 | Imported directly by `clusterer.py`; runs in the same process |

This is not a mere unused or development-only dependency. The default builder,
timeline, graph store, working set, health aggregation, and clustering paths use
igraph objects, and community detection calls Leiden directly. The standalone
binary build also explicitly collects both packages.

The Free Software Foundation's GPL FAQ treats modules designed to link and share
data structures in one process as a combined program. Whether and how that view
applies to this distribution is a legal conclusion for the maintainers or
counsel, not for this engineering review.

## Distribution scenarios

### Repository, source distribution, and wheel

The CodeGenome sdist and wheel contain MIT-licensed CodeGenome source and declare
the GPL packages as external runtime dependencies. They do not vendor igraph or
Leiden binaries. Installing and running the declared dependencies nevertheless
creates a tightly integrated runtime, so the MIT metadata must not be presented
as a conclusion that the full runtime has no GPL obligations.

### Standalone executable

`build_cli.py` collects igraph and Leiden into a PyInstaller application. Do not
publish or attach that executable to a public release until maintainers have
chosen a GPL-compliant distribution approach and assembled the corresponding
source, notices, and any other required materials.

### Internal use

Private use is distinct from redistribution, but the exact facts still matter.
Anyone redistributing the application, an environment image, or a bundled binary
must repeat the review for that artifact.

## Required release decision

Before approving the protected `pypi` GitHub environment, record one of these
decisions in a release issue or ADR:

1. distribute the combined runtime under terms confirmed to satisfy the relevant
   GPL versions while preserving MIT notices for CodeGenome's original files;
2. replace the GPL graph stack with permissively licensed implementations;
3. isolate GPL programs across a boundary that qualified counsel accepts as
   separate works; or
4. obtain a written compatibility determination for the intended sdist/wheel
   distribution.

Do not infer that removing dependency binaries from the wheel alone resolves the
question, and do not change CodeGenome's license without authorization from all
relevant copyright holders.

## Controls implemented in Phase 2

- PEP 639 metadata identifies CodeGenome's source license as MIT and includes
  `LICENSE` plus `THIRD_PARTY_NOTICES.md` in distributions.
- Production publishing uses the protected `pypi` environment, which must require
  maintainer approval.
- The publish workflow creates only an sdist and wheel; it does not build or
  upload the PyInstaller executable.
- Trusted Publishing uses short-lived OIDC credentials and enables PyPI artifact
  attestations.
- The release workflow generates a CycloneDX JSON SBOM from a clean environment
  containing the built wheel and its resolved runtime dependencies.

## Release checklist

- [ ] Confirm the dependency versions and license metadata in the release lock.
- [ ] Review and archive the generated `sbom/codegenome.cdx.json` workflow artifact.
- [ ] Review any newly added or relicensed transitive dependency.
- [ ] Record the maintainer/legal decision for igraph and Leiden.
- [ ] Verify `LICENSE` and `THIRD_PARTY_NOTICES.md` exist in both sdist and wheel.
- [ ] Confirm no standalone binary is attached without a separate compliance package.

## Primary references

- [python-igraph licensing](https://igraph.org/python/versions/latest/)
- [leidenalg repository](https://github.com/vtraag/leidenalg)
- [GNU GPL FAQ on combining works](https://www.gnu.org/licenses/gpl-faq.en.html)
- [PyPA licensing metadata guidance](https://packaging.python.org/en/latest/guides/licensing-examples-and-user-scenarios/)
