"""Shared AST helpers used by the per-language extractors."""

from __future__ import annotations

from tree_sitter import Node

from codegenome.parser.types import ParseResult, ParsedCall, ParsedSymbol


def line_number(node: Node) -> int:
    """Return the 1-indexed start line for a node."""
    return node.start_point[0] + 1


def end_line(node: Node) -> int:
    """Return the 1-indexed end line for a node."""
    return node.end_point[0] + 1


def node_text(source: bytes, node: Node) -> str:
    """Decode the source slice covered by ``node``."""
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def collect_instance_attrs(body_node: Node | None, source: bytes) -> frozenset[str]:
    """Collect instance attribute names accessed via self/this in a method body."""
    if body_node is None:
        return frozenset()

    attrs: set[str] = set()

    def walk(node: Node) -> None:
        if node.type == "attribute":
            obj = node.child_by_field_name("object")
            attr = node.child_by_field_name("attribute")
            if obj is not None and attr is not None:
                receiver = node_text(source, obj)
                if receiver in {"self", "this"}:
                    attrs.add(node_text(source, attr))
        elif node.type == "member_expression":
            obj = node.child_by_field_name("object")
            prop = node.child_by_field_name("property")
            if obj is not None and prop is not None and node_text(source, obj) == "this":
                attrs.add(node_text(source, prop))
        for child in node.children:
            walk(child)

    walk(body_node)
    return frozenset(attrs)


def count_complexity(source: bytes, node: Node) -> int:
    """Approximate cyclomatic complexity from branch-like AST nodes."""
    branch_types = {
        "if_statement",
        "elif_clause",
        "else_clause",
        "for_statement",
        "for_in_statement",
        "while_statement",
        "case_clause",
        "catch_clause",
        "conditional_expression",
        "binary_expression",
        "match_arm",
        "guard",
    }
    count = 1

    def walk(current: Node) -> None:
        nonlocal count
        if current.type in branch_types:
            count += 1
            if current.type == "binary_expression":
                text = node_text(source, current)
                if "&&" not in text and "||" not in text and " and " not in text and " or " not in text:
                    count -= 1
        for child in current.children:
            walk(child)

    walk(node)
    return count


def python_docstring(source: bytes, body_node: Node | None) -> str | None:
    """Extract a Python docstring from the first statement of a body node."""
    if body_node is None or not body_node.children:
        return None
    first = body_node.children[0]
    if first.type != "expression_statement":
        return None
    expr = first.children[0] if first.children else None
    if expr is None or expr.type != "string":
        return None
    text = node_text(source, expr)
    for quote in ('"""', "'''", '"', "'"):
        if text.startswith(quote) and text.endswith(quote):
            return text[len(quote) : -len(quote)].strip()
    return text.strip()


def leading_comment_doc(source: bytes, node: Node) -> str | None:
    """Collect a leading line-comment block immediately above a node."""
    start = node.start_byte
    prefix = source[:start].decode("utf-8", errors="replace")
    lines = prefix.splitlines()
    collected: list[str] = []
    for line in reversed(lines[-5:]):
        stripped = line.strip()
        if stripped.startswith("#"):
            collected.insert(0, stripped.lstrip("#").strip())
        elif stripped.startswith("//"):
            collected.insert(0, stripped.lstrip("/").strip())
        elif stripped.startswith("///") or stripped.startswith("//!"):
            collected.insert(0, stripped.lstrip("/!").strip())
        elif not stripped:
            continue
        else:
            break
    if not collected:
        return None
    return "\n".join(collected)


def append_symbol(
    result: ParseResult,
    *,
    name: str,
    kind: str,
    node: Node,
    source: bytes,
    qualified_name: str | None = None,
    body_node: Node | None = None,
) -> str:
    """Append a :class:`ParsedSymbol` to ``result`` and return its qualified name."""
    docstring = python_docstring(source, body_node) if body_node else None
    if docstring is None:
        docstring = leading_comment_doc(source, node)
    qname = qualified_name or name
    instance_attrs = (
        collect_instance_attrs(body_node, source)
        if kind in {"function", "method"} and body_node is not None
        else frozenset()
    )
    result.symbols.append(
        ParsedSymbol(
            name=name,
            kind=kind,
            start_line=line_number(node),
            end_line=end_line(node),
            docstring=docstring,
            complexity=count_complexity(source, node),
            qualified_name=qname,
            instance_attrs=instance_attrs,
        )
    )
    return qname


def record_call(result: ParseResult, caller: str, callee_node: Node, source: bytes) -> None:
    """Record a call edge from ``caller`` to the resolved callee name."""
    callee = call_target_name(callee_node, source)
    if not callee or not caller:
        return
    result.calls.append(
        ParsedCall(
            caller=caller,
            callee=callee,
            line=line_number(callee_node),
        )
    )


def call_target_name(node: Node, source: bytes) -> str | None:
    """Resolve the textual callee name from a call's function node."""
    if node.type == "identifier":
        return node_text(source, node)
    if node.type == "attribute":
        return node_text(source, node)
    if node.type == "field_expression":
        return node_text(source, node)
    if node.type == "member_expression":
        return node_text(source, node)
    if node.type == "scoped_identifier":
        return node_text(source, node)
    if node.type == "selector_expression":
        for child in reversed(node.children):
            if child.type == "field_identifier":
                return node_text(source, child)
    if node.children:
        return call_target_name(node.children[0], source)
    return None


_INTERFACE_BASE_NAMES = frozenset({"Protocol"})
_ABSTRACT_BASE_NAMES = frozenset({"ABC", "ABCMeta"})


def _collect_base_names(source: bytes, supers_node: Node | None) -> list[str]:
    """Extract textual base-class names from a superclasses / heritage node."""
    if supers_node is None:
        return []
    names: list[str] = []
    for child in supers_node.children:
        if child.type in {"identifier", "attribute", "type_identifier", "scoped_type_identifier"}:
            names.append(node_text(source, child))
        elif child.type == "argument_list":
            for base in child.children:
                if base.type in {"identifier", "attribute", "type_identifier"}:
                    names.append(node_text(source, base))
    return names


def _node_has_decorator(source: bytes, node: Node, *needles: str) -> bool:
    """Return True when ``node`` carries a decorator containing any ``needles``."""
    for child in node.children:
        if child.type != "decorator":
            continue
        text = node_text(source, child).strip("@").casefold()
        if any(needle.casefold() in text for needle in needles):
            return True
    return False


def python_class_kind(source: bytes, class_node: Node, supers_node: Node | None) -> str:
    """Classify a Python ``class_definition`` as class, abstract_class, or interface."""
    for base in _collect_base_names(source, supers_node):
        short = base.rsplit(".", 1)[-1]
        if short in _INTERFACE_BASE_NAMES or base.endswith(".Protocol"):
            return "interface"
    for base in _collect_base_names(source, supers_node):
        short = base.rsplit(".", 1)[-1]
        if short in _ABSTRACT_BASE_NAMES or base.endswith(".ABC"):
            return "abstract_class"
    if _node_has_decorator(source, class_node, "abstract"):
        return "abstract_class"
    body = class_node.child_by_field_name("body")
    if body is not None:
        for child in body.children:
            if child.type == "function_definition" and _node_has_decorator(
                source, child, "abstractmethod"
            ):
                return "abstract_class"
    return "class"


def typescript_class_kind(node: Node) -> str:
    """Classify a TS/JS class AST node."""
    if node.type == "abstract_class_declaration":
        return "abstract_class"
    return "class"


def go_type_kind(source: bytes, spec_node: Node) -> str:
    """Classify a Go ``type_spec`` as class (struct) or interface."""
    type_node = spec_node.child_by_field_name("type")
    if type_node is not None and type_node.type == "interface_type":
        return "interface"
    return "class"
