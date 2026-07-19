# Third-party notices

CodeGenome's own source code is licensed under the MIT License in `LICENSE`.
Its required runtime dependency set includes separately licensed projects. In
particular:

| Dependency | Declared license | Use in CodeGenome |
|---|---|---|
| `python-igraph` / igraph | GNU GPL version 2 or later | Default in-process graph backend |
| `leidenalg` | GNU GPL version 3 | In-process Leiden community detection |

The authoritative copyright notices and license texts are distributed by those
projects and by their installed Python distributions:

- [python-igraph source and license](https://github.com/igraph/python-igraph)
- [igraph licensing documentation](https://igraph.org/python/versions/latest/)
- [leidenalg source and license](https://github.com/vtraag/leidenalg)

CodeGenome's wheel and source distribution declare these packages as
dependencies; they do not vendor their source or binaries. A standalone
PyInstaller executable does bundle them and therefore has materially different
distribution obligations. See `docs/license-compliance.md` before redistributing
CodeGenome or a bundled executable.

This notice is informational and is not legal advice. It does not replace the
license texts shipped by each dependency.
