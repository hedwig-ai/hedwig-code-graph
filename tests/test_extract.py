"""Tests for code extraction (regex fallback)."""

from hedwig_kg.core.extract import extract_file


class TestExtractPython:
    def test_extracts_classes(self):
        code = "class Foo:\n    pass\n\nclass Bar(Foo):\n    pass\n"
        result = extract_file("test.py", "python", code)
        names = {n.name for n in result.nodes}
        assert "Foo" in names
        assert "Bar" in names

    def test_extracts_functions(self):
        code = "def hello(name):\n    return name\n\nasync def fetch(url):\n    pass\n"
        result = extract_file("test.py", "python", code)
        names = {n.name for n in result.nodes}
        assert "hello" in names
        assert "fetch" in names

    def test_extracts_imports(self):
        code = "import os\nfrom pathlib import Path\n"
        result = extract_file("test.py", "python", code)
        targets = {e.target for e in result.edges if e.relation == "imports"}
        assert any("os" in t for t in targets)
        assert any("Path" in t for t in targets)

    def test_module_node_created(self):
        result = extract_file("hello.py", "python", "x = 1\n")
        modules = [n for n in result.nodes if n.kind == "module"]
        assert len(modules) == 1
        assert modules[0].name == "hello"


class TestExtractJavaScript:
    def test_extracts_classes(self):
        code = "class App extends Component {\n}\n"
        result = extract_file("app.js", "javascript", code)
        names = {n.name for n in result.nodes}
        assert "App" in names

    def test_extracts_functions(self):
        code = "function render() {}\nconst update = () => {}\n"
        result = extract_file("app.js", "javascript", code)
        names = {n.name for n in result.nodes}
        assert "render" in names

    def test_extracts_imports(self):
        code = "import { useState } from 'react';\n"
        result = extract_file("app.js", "javascript", code)
        targets = {e.target for e in result.edges if e.relation == "imports"}
        assert any("react" in t for t in targets)


class TestExtractFallback:
    def test_unknown_language_returns_module(self):
        result = extract_file("main.go", "go", "package main\n")
        assert len(result.nodes) == 1
        assert result.nodes[0].kind == "module"
