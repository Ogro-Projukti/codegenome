"""Pydantic schemas for progressive-disclosure genome REST endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from codegenome.serializers.nucleotide_mapper import (
    CallPayload,
    ImportPayload,
    NucleotideBase,
    SymbolPayload,
)


class ModuleSummary(BaseModel):
    """Top-level karyotype summary for one package module."""

    module_id: str
    gene_count: int = Field(ge=0, description="Number of source files (genes) in the module.")
    health_score: float = Field(ge=0.0, le=1.0)
    coverage_available: bool = False
    community_id: int | None = Field(
        default=None,
        description="Leiden community id this module predominantly belongs to.",
    )
    base_counts: dict[str, int] = Field(
        default_factory=dict,
        description="A/T/G/C nucleotide tallies (A, A*, T, G, C) for the module.",
    )


class GenomeSummaryResponse(BaseModel):
    """Lightweight genome overview for initial karyotype load."""

    modules: list[ModuleSummary]
    snapshot_id: int | None = None


class HelixNode(BaseModel):
    """One nucleotide in the dense helix node array."""

    index: int = Field(ge=0)
    file_path: str
    base: NucleotideBase
    line: int
    payload: SymbolPayload | ImportPayload | CallPayload


class HelixEdge(BaseModel):
    """Directed edge between helix node indices."""

    source: int = Field(ge=0)
    target: int = Field(ge=0)
    edge_type: Literal["calls", "imports", "contains", "inherits"]


class HelixGraphResponse(BaseModel):
    """Dense A/T/G/C payload for the helix renderer."""

    module_id: str
    nodes: list[HelixNode]
    edges: list[HelixEdge]
    health_score: float = Field(ge=0.0, le=1.0)
    coverage_available: bool = False
    alerts: list[str] = Field(default_factory=list)


class MethodNode(BaseModel):
    """Function or method inside a class or file."""

    name: str
    qualified_name: str
    kind: Literal["function", "method"]
    start_line: int
    end_line: int
    complexity: int | None = None


class ClassNode(BaseModel):
    """Class, abstract class, or interface with nested methods."""

    name: str
    qualified_name: str
    kind: Literal["class", "abstract_class", "interface"]
    start_line: int
    end_line: int
    complexity: int | None = None
    methods: list[MethodNode] = Field(default_factory=list)


class FileStructureNode(BaseModel):
    """One source file and its contained symbols."""

    path: str
    functions: list[MethodNode] = Field(default_factory=list)
    classes: list[ClassNode] = Field(default_factory=list)


class StructureTreeResponse(BaseModel):
    """Nested Package -> Files -> Classes -> Methods containment tree."""

    module_id: str
    package: str
    files: list[FileStructureNode]


class KaryotypeModuleUpdate(BaseModel):
    """Lightweight health/count patch for karyotype subscribers."""

    module_id: str
    gene_count: int = Field(ge=0)
    health_score: float = Field(ge=0.0, le=1.0)
    coverage_available: bool = False
    community_id: int | None = None
    base_counts: dict[str, int] = Field(default_factory=dict)


class KaryotypeUpdateMessage(BaseModel):
    """WebSocket payload for karyotype room subscribers."""

    type: Literal["karyotype_update"] = "karyotype_update"
    modules: list[KaryotypeModuleUpdate]
    snapshot_id: int | None = None


def helix_node_payload_dict(node: HelixNode) -> dict[str, Any]:
    """Serialize a helix node for JSON responses."""
    return node.model_dump(mode="json")
