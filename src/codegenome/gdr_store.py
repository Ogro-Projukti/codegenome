"""Snapshot-scoped persistence for the Global Dependency Registry (GDR)."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass

from codegenome.registry import GlobalDependencyRegistry, RegistryEntry

SCHEMA_VERSION = "3"
GDR_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gdr_files (
    snapshot_id   INTEGER NOT NULL,
    file_path     TEXT    NOT NULL,
    provides_json TEXT    NOT NULL,
    consumes_json TEXT    NOT NULL,
    updated_at    REAL    NOT NULL,
    PRIMARY KEY (snapshot_id, file_path),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gdr_provides (
    snapshot_id INTEGER NOT NULL,
    fqn         TEXT    NOT NULL,
    file_path   TEXT    NOT NULL,
    PRIMARY KEY (snapshot_id, fqn),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS gdr_consumes (
    snapshot_id INTEGER NOT NULL,
    fqn         TEXT    NOT NULL,
    file_path   TEXT    NOT NULL,
    PRIMARY KEY (snapshot_id, fqn, file_path),
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_gdr_consumes_lookup
    ON gdr_consumes (snapshot_id, fqn);

CREATE INDEX IF NOT EXISTS idx_gdr_provides_file
    ON gdr_provides (snapshot_id, file_path);

CREATE INDEX IF NOT EXISTS idx_gdr_consumes_file
    ON gdr_consumes (snapshot_id, file_path);

CREATE INDEX IF NOT EXISTS idx_gdr_files_snapshot
    ON gdr_files (snapshot_id);
"""


@dataclass(frozen=True)
class GDRFileEntry:
    """Provides and consumes for a single file at a snapshot."""

    file_path: str
    provides: frozenset[str]
    consumes: frozenset[str]


@dataclass(frozen=True)
class ChangeScope:
    """Files that must be resident for a surgical graph update."""

    changed: frozenset[str]
    dependents: frozenset[str]
    providers: frozenset[str]

    @property
    def all_files(self) -> frozenset[str]:
        return self.changed | self.dependents | self.providers


class GDRStore:
    """Persist and query snapshot-scoped GDR data in codegenome.db."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def initialize_schema(self) -> None:
        """Create GDR tables and schema metadata if missing."""
        self._conn.executescript(GDR_SCHEMA_SQL)
        self._conn.execute(
            """
            INSERT INTO schema_meta (key, value)
            VALUES ('timeline_schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (SCHEMA_VERSION,),
        )
        self._conn.commit()

    def has_snapshot(self, snapshot_id: int) -> bool:
        """Return True if GDR rows exist for the snapshot."""
        row = self._conn.execute(
            "SELECT 1 FROM gdr_files WHERE snapshot_id = ? LIMIT 1",
            (snapshot_id,),
        ).fetchone()
        return row is not None

    def persist_snapshot(
        self,
        snapshot_id: int,
        registry: GlobalDependencyRegistry,
        *,
        updated_at: float | None = None,
    ) -> None:
        """Write full GDR state for a snapshot from an in-memory registry."""
        timestamp = updated_at if updated_at is not None else time.time()
        file_rows: list[tuple[int, str, str, str, float]] = []
        provide_rows: list[tuple[int, str, str]] = []
        consume_rows: list[tuple[int, str, str]] = []

        for file_path, entry in registry.files.items():
            provides = sorted(entry.provides)
            consumes = sorted(entry.consumes)
            file_rows.append(
                (
                    snapshot_id,
                    file_path,
                    json.dumps(provides, sort_keys=True),
                    json.dumps(consumes, sort_keys=True),
                    timestamp,
                )
            )
            for fqn in provides:
                provide_rows.append((snapshot_id, fqn, file_path))
            for fqn in consumes:
                consume_rows.append((snapshot_id, fqn, file_path))

        self._conn.execute("DELETE FROM gdr_files WHERE snapshot_id = ?", (snapshot_id,))
        self._conn.execute("DELETE FROM gdr_provides WHERE snapshot_id = ?", (snapshot_id,))
        self._conn.execute("DELETE FROM gdr_consumes WHERE snapshot_id = ?", (snapshot_id,))

        if file_rows:
            self._conn.executemany(
                """
                INSERT INTO gdr_files (snapshot_id, file_path, provides_json, consumes_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                file_rows,
            )
        if provide_rows:
            self._conn.executemany(
                "INSERT INTO gdr_provides (snapshot_id, fqn, file_path) VALUES (?, ?, ?)",
                provide_rows,
            )
        if consume_rows:
            self._conn.executemany(
                "INSERT INTO gdr_consumes (snapshot_id, fqn, file_path) VALUES (?, ?, ?)",
                consume_rows,
            )
        self._conn.commit()

    def load_file(self, snapshot_id: int, file_path: str) -> GDRFileEntry | None:
        """Load provides/consumes for one file."""
        row = self._conn.execute(
            """
            SELECT provides_json, consumes_json
            FROM gdr_files
            WHERE snapshot_id = ? AND file_path = ?
            """,
            (snapshot_id, file_path),
        ).fetchone()
        if row is None:
            return None
        return GDRFileEntry(
            file_path=file_path,
            provides=frozenset(json.loads(row["provides_json"])),
            consumes=frozenset(json.loads(row["consumes_json"])),
        )

    def get_provider(self, snapshot_id: int, fqn: str) -> str | None:
        """Return the file path that provides an FQN at a snapshot."""
        row = self._conn.execute(
            "SELECT file_path FROM gdr_provides WHERE snapshot_id = ? AND fqn = ?",
            (snapshot_id, fqn),
        ).fetchone()
        return None if row is None else row["file_path"]

    def get_dependents(self, snapshot_id: int, fqn: str) -> set[str]:
        """Return file paths that consume an FQN at a snapshot."""
        rows = self._conn.execute(
            "SELECT file_path FROM gdr_consumes WHERE snapshot_id = ? AND fqn = ?",
            (snapshot_id, fqn),
        ).fetchall()
        return {row["file_path"] for row in rows}

    def resolve_change_scope(
        self,
        snapshot_id: int,
        *,
        changed_files: set[str],
        removed_fqns: set[str],
        new_consumes: dict[str, set[str]] | None = None,
    ) -> ChangeScope:
        """Compute the minimal file set needed for a surgical update."""
        dependents: set[str] = set()
        for fqn in removed_fqns:
            dependents.update(self.get_dependents(snapshot_id, fqn))

        providers: set[str] = set()
        consumes_by_file = new_consumes or {}
        for file_path in changed_files:
            consumes = consumes_by_file.get(file_path)
            if consumes is None:
                entry = self.load_file(snapshot_id, file_path)
                consumes = set(entry.consumes) if entry is not None else set()
            for consume_key in consumes:
                provider = self.get_provider(snapshot_id, consume_key)
                if provider:
                    providers.add(provider)

        return ChangeScope(
            changed=frozenset(changed_files),
            dependents=frozenset(dependents),
            providers=frozenset(providers),
        )

    def hydrate_registry(
        self,
        snapshot_id: int,
        file_paths: set[str] | None = None,
    ) -> GlobalDependencyRegistry:
        """Rebuild an in-memory registry from persisted GDR tables."""
        registry = GlobalDependencyRegistry()

        if file_paths is None:
            rows = self._conn.execute(
                """
                SELECT file_path, provides_json, consumes_json
                FROM gdr_files
                WHERE snapshot_id = ?
                ORDER BY file_path
                """,
                (snapshot_id,),
            ).fetchall()
        else:
            if not file_paths:
                return registry
            placeholders = ", ".join("?" for _ in file_paths)
            rows = self._conn.execute(
                f"""
                SELECT file_path, provides_json, consumes_json
                FROM gdr_files
                WHERE snapshot_id = ? AND file_path IN ({placeholders})
                ORDER BY file_path
                """,
                (snapshot_id, *sorted(file_paths)),
            ).fetchall()

        for row in rows:
            registry.files[row["file_path"]] = RegistryEntry(
                set(json.loads(row["provides_json"])),
                set(json.loads(row["consumes_json"])),
            )

        if file_paths is None:
            for row in self._conn.execute(
                "SELECT fqn, file_path FROM gdr_provides WHERE snapshot_id = ?",
                (snapshot_id,),
            ):
                registry.providers[row["fqn"]] = row["file_path"]
            for row in self._conn.execute(
                "SELECT fqn, file_path FROM gdr_consumes WHERE snapshot_id = ?",
                (snapshot_id,),
            ):
                registry.consumers.setdefault(row["fqn"], set()).add(row["file_path"])
            return registry

        referenced_fqns: set[str] = set()
        for entry in registry.files.values():
            referenced_fqns.update(entry.provides)
            referenced_fqns.update(entry.consumes)

        for fqn in referenced_fqns:
            provider = self.get_provider(snapshot_id, fqn)
            if provider is not None:
                registry.providers[fqn] = provider
            dependents = self.get_dependents(snapshot_id, fqn)
            if dependents:
                registry.consumers[fqn] = dependents

        return registry
