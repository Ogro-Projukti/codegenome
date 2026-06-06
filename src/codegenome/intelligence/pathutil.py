"""Lightweight path helper used in hot analysis loops."""

from __future__ import annotations


class PathLike:
    """Minimal path helper to avoid importing pathlib in hot loops.

    Attributes:
        _value (str): The internal normalized path string.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        """Initialize the PathLike object.

        Args:
            value (str): The path string to normalize and wrap.
        """
        self._value = value.replace("\\", "/")

    @property
    def name(self) -> str:
        return self._value.rsplit("/", 1)[-1]

    @property
    def stem(self) -> str:
        name = self.name
        if "." in name:
            return name.rsplit(".", 1)[0]
        return name

    @property
    def parent(self) -> "PathLike":
        if "/" not in self._value:
            return PathLike(".")
        return PathLike(self._value.rsplit("/", 1)[0])

    def as_posix(self) -> str:
        return self._value

    def __str__(self) -> str:
        return self._value
