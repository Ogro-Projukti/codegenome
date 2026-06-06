"""Rust symbol, import, inheritance (impl/trait), and call extractor."""

from __future__ import annotations

import re

from tree_sitter import Node

from codegenome.parser.common import (
    append_symbol,
    line_number,
    node_text,
    record_call,
)
from codegenome.parser.types import ParsedInheritance, ParsedImport, ParseResult


def extract(source: bytes, root: Node, result: ParseResult) -> None:
    """Extract Rust structure from ``root`` into ``result``."""
    scope_stack: list[str] = [""]

    def current_scope() -> str:
        return scope_stack[-1]

    def walk(node: Node) -> None:
        if node.type == "function_item":
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

        if node.type in {"struct_item", "enum_item", "trait_item"}:
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = node_text(source, name_node)
                kind = "interface" if node.type == "trait_item" else "class"
                qname = append_symbol(
                    result,
                    name=name,
                    kind=kind,
                    node=node,
                    source=source,
                    qualified_name=name,
                )
                if node.type == "struct_item":
                    scope_stack.append(qname)
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            walk(child)
                    scope_stack.pop()
            return

        if node.type == "impl_item":
            type_node = node.child_by_field_name("type")
            trait_node = node.child_by_field_name("trait")
            if type_node is not None:
                type_name = node_text(source, type_node)
                if trait_node is not None:
                    result.inheritance.append(
                        ParsedInheritance(
                            class_name=type_name,
                            base=node_text(source, trait_node),
                            line=line_number(trait_node),
                        )
                    )
                scope_stack.append(type_name)
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        walk(child)
                scope_stack.pop()
            return

        if node.type == "use_declaration":
            text = node_text(source, node)
            module = re.sub(r"^use\s+", "", text).strip().strip(";")
            result.imports.append(
                ParsedImport(module=module, names=[module], start_line=line_number(node))
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
