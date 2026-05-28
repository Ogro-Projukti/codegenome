"""Global Dependency Registry for tracking O(1) cross-module graph relationships."""

from dataclasses import dataclass, field
from typing import Dict, Set, List


@dataclass
class RegistryEntry:
    """Provides and Consumes sets for a single file.
    
    Attributes:
        provides (Set[str]): The set of fully qualified names provided by this file.
        consumes (Set[str]): The set of fully qualified names consumed by this file.
    """
    provides: Set[str] = field(default_factory=set)
    consumes: Set[str] = field(default_factory=set)


class GlobalDependencyRegistry:
    """In-memory index for resolving cross-module dependencies in O(1) time."""

    def __init__(self) -> None:
        """Initialize an empty GlobalDependencyRegistry."""
        self.files: Dict[str, RegistryEntry] = {}
        self.providers: Dict[str, str] = {}
        self.consumers: Dict[str, Set[str]] = {}

    def update_file(self, file_path: str, provides: Set[str], consumes: Set[str]) -> List[str]:
        """Update the index for a file and return any FQNs that were deleted.

        Args:
            file_path (str): The path to the file being updated.
            provides (Set[str]): The new set of provided FQNs.
            consumes (Set[str]): The new set of consumed FQNs.

        Returns:
            List[str]: A list of FQNs that are no longer provided by this file.
        """
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
        """Return file paths that consume a specific FQN.

        Args:
            fqn (str): The fully qualified name to look up.

        Returns:
            Set[str]: A set of file paths that consume the given FQN.
        """
        return self.consumers.get(fqn, set())

    def get_provider(self, fqn: str) -> str | None:
        """Return the file path that provides a specific FQN.

        Args:
            fqn (str): The fully qualified name to look up.

        Returns:
            str | None: The file path that provides the FQN, or None if not found.
        """
        return self.providers.get(fqn)

    def remove_file(self, file_path: str) -> List[str]:
        """Remove a file from the index completely.

        Args:
            file_path (str): The path to the file to remove.

        Returns:
            List[str]: A list of FQNs that were provided by the removed file.
        """
        return self.update_file(file_path, set(), set())
