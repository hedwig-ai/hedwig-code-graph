"""Tests for markdown document extraction."""

from hedwig_cg.core.extract import extract_file

SAMPLE_MD = """\
# Project Overview

This is the main documentation.

## Installation

Run `pip install hedwig-cg` to install.

### Requirements

- Python 3.10+
- SQLite

## Usage

See [Installation](#installation) for setup.
See [config](./config.md) for configuration.

## API Reference

### Functions

Main entry point is `run_pipeline`.
"""


class TestMarkdownExtraction:
    def test_extracts_document_node(self, tmp_path):
        f = tmp_path / "README.md"
        f.write_text(SAMPLE_MD)
        result = extract_file(str(f), "markdown", SAMPLE_MD)
        kinds = {n.kind for n in result.nodes}
        assert "document" in kinds

    def test_extracts_headings_as_sections(self, tmp_path):
        f = tmp_path / "README.md"
        f.write_text(SAMPLE_MD)
        result = extract_file(str(f), "markdown", SAMPLE_MD)
        sections = [n for n in result.nodes if n.kind == "section"]
        names = {s.name for s in sections}
        assert "Project Overview" in names
        assert "Installation" in names
        assert "Usage" in names
        assert "API Reference" in names
        assert "Requirements" in names
        assert "Functions" in names

    def test_heading_hierarchy(self, tmp_path):
        f = tmp_path / "README.md"
        f.write_text(SAMPLE_MD)
        result = extract_file(str(f), "markdown", SAMPLE_MD)
        # "Requirements" (h3) should be defined by a parent, not directly by document
        edges = result.edges
        req_edges = [
            e for e in edges
            if e.target.endswith("::section::Requirements")
        ]
        assert len(req_edges) == 1
        # Parent should be Installation (h2), not document
        assert "::section::Installation" in req_edges[0].source

    def test_extracts_internal_links(self, tmp_path):
        f = tmp_path / "README.md"
        f.write_text(SAMPLE_MD)
        result = extract_file(str(f), "markdown", SAMPLE_MD)
        ref_edges = [e for e in result.edges if e.relation == "references"]
        targets = {e.target for e in ref_edges}
        assert "*::document::config" in targets

    def test_ignores_external_links(self, tmp_path):
        md = "# Title\n\n[Google](https://google.com)\n[local](./local.md)\n"
        f = tmp_path / "test.md"
        f.write_text(md)
        result = extract_file(str(f), "markdown", md)
        ref_edges = [e for e in result.edges if e.relation == "references"]
        targets = {e.target for e in ref_edges}
        assert "*::document::local" in targets
        assert not any("google" in t for t in targets)

    def test_section_has_snippet(self, tmp_path):
        f = tmp_path / "README.md"
        f.write_text(SAMPLE_MD)
        result = extract_file(str(f), "markdown", SAMPLE_MD)
        install = [n for n in result.nodes if n.name == "Installation"][0]
        assert "pip install" in install.source_snippet

    def test_empty_markdown(self, tmp_path):
        f = tmp_path / "empty.md"
        f.write_text("")
        result = extract_file(str(f), "markdown", "")
        assert len(result.nodes) == 1
        assert result.nodes[0].kind == "document"
