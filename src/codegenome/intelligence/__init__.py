"""Architectural intelligence analysis over CodeGenome dependency graphs.

This package decomposes the former monolithic ``intelligence`` module into
focused analyzers that share an :class:`AnalysisContext`:

- :mod:`~codegenome.intelligence.structural` - dead code, cycles, entry points, orphans
- :mod:`~codegenome.intelligence.rankings` - god nodes, complexity, churn
- :mod:`~codegenome.intelligence.coupling` - CBO/LCOM rankings and annotation
- :mod:`~codegenome.intelligence.classifier` - node role classification
- :mod:`~codegenome.intelligence.projections` - file-level graph projections

``GraphIntelligence`` remains the public facade with its original API.
"""

from codegenome.intelligence.report import (
    IntelligenceReport,
    report_from_dict,
    report_to_dict,
)
from codegenome.intelligence.pathutil import PathLike
from codegenome.intelligence.classifier import NodeClassifier
from codegenome.intelligence.projections import FileGraphProjector
from codegenome.intelligence.context import AnalysisContext
from codegenome.intelligence.engine import GraphIntelligence

__all__ = [
    "GraphIntelligence",
    "IntelligenceReport",
    "report_to_dict",
    "report_from_dict",
    "PathLike",
    "NodeClassifier",
    "FileGraphProjector",
    "AnalysisContext",
]
