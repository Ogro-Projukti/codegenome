"""Graph statistics dataclass and export-format constants."""

from __future__ import annotations

from dataclasses import dataclass, field

SUPPORTED_FORMATS = frozenset(
    {"json", "html", "graphml", "cypher", "markdown", "obsidian"}
)


@dataclass(frozen=True)
class GraphStatistics:
    """High-level graph metrics for reports and exports.

    Attributes:
        node_count (int): Total number of nodes in the graph.
        edge_count (int): Total number of edges in the graph.
        file_count (int): Number of nodes representing files.
        symbol_count (int): Number of nodes representing symbols.
        import_count (int): Number of nodes representing imports.
        external_count (int): Number of external nodes.
        community_count (int): Number of detected communities.
        bridge_count (int): Number of bridge nodes connecting communities.
        languages (dict[str, int]): Distribution of programming languages among files.
    """

    node_count: int
    edge_count: int
    file_count: int
    symbol_count: int
    import_count: int
    external_count: int
    community_count: int
    bridge_count: int
    languages: dict[str, int] = field(default_factory=dict)
