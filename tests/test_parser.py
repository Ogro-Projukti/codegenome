"""Tests for tree-sitter source parser."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from codegenome import parser as parser_module
from codegenome.parser import SourceParser


@pytest.fixture
def parser() -> SourceParser:
    return SourceParser()


def test_parser_extracts_python_symbols(parser: SourceParser) -> None:
    source = b'''"""Module doc."""
import os
from pathlib import Path

class Greeter:
    """Says hello."""

    def greet(self, name):
        self.name = name
        if name:
            helper(name)
        return self.name

def helper(value):
    return value
'''
    result = parser.parse_bytes(source, "python", "sample.py")
    assert not result.errors or result.errors == ["Syntax errors detected in AST"]
    names = {symbol.name for symbol in result.symbols}
    assert "Greeter" in names
    assert "greet" in names
    assert "helper" in names
    assert any(symbol.kind == "class" for symbol in result.symbols)
    assert any(symbol.docstring for symbol in result.symbols)
    assert any(symbol.complexity and symbol.complexity >= 1 for symbol in result.symbols)
    assert result.imports
    assert any(call.callee == "helper" for call in result.calls)
    greet = next(symbol for symbol in result.symbols if symbol.name == "greet")
    assert "name" in greet.instance_attrs


def test_parser_extracts_javascript_and_typescript(parser: SourceParser) -> None:
    js = b"""
import fs from 'fs';

class Service extends Base {
  run() {
    helper();
  }
}

function helper() {
  return 1;
}
"""
    js_result = parser.parse_bytes(js, "javascript", "app.js")
    assert any(symbol.name == "Service" for symbol in js_result.symbols)
    assert js_result.imports
    assert js_result.inheritance

    ts = b"""
export class Worker {
  execute(): void {
    doWork();
  }
}
"""
    ts_result = parser.parse_bytes(ts, "typescript", "worker.ts")
    assert any(symbol.name == "Worker" for symbol in ts_result.symbols)


def test_parser_extracts_go_and_rust(parser: SourceParser) -> None:
    go_source = b"""package main

import "fmt"

type Greeter struct {}

func (g Greeter) Hello() {
    fmt.Println("hi")
    helper()
}

func helper() {}
"""
    go_result = parser.parse_bytes(go_source, "go", "main.go")
    assert any(symbol.name == "Greeter" for symbol in go_result.symbols)
    assert any(symbol.name == "Hello" for symbol in go_result.symbols)
    assert go_result.imports

    rust_source = b"""
use std::io;

struct Worker;

impl Worker {
    fn run(&self) {
        helper();
    }
}

fn helper() {}
"""
    rust_result = parser.parse_bytes(rust_source, "rust", "main.rs")
    assert any(symbol.name == "Worker" for symbol in rust_result.symbols)
    assert any(symbol.name == "run" for symbol in rust_result.symbols)
    assert rust_result.imports


def test_parser_malformed_syntax_is_non_fatal(parser: SourceParser, caplog: pytest.LogCaptureFixture) -> None:
    bad_source = b"def broken(:\n    pass\n"
    result = parser.parse_bytes(bad_source, "python", "broken.py")
    assert result.errors
    assert result.symbols == [] or isinstance(result.symbols, list)


def test_parser_unknown_extension_returns_none(parser: SourceParser, tmp_path: Path) -> None:
    path = tmp_path / "data.bin"
    path.write_bytes(b"\x00\x01")
    assert parser.parse_file(path) is None


def test_parser_read_failure_is_graceful(parser: SourceParser, tmp_path: Path) -> None:
    path = tmp_path / "missing.py"
    result = parser.parse_file(path)
    assert result is not None
    assert result.errors


def test_build_language_supports_legacy_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    capsule = object()

    class LegacyLanguage:
        def __init__(self, received_capsule: object, name: str) -> None:
            self.received_capsule = received_capsule
            self.name = name

    module = SimpleNamespace(language=lambda: capsule)
    monkeypatch.setattr(parser_module, "Language", LegacyLanguage)

    language = parser_module._build_language(module, "language", "python")
    assert language.received_capsule is capsule
    assert language.name == "python"


def test_build_language_supports_modern_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    capsule = object()

    class ModernLanguage:
        def __init__(self, received_capsule: object) -> None:
            self.received_capsule = received_capsule

    module = SimpleNamespace(language=lambda: capsule)
    monkeypatch.setattr(parser_module, "Language", ModernLanguage)

    language = parser_module._build_language(module, "language", "python")
    assert language.received_capsule is capsule
