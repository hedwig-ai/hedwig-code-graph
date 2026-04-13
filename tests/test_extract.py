"""Tests for code extraction (regex fallback)."""

from hedwig_cg.core.extract import extract_file


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


class TestExtractHTML:
    def test_extracts_headings(self):
        html = (
            "<html><body><h1>Title</h1><h2>Section A</h2>"
            "<p>text</p><h2>Section B</h2></body></html>"
        )
        result = extract_file("page.html", "html", html)
        names = {n.name for n in result.nodes}
        assert "Title" in names
        assert "Section A" in names
        assert "Section B" in names

    def test_creates_document_node(self):
        html = "<html><body><p>Hello</p></body></html>"
        result = extract_file("page.html", "html", html)
        docs = [n for n in result.nodes if n.kind == "document"]
        assert len(docs) == 1
        assert docs[0].name == "page"

    def test_extracts_local_links(self):
        html = '<a href="other.html">link</a><a href="https://example.com">ext</a>'
        result = extract_file("page.html", "html", html)
        ref_edges = [e for e in result.edges if e.relation == "references"]
        targets = {e.target for e in ref_edges}
        assert any("other" in t for t in targets)
        # External links should NOT create reference edges
        assert not any("example" in t for t in targets)

    def test_heading_defines_edges(self):
        html = "<h1>Main</h1><h2>Sub</h2>"
        result = extract_file("page.html", "html", html)
        defines = [e for e in result.edges if e.relation == "defines"]
        assert len(defines) >= 2


class TestExtractCSV:
    def test_extracts_columns(self):
        csv_content = "name,age,email\nAlice,30,a@b.com\nBob,25,b@c.com\n"
        result = extract_file("users.csv", "csv", csv_content)
        names = {n.name for n in result.nodes}
        assert "name" in names
        assert "age" in names
        assert "email" in names

    def test_creates_document_node(self):
        csv_content = "col1,col2\nval1,val2\n"
        result = extract_file("data.csv", "csv", csv_content)
        docs = [n for n in result.nodes if n.kind == "document"]
        assert len(docs) == 1
        assert docs[0].name == "data"

    def test_column_nodes_are_variables(self):
        csv_content = "x,y,z\n1,2,3\n"
        result = extract_file("points.csv", "csv", csv_content)
        vars_ = [n for n in result.nodes if n.kind == "variable"]
        assert len(vars_) == 3

    def test_defines_edges_for_columns(self):
        csv_content = "a,b\n1,2\n"
        result = extract_file("sheet.csv", "csv", csv_content)
        defines = [e for e in result.edges if e.relation == "defines"]
        assert len(defines) == 2

    def test_tsv_support(self):
        tsv_content = "col1\tcol2\nval1\tval2\n"
        result = extract_file("data.tsv", "csv", tsv_content)
        names = {n.name for n in result.nodes}
        assert "col1" in names
        assert "col2" in names

    def test_snippet_contains_column_info(self):
        csv_content = "name,age\nAlice,30\n"
        result = extract_file("people.csv", "csv", csv_content)
        doc = [n for n in result.nodes if n.kind == "document"][0]
        assert "Columns:" in doc.source_snippet
        assert "name" in doc.source_snippet


class TestExtractPDF:
    def test_creates_document_node_without_pymupdf(self):
        """PDF extraction should create a document node even without pymupdf."""
        result = extract_file("report.pdf", "pdf", "[binary content]")
        docs = [n for n in result.nodes if n.kind == "document"]
        assert len(docs) == 1
        assert docs[0].name == "report"
        assert docs[0].language == "pdf"


class TestExtractFallback:
    def test_unknown_language_returns_module(self):
        result = extract_file("main.go", "go", "package main\n")
        assert len(result.nodes) == 1
        assert result.nodes[0].kind == "module"
