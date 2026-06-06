"""Go symbol, import, and call extractor."""

from __future__ import annotations

from tree_sitter import Node

from codegenome.parser.common import (
    append_symbol,
    line_number,
    node_text,
    record_call,
)
from codegenome.parser.types import ParsedImport, ParseResult


def extract(source: bytes, root: Node, result: ParseResult) -> None:
    """Extract Go structure from ``root`` into ``result``."""
    package_name = ""
    for child in root.children:
        if child.type == "package_clause":
            for part in child.children:
                if part.type == "package_identifier":
                    package_name = node_text(source, part)

    scope_stack: list[str] = [package_name]

    def current_scope() -> str:
        return scope_stack[-1]

    def walk(node: Node) -> None:
        if node.type == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = node_text(source, name_node)
                qname = f"{current_scope()}.{name}" if current_scope() else name
                qname = append_symbol(
                    result,
                    name=name,
                    kind="function",
                    node=node,
                    source=source,
                    qualified_name=qname,
                    body_node=node.child_by_field_name("body"),
                )
                body = node.child_by_field_name("body")
                if body:
                    _walk_calls(body, qname)
            return

        if node.type == "method_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = node_text(source, name_node)
                qname = f"{current_scope()}.{name}" if current_scope() else name
                qname = append_symbol(
                    result,
                    name=name,
                    kind="method",
                    node=node,
                    source=source,
                    qualified_name=qname,
                    body_node=node.child_by_field_name("body"),
                )
                body = node.child_by_field_name("body")
                if body:
                    _walk_calls(body, qname)
            return

        if node.type == "type_declaration":
            for spec in node.children:
                if spec.type == "type_spec":
                    name_node = spec.child_by_field_name("name")
                    if name_node is not None:
                        name = node_text(source, name_node)
                        append_symbol(
                            result,
                            name=name,
                            kind="class",
                            node=spec,
                            source=source,
                            qualified_name=name,
                        )
            return

        if node.type == "import_declaration":
            for child in node.children:
                if child.type == "import_spec":
                    path_node = child.child_by_field_name("path")
                    module = node_text(source, path_node).strip('"') if path_node else ""
                    result.imports.append(
                        ParsedImport(module=module, names=[module], start_line=line_number(child))
                    )
            return

        for child in node.children:
            walk(child)

    def _walk_calls(node: Node, caller: str) -> None:
        if node.type == "call_expression":
            func = node.child_by_field_name("function")
            if func:
                record_call(result, caller, func, source)
        for child in node.children:
            _walk_calls(child, caller)

    walk(root)
