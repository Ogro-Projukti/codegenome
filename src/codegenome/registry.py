"""Global Dependency Registry for tracking O(1) cross-module graph relationships."""

from dataclasses import dataclass, field
from typing import Dict, Set, List


@dataclass
class RegistryEntry:
    """Provides and Consumes sets for a single file."""
    provides: Set[str] = field(default_factory=set)
    consumes: Set[str] = field(default_factory=set)


class GlobalDependencyRegistry:
    """In-memory index for resolving cross-module dependencies in O(1) time."""

    def __init__(self) -> None:
        self.files: Dict[str, RegistryEntry] = {}
        self.providers: Dict[str, str] = {}
        self.consumers: Dict[str, Set[str]] = {}

    def update_file(self, file_path: str, provides: Set[str], consumes: Set[str]) -> List[str]:
        """Update the index for a file and return any FQNs that were deleted."""
        old_entry = self.files.get(file_path, RegistryEntry())
        
        removed_fqns = []
        for fqn in old_entry.provides - provides:
            if self.providers.get(fqn) == file_path:
                del self.providers[fqn]
                removed_fqns.append(fqn)
                
        for fqn in provides:
            self.providers[fqn] = file_path
            
        for fqn in old_entry.consumes - consumes:
            if fqn in self.consumers:
                self.consumers[fqn].discard(file_path)
                if not self.consumers[fqn]:
                    del self.consumers[fqn]
                
        for fqn in consumes:
            if fqn not in self.consumers:
                self.consumers[fqn] = set()
            self.consumers[fqn].add(file_path)
            
        self.files[file_path] = RegistryEntry(provides, consumes)
        return removed_fqns

    def get_dependents(self, fqn: str) -> Set[str]:
        """Return file paths that consume a specific FQN."""
        return self.consumers.get(fqn, set())

    def get_provider(self, fqn: str) -> str | None:
        """Return the file path that provides a specific FQN."""
        return self.providers.get(fqn)

    def remove_file(self, file_path: str) -> List[str]:
        """Remove a file from the index completely."""
        return self.update_file(file_path, set(), set())
