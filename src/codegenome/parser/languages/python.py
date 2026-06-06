"""Python symbol, import, inheritance, and call extractor."""

from __future__ import annotations

from tree_sitter import Node

from codegenome.parser.common import (
    append_symbol,
    go_type_kind,
    line_number,
    node_text,
    python_class_kind,
    record_call,
    typescript_class_kind,
)
from codegenome.parser.types import ParsedInheritance, ParsedImport, ParseResult


def extract(source: bytes, root: Node, result: ParseResult) -> None:
    """Extract Python structure from ``root`` into ``result``."""
    scope_stack: list[str] = [""]

    def current_scope() -> str:
        return scope_stack[-1]

    def walk(node: Node) -> None:
        if node.type == "function_definition":
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
                scope_stack.append(qname)
                body = node.child_by_field_name("body")
                if body:
                    _walk_calls(body, qname)
                    for child in body.children:
                        walk(child)
                scope_stack.pop()
                return

        if node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = node_text(source, name_node)
                qname = f"{current_scope()}.{name}" if current_scope() else name
                supers = node.child_by_field_name("superclasses")
                kind = python_class_kind(source, node, supers)
                qname = append_symbol(
                    result,
                    name=name,
                    kind=kind,
                    node=node,
                    source=source,
                    qualified_name=qname,
                    body_node=node.child_by_field_name("body"),
                )
                if supers:
                    for child in supers.children:
                        if child.type in {"identifier", "attribute", "argument_list"}:
                            for base in child.children:
                                if base.type in {"identifier", "attribute"}:
                                    result.inheritance.append(
                                        ParsedInheritance(
                                            class_name=name,
                                            base=node_text(source, base),
                                            line=line_number(base),
                                        )
                                    )
                scope_stack.append(qname)
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        walk(child)
                scope_stack.pop()
                return

        if node.type == "import_statement":
            names = [node_text(source, child) for child in node.children if child.type == "dotted_name"]
            if names:
                result.imports.append(
                    ParsedImport(module=names[0], names=[names[0]], start_line=line_number(node))
                )
            return

        if node.type == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            module = node_text(source, module_node) if module_node else ""
            imported: list[str] = []
            for child in node.children:
                if child.type == "dotted_name":
                    imported.append(node_text(source, child))
                elif child.type == "aliased_import":
                    name_node = child.child_by_field_name("name")
                    if name_node:
                        imported.append(node_text(source, name_node))
            result.imports.append(
                ParsedImport(
                    module=module,
                    names=imported or [module],
                    start_line=line_number(node),
                    is_relative=module.startswith("."),
                )
            )
            return

        for child in node.children:
            walk(child)

    def _walk_calls(node: Node, caller: str) -> None:
        if node.type == "call":
            func = node.child_by_field_name("function")
            if func:
                record_call(result, caller, func, source)
        for child in node.children:
            _walk_calls(child, caller)

    walk(root)
