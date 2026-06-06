"""JavaScript/TypeScript/TSX symbol, import, inheritance, and call extractor."""

from __future__ import annotations

from tree_sitter import Node

from codegenome.parser.common import (
    append_symbol,
    line_number,
    node_text,
    record_call,
    typescript_class_kind,
)
from codegenome.parser.types import ParsedInheritance, ParsedImport, ParseResult


def extract(source: bytes, root: Node, result: ParseResult, language: str) -> None:
    """Extract JS-like structure from ``root`` into ``result``."""
    scope_stack: list[str] = [""]

    def current_scope() -> str:
        return scope_stack[-1]

    def walk(node: Node) -> None:
        if node.type in {"function_declaration", "method_definition", "generator_function_declaration"}:
            name_node = node.child_by_field_name("name")
            name = node_text(source, name_node) if name_node else "<anonymous>"
            kind = "method" if node.type == "method_definition" else "function"
            qname = f"{current_scope()}.{name}" if current_scope() else name
            qname = append_symbol(
                result,
                name=name,
                kind=kind,
                node=node,
                source=source,
                qualified_name=qname,
                body_node=node.child_by_field_name("body"),
            )
            scope_stack.append(qname)
            body = node.child_by_field_name("body")
            if body:
                _walk_calls(body, qname)
            scope_stack.pop()
            return

        if node.type in {"class_declaration", "abstract_class_declaration"}:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = node_text(source, name_node)
                qname = f"{current_scope()}.{name}" if current_scope() else name
                qname = append_symbol(
                    result,
                    name=name,
                    kind=typescript_class_kind(node),
                    node=node,
                    source=source,
                    qualified_name=qname,
                    body_node=node.child_by_field_name("body"),
                )
                heritage = None
                for child in node.children:
                    if child.type.endswith("class_heritage") or child.type == "extends_clause":
                        heritage = child
                        break
                if heritage:
                    for child in heritage.children:
                        if child.type in {"identifier", "member_expression", "type_identifier"}:
                            result.inheritance.append(
                                ParsedInheritance(
                                    class_name=name,
                                    base=node_text(source, child),
                                    line=line_number(child),
                                )
                            )
                scope_stack.append(qname)
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        walk(child)
                scope_stack.pop()
                return

        if node.type == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = node_text(source, name_node)
                qname = f"{current_scope()}.{name}" if current_scope() else name
                append_symbol(
                    result,
                    name=name,
                    kind="interface",
                    node=node,
                    source=source,
                    qualified_name=qname,
                    body_node=node.child_by_field_name("body"),
                )
            return

        if node.type == "import_statement":
            source_node = node.child_by_field_name("source")
            module = node_text(source, source_node).strip("\"'") if source_node else ""
            names: list[str] = []
            for child in node.children:
                if child.type == "import_clause":
                    for part in child.children:
                        if part.type == "identifier":
                            names.append(node_text(source, part))
                        elif part.type == "named_imports":
                            for spec in part.children:
                                if spec.type == "import_specifier":
                                    name_node = spec.child_by_field_name("name")
                                    if name_node:
                                        names.append(node_text(source, name_node))
            result.imports.append(
                ParsedImport(
                    module=module,
                    names=names or [module],
                    start_line=line_number(node),
                    is_relative=module.startswith("."),
                )
            )
            return

        if node.type == "lexical_declaration":
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    value_node = child.child_by_field_name("value")
                    if name_node and value_node and value_node.type in {
                        "arrow_function",
                        "function_expression",
                        "function",
                    }:
                        name = node_text(source, name_node)
                        qname = f"{current_scope()}.{name}" if current_scope() else name
                        qname = append_symbol(
                            result,
                            name=name,
                            kind="function",
                            node=child,
                            source=source,
                            qualified_name=qname,
                            body_node=value_node.child_by_field_name("body"),
                        )
                        body = value_node.child_by_field_name("body")
                        if body:
                            _walk_calls(body, qname)

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
