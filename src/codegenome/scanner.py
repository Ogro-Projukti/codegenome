"""Recursive workspace scanner with SHA256 fingerprinting and SQLite cache.

This module provides tools for efficiently scanning a workspace directory,
respecting ignore patterns, and tracking file additions, modifications,
and deletions using a SQLite-backed hash cache.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from codegenome.gitignore import DEFAULT_IGNORE_PATTERNS, IgnoreMatcher

__all__ = [
    "DEFAULT_IGNORE_PATTERNS",
    "FileRecord",
    "IgnoreMatcher",
    "ScanCache",
    "ScanResult",
    "WorkspaceScanner",
    "sha256_file",
]


@dataclass(frozen=True)
class FileRecord:
    """Metadata for a single scanned file.

    Attributes:
        path (str): Relative path to the file from the workspace root.
        absolute_path (str): Absolute path to the file.
        sha256 (str): SHA-256 hash of the file contents.
        size (int): File size in bytes.
        mtime (float): Last modification time.
    """

    path: str
    absolute_path: str
    sha256: str
    size: int
    mtime: float


@dataclass
class ScanResult:
    """Outcome of a workspace scan.

    Attributes:
        root (str): The root directory of the scan.
        files (list[FileRecord]): All files found during the scan.
        added (list[str]): Paths of newly added files.
        modified (list[str]): Paths of modified files.
        deleted (list[str]): Paths of deleted files.
        unchanged (list[str]): Paths of files that have not changed.
    """

    root: str
    files: list[FileRecord] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)


class ScanCache:
    """SQLite-backed cache of file fingerprints for incremental scans.

    Maintains a local SQLite database to store previously seen files and
    their SHA-256 hashes, sizes, and modification times.
    """

    def __init__(self, db_path: Path) -> None:
        """Initialize the ScanCache and connect to the SQLite database.

        Args:
            db_path (Path): Path to the SQLite database file.
        """
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS file_cache (
                path TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL,
                size INTEGER NOT NULL,
                mtime REAL NOT NULL
            )
            """
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def load_all(self) -> dict[str, FileRecord]:
        """Load all cached file records from the database.

        Returns:
            dict[str, FileRecord]: A mapping from file paths to FileRecord objects.
        """
        rows = self._conn.execute(
            "SELECT path, sha256, size, mtime FROM file_cache"
        ).fetchall()
        return {
            path: FileRecord(
                path=path,
                absolute_path="",
                sha256=sha256,
                size=size,
                mtime=mtime,
            )
            for path, sha256, size, mtime in rows
        }

    def upsert(self, record: FileRecord) -> None:
        """Insert or update a file record in the cache.

        Args:
            record (FileRecord): The file record to store.
        """
        self._conn.execute(
            """
            INSERT INTO file_cache (path, sha256, size, mtime)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                sha256=excluded.sha256,
                size=excluded.size,
                mtime=excluded.mtime
            """,
            (record.path, record.sha256, record.size, record.mtime),
        )

    def delete(self, path: str) -> None:
        """Delete a file record from the cache.

        Args:
            path (str): The relative path of the file to remove.
        """
        self._conn.execute("DELETE FROM file_cache WHERE path = ?", (path,))

    def commit(self) -> None:
        """Commit the current transaction to the database."""
        self._conn.commit()


def sha256_file(path: Path) -> str:
    """Compute the SHA-256 hash of a file.

    Args:
        path (Path): Path to the file.

    Returns:
        str: The hex-encoded SHA-256 digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class WorkspaceScanner:
    """Walk a workspace, hash files, and track changes incrementally.

    Uses IgnoreMatcher to skip unwanted files and ScanCache to quickly
    identify added, modified, or deleted files.
    """

    def __init__(
        self,
        root: Path | str,
        cache_db: Path | str | None = None,
    ) -> None:
        """Initialize the WorkspaceScanner.

        Args:
            root (Path | str): The workspace root directory.
            cache_db (Path | str | None): Path to the SQLite cache DB.
                If None, defaults to `.genome/scan_cache.db` in the workspace root.
        """
        self.root = Path(root).resolve()
        self.ignore = IgnoreMatcher.for_workspace(self.root)
        if cache_db is None:
            cache_db = self.root / ".genome" / "scan_cache.db"
        self.cache_path = Path(cache_db).resolve()
        self.cache = ScanCache(self.cache_path)
        self._register_cache_ignore()

    def _register_cache_ignore(self) -> None:
        try:
            rel_cache = self.cache_path.relative_to(self.root).as_posix()
        except ValueError:
            return
        if rel_cache:
            self.ignore.add_pattern(rel_cache)

    def scan(
        self,
        incremental: bool = True,
        *,
        on_progress: Callable[[int], None] | None = None,
        progress_interval: int = 100,
    ) -> ScanResult:
        """Perform a workspace scan and compare against the cache.

        Args:
            incremental (bool): If True, compare against previous cache state.
                If False, ignore previous state and treat all files as added.
            on_progress (Callable[[int], None] | None): Optional callback invoked
                periodically with the number of files scanned so far.
            progress_interval (int): Minimum file count between progress callbacks.

        Returns:
            ScanResult: The result of the scan including added, modified,
                deleted, and unchanged files.
        """
        result = ScanResult(root=str(self.root))
        previous = self.cache.load_all() if incremental else {}
        seen: set[str] = set()
        scanned = 0

        if not self.root.is_dir():
            self.cache.commit()
            return result

        for dirpath, dirnames, filenames in os.walk(self.root):
            current = Path(dirpath)
            rel_dir = current.relative_to(self.root).as_posix()
            if rel_dir == ".":
                rel_dir = ""

            dirnames[:] = [
                name
                for name in dirnames
                if not self.ignore.is_ignored(
                    f"{rel_dir}/{name}".strip("/"), is_dir=True
                )
            ]

            for filename in filenames:
                rel_path = f"{rel_dir}/{filename}".strip("/") if rel_dir else filename
                if self.ignore.is_ignored(rel_path):
                    continue

                abs_path = current / filename
                try:
                    stat = abs_path.stat()
                    digest = sha256_file(abs_path)
                except OSError:
                    continue

                record = FileRecord(
                    path=rel_path,
                    absolute_path=str(abs_path),
                    sha256=digest,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                )
                result.files.append(record)
                seen.add(rel_path)
                scanned += 1
                if on_progress is not None and (
                    scanned == 1 or scanned % progress_interval == 0
                ):
                    on_progress(scanned)

                prev = previous.get(rel_path)
                if prev is None:
                    result.added.append(rel_path)
                elif prev.sha256 != digest:
                    result.modified.append(rel_path)
                else:
                    result.unchanged.append(rel_path)

                self.cache.upsert(record)

        for path in sorted(set(previous) - seen):
            result.deleted.append(path)
            self.cache.delete(path)

        if on_progress is not None and scanned > 0 and scanned % progress_interval != 0:
            on_progress(scanned)

        self.cache.commit()
        return result
