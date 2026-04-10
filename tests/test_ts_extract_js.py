"""Tests for tree-sitter JavaScript/TypeScript extraction."""

from __future__ import annotations

import pytest

from hedwig_kg.core.ts_extract import _ensure_parser, extract_file_ts


@pytest.fixture(autouse=True)
def _reset_parsers():
    """Reset cached parsers between tests."""
    from hedwig_kg.core import ts_extract
    ts_extract._parsers.clear()
    ts_extract._languages.clear()


JS_AVAILABLE = _ensure_parser("javascript")

# Reset after availability check
from hedwig_kg.core import ts_extract as _ts  # noqa: E402

_ts._parsers.clear()
_ts._languages.clear()

pytestmark = pytest.mark.skipif(not JS_AVAILABLE, reason="tree-sitter-javascript not installed")


# --- Simple function extraction ---

class TestJsFunctionExtraction:
    def test_function_declaration(self):
        code = 'function greet(name) {\n  return "Hello " + name;\n}'
        result = extract_file_ts("src/hello.js", "javascript", code)
        names = [n.name for n in result.nodes]
        assert "hello" in names  # module node
        assert "greet" in names

    def test_arrow_function_const(self):
        code = "const add = (a, b) => a + b;"
        result = extract_file_ts("src/math.js", "javascript", code)
        names = [n.name for n in result.nodes]
        assert "add" in names

    def test_function_signature(self):
        code = "function multiply(x, y) { return x * y; }"
        result = extract_file_ts("src/math.js", "javascript", code)
        func = next(n for n in result.nodes if n.name == "multiply")
        assert "(x, y)" in func.signature

    def test_exported_function(self):
        code = "export function handleRequest(req, res) {\n  res.send('ok');\n}"
        result = extract_file_ts("src/handler.js", "javascript", code)
        names = [n.name for n in result.nodes]
        assert "handleRequest" in names


# --- Class extraction ---

class TestJsClassExtraction:
    def test_class_declaration(self):
        code = (
            "class Animal {\n  constructor(name) { this.name = name; }\n"
            "  speak() { return this.name; }\n}"
        )
        result = extract_file_ts("src/animal.js", "javascript", code)
        names = [n.name for n in result.nodes]
        assert "Animal" in names
        kinds = {n.name: n.kind for n in result.nodes}
        assert kinds["Animal"] == "class"

    def test_class_methods_are_extracted(self):
        code = "class Dog {\n  bark() { return 'woof'; }\n  fetch(item) { return item; }\n}"
        result = extract_file_ts("src/dog.js", "javascript", code)
        names = [n.name for n in result.nodes]
        assert "Dog.bark" in names
        assert "Dog.fetch" in names

    def test_method_kind_is_method(self):
        code = "class Cat {\n  meow() { return 'meow'; }\n}"
        result = extract_file_ts("src/cat.js", "javascript", code)
        meow = next(n for n in result.nodes if n.name == "Cat.meow")
        assert meow.kind == "method"

    def test_class_extends(self):
        code = "class Dog extends Animal {\n  bark() {}\n}"
        result = extract_file_ts("src/dog.js", "javascript", code)
        inherit_edges = [e for e in result.edges if e.relation == "inherits"]
        assert len(inherit_edges) >= 1
        assert any("Animal" in e.target for e in inherit_edges)

    def test_exported_class(self):
        code = "export class Router {\n  route(path) {}\n}"
        result = extract_file_ts("src/router.js", "javascript", code)
        names = [n.name for n in result.nodes]
        assert "Router" in names
        assert "Router.route" in names


# --- Import extraction ---

class TestJsImportExtraction:
    def test_import_statement(self):
        code = "import express from 'express';\n\nfunction app() {}"
        result = extract_file_ts("src/app.js", "javascript", code)
        import_edges = [e for e in result.edges if e.relation == "imports"]
        assert any("express" in e.target for e in import_edges)

    def test_named_import(self):
        code = "import { useState, useEffect } from 'react';\n"
        result = extract_file_ts("src/comp.js", "javascript", code)
        import_edges = [e for e in result.edges if e.relation == "imports"]
        assert any("react" in e.target for e in import_edges)


# --- Constants ---

class TestJsConstantExtraction:
    def test_uppercase_const(self):
        code = "const MAX_RETRIES = 3;"
        result = extract_file_ts("src/config.js", "javascript", code)
        names = [n.name for n in result.nodes]
        assert "MAX_RETRIES" in names

    def test_lowercase_const_not_extracted(self):
        code = "const name = 'hello';"
        result = extract_file_ts("src/config.js", "javascript", code)
        names = [n.name for n in result.nodes]
        assert "name" not in names


# --- Edge cases ---

class TestJsEdgeCases:
    def test_empty_file(self):
        result = extract_file_ts("src/empty.js", "javascript", "")
        # At minimum, should have module node
        assert len(result.nodes) >= 1
        assert result.nodes[0].kind == "module"

    def test_defines_edges(self):
        code = "function foo() {}\nfunction bar() {}"
        result = extract_file_ts("src/funcs.js", "javascript", code)
        defines = [e for e in result.edges if e.relation == "defines"]
        assert len(defines) >= 2

    def test_complex_file(self):
        code = """
import { EventEmitter } from 'events';

const MAX_LISTENERS = 10;

export class Server extends EventEmitter {
  constructor(port) {
    super();
    this.port = port;
  }

  listen() {
    console.log('listening on', this.port);
  }

  close() {
    this.emit('close');
  }
}

export function createServer(port) {
  return new Server(port);
}
"""
        result = extract_file_ts("src/server.js", "javascript", code)
        names = [n.name for n in result.nodes]
        assert "Server" in names
        assert "Server.listen" in names
        assert "Server.close" in names
        assert "createServer" in names
        assert "MAX_LISTENERS" in names

        # Verify inheritance
        inherit = [e for e in result.edges if e.relation == "inherits"]
        assert any("EventEmitter" in e.target for e in inherit)

        # Verify import
        imports = [e for e in result.edges if e.relation == "imports"]
        assert any("events" in e.target for e in imports)


# --- Fallback behavior ---

class TestFallbackBehavior:
    def test_unknown_language_falls_back(self):
        code = "fn main() { println!(\"hello\"); }"
        result = extract_file_ts("src/main.rs", "rust", code)
        # Should still return something via regex fallback
        assert result is not None
