"""Git-aware ignore matching with nested .gitignore and .genomeignore support."""

from __future__ import annotations

from pathlib import Path

from pathspec import GitIgnoreSpec

IGNORE_FILENAMES = (".gitignore", ".genomeignore")

DEFAULT_IGNORE_PATTERNS = [
    ".git/",
    ".venv/",
    "node_modules/",
    "__pycache__/",
    "*.pyc",
    ".genome/",
    ".genomeignore",
]


def _parse_ignore_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
    return lines


def _rewrite_pattern(base_dir: str, pattern: str) -> str:
    """Rewrite a nested ignore pattern so it applies from the workspace root."""
    if not base_dir:
        return pattern

    negated = pattern.startswith("!")
    body = pattern[1:] if negated else pattern
    if body.startswith("/"):
        rewritten = f"{base_dir}/{body[1:]}"
    elif "/" in body:
        rewritten = f"{base_dir}/{body}"
    else:
        rewritten = f"{base_dir}/**/{body}"

    return f"!{rewritten}" if negated else rewritten


class IgnoreMatcher:
    """Match paths using gitignore semantics, including nested ignore files."""

    def __init__(
        self,
        root: Path | None = None,
        extra_patterns: list[str] | None = None,
        *,
        load_workspace_ignores: bool = True,
    ) -> None:
        self.root = root.resolve() if root is not None else None
        self._extra_patterns = list(extra_patterns or [])
        self._load_workspace_ignores = load_workspace_ignores
        self._dir_lines: dict[str, list[str]] = {}
        self._spec_cache: dict[tuple[tuple[str, ...], bool], GitIgnoreSpec] = {}

    @classmethod
    def from_file(cls, root: Path, filename: str = ".genomeignore") -> IgnoreMatcher:
        ignore_path = root / filename
        extra: list[str] = []
        if ignore_path.is_file():
            extra = _parse_ignore_lines(
                ignore_path.read_text(encoding="utf-8", errors="replace")
            )
        return cls(
            root=root,
            extra_patterns=extra,
            load_workspace_ignores=False,
        )

    @classmethod
    def for_workspace(cls, root: Path) -> IgnoreMatcher:
        return cls(root=root, load_workspace_ignores=True)

    def add_pattern(self, pattern: str) -> None:
        self._extra_patterns.append(pattern)
        self._spec_cache.clear()

    def _ignore_lines_for_dir(self, rel_dir: str) -> list[str]:
        if rel_dir in self._dir_lines:
            return self._dir_lines[rel_dir]

        if self.root is None or not self._load_workspace_ignores:
            self._dir_lines[rel_dir] = []
            return []

        abs_dir = self.root / rel_dir if rel_dir else self.root
        lines: list[str] = []
        for name in IGNORE_FILENAMES:
            ignore_path = abs_dir / name
            if ignore_path.is_file():
                lines.extend(
                    _parse_ignore_lines(
                        ignore_path.read_text(encoding="utf-8", errors="replace")
                    )
                )
        self._dir_lines[rel_dir] = lines
        return lines

    @staticmethod
    def _ancestor_dirs(rel_path: str, is_dir: bool) -> tuple[str, ...]:
        normalized = rel_path.replace("\\", "/").strip("/")
        if not normalized:
            return ("",)

        parts = normalized.rstrip("/").split("/")
        if is_dir:
            dir_parts = parts
        else:
            dir_parts = parts[:-1] if len(parts) > 1 else []

        ancestors = [""]
        for index in range(len(dir_parts)):
            ancestors.append("/".join(dir_parts[: index + 1]))
        return tuple(ancestors)

    def _spec_for_ancestors(self, ancestors: tuple[str, ...]) -> GitIgnoreSpec:
        merged: list[str] = list(DEFAULT_IGNORE_PATTERNS)
        merged.extend(self._extra_patterns)
        for base_dir in ancestors:
            for line in self._ignore_lines_for_dir(base_dir):
                merged.append(_rewrite_pattern(base_dir, line))
        return GitIgnoreSpec.from_lines(merged)

    def _get_spec(self, rel_path: str, is_dir: bool) -> GitIgnoreSpec:
        normalized = rel_path.replace("\\", "/").strip("/")
        if is_dir and normalized:
            normalized = f"{normalized}/"
        ancestors = self._ancestor_dirs(normalized, is_dir)
        cache_key = (ancestors, is_dir)
        spec = self._spec_cache.get(cache_key)
        if spec is None:
            spec = self._spec_for_ancestors(ancestors)
            self._spec_cache[cache_key] = spec
        return spec

    def is_ignored(self, rel_path: str, is_dir: bool = False) -> bool:
        normalized = rel_path.replace("\\", "/").strip("/")
        if not normalized and not is_dir:
            return False

        check_path = f"{normalized}/" if is_dir and normalized else normalized
        return self._get_spec(check_path, is_dir).match_file(check_path)
