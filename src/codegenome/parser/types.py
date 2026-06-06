"""Dataclasses describing parsed source structure."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParsedSymbol:
    """Represents a parsed symbol (class, function, method) from source code.

    Attributes:
        name (str): The local name of the symbol.
        kind (str): The kind of symbol (e.g., 'class', 'function', 'method').
        start_line (int): The starting line number (1-indexed).
        end_line (int): The ending line number (1-indexed).
        docstring (str | None): The extracted docstring or leading comment.
        complexity (int | None): Cyclomatic complexity score, if calculated.
        qualified_name (str | None): Fully qualified name, including parent scopes.
        instance_attrs (frozenset[str]): Instance attributes accessed in method bodies.
    """
    name: str
    kind: str
    start_line: int
    end_line: int
    docstring: str | None = None
    complexity: int | None = None
    qualified_name: str | None = None
    instance_attrs: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ParsedImport:
    """Represents an import statement in source code.

    Attributes:
        module (str): The name of the module being imported.
        names (list[str]): The specific symbols imported from the module.
        start_line (int): The line number where the import occurs.
        is_relative (bool): Whether the import is a relative import.
    """
    module: str
    names: list[str]
    start_line: int
    is_relative: bool = False


@dataclass(frozen=True)
class ParsedInheritance:
    """Represents an inheritance relationship extracted from source code.

    Attributes:
        class_name (str): The name of the derived class.
        base (str): The name of the base class or interface.
        line (int): The line number where the inheritance is declared.
    """
    class_name: str
    base: str
    line: int


@dataclass(frozen=True)
class ParsedCall:
    """Represents a function or method call extracted from source code.

    Attributes:
        caller (str): The fully qualified name of the calling function/method.
        callee (str): The name or path of the called function/method.
        line (int): The line number where the call occurs.
    """
    caller: str
    callee: str
    line: int


@dataclass
class ParseResult:
    """Aggregates all parsed information for a single source file.

    Attributes:
        path (str): File path.
        language (str): Language identifier.
        symbols (list[ParsedSymbol]): Extracted symbols.
        imports (list[ParsedImport]): Extracted imports.
        inheritance (list[ParsedInheritance]): Extracted inheritance relationships.
        calls (list[ParsedCall]): Extracted function calls.
        errors (list[str]): Any errors encountered during parsing.
    """
    path: str
    language: str
    symbols: list[ParsedSymbol] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    inheritance: list[ParsedInheritance] = field(default_factory=list)
    calls: list[ParsedCall] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
