"""AST extraction module using tree-sitter.

Extracts structural elements (functions, classes, imports, calls) from source files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExtractedNode:
    id: str
    name: str
    kind: str  # "function", "class", "method", "module", "variable"
    file_path: str
    language: str
    start_line: int = 0
    end_line: int = 0
    docstring: str = ""
    signature: str = ""
    source_snippet: str = ""  # First N lines for embedding context
    decorators: list[str] = field(default_factory=list)


@dataclass
class ExtractedEdge:
    source: str
    target: str
    relation: str  # "imports", "calls", "defines", "inherits", "contains"
    confidence: str = "EXTRACTED"  # EXTRACTED | INFERRED | AMBIGUOUS


@dataclass
class ExtractionResult:
    nodes: list[ExtractedNode] = field(default_factory=list)
    edges: list[ExtractedEdge] = field(default_factory=list)


# Regex-based fallback extractors (when tree-sitter is not available for a language)
_PYTHON_CLASS = re.compile(r"^class\s+(\w+)(?:\(([^)]*)\))?:", re.MULTILINE)
_PYTHON_FUNC = re.compile(r"^(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)", re.MULTILINE)
_PYTHON_IMPORT = re.compile(
    r"^(?:from\s+([\w.]+)\s+)?import\s+([\w.,\s]+)", re.MULTILINE
)
_JS_FUNC = re.compile(
    r"(?:export\s+)?(?:async\s+)?function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(",
    re.MULTILINE,
)
_JS_CLASS = re.compile(r"class\s+(\w+)(?:\s+extends\s+(\w+))?", re.MULTILINE)
_JS_IMPORT = re.compile(
    r'import\s+(?:\{[^}]*\}|\w+)(?:\s*,\s*(?:\{[^}]*\}|\w+))?\s+from\s+["\']([^"\']+)',
    re.MULTILINE,
)


def _make_node_id(file_path: str, name: str, kind: str) -> str:
    return f"{file_path}::{kind}::{name}"


def _extract_snippet(content: str, start: int, end: int, max_lines: int = 0) -> str:
    """Extract source lines. max_lines=0 means no limit (full source)."""
    lines = content.splitlines()
    if max_lines > 0:
        snippet_lines = lines[start:min(end + 1, start + max_lines)]
    else:
        snippet_lines = lines[start:end + 1]
    return "\n".join(snippet_lines)


def _extract_python(file_path: str, content: str) -> ExtractionResult:
    result = ExtractionResult()
    module_id = _make_node_id(file_path, Path(file_path).stem, "module")
    result.nodes.append(ExtractedNode(
        id=module_id,
        name=Path(file_path).stem,
        kind="module",
        file_path=file_path,
        language="python",
    ))

    # Extract classes
    for m in _PYTHON_CLASS.finditer(content):
        name = m.group(1)
        bases = m.group(2) or ""
        line = content[:m.start()].count("\n")
        node_id = _make_node_id(file_path, name, "class")
        result.nodes.append(ExtractedNode(
            id=node_id, name=name, kind="class",
            file_path=file_path, language="python",
            start_line=line,
            source_snippet=_extract_snippet(content, line, line + 30),
        ))
        result.edges.append(ExtractedEdge(module_id, node_id, "defines"))
        for base in (b.strip() for b in bases.split(",") if b.strip()):
            base_id = f"*::{base}"  # Placeholder, resolved during build
            result.edges.append(ExtractedEdge(node_id, base_id, "inherits"))

    # Extract functions
    for m in _PYTHON_FUNC.finditer(content):
        name = m.group(1)
        sig = m.group(2) or ""
        line = content[:m.start()].count("\n")
        node_id = _make_node_id(file_path, name, "function")
        result.nodes.append(ExtractedNode(
            id=node_id, name=name, kind="function",
            file_path=file_path, language="python",
            start_line=line, signature=f"({sig})",
            source_snippet=_extract_snippet(content, line, line + 15),
        ))
        result.edges.append(ExtractedEdge(module_id, node_id, "defines"))

    # Extract imports
    for m in _PYTHON_IMPORT.finditer(content):
        from_mod = m.group(1) or ""
        imports = m.group(2)
        for imp in (i.strip().split(" as ")[0] for i in imports.split(",")):
            if imp:
                target = f"{from_mod}.{imp}" if from_mod else imp
                target_id = f"*::module::{target}"
                result.edges.append(ExtractedEdge(module_id, target_id, "imports"))

    return result


def _extract_javascript(file_path: str, content: str) -> ExtractionResult:
    result = ExtractionResult()
    module_id = _make_node_id(file_path, Path(file_path).stem, "module")
    result.nodes.append(ExtractedNode(
        id=module_id,
        name=Path(file_path).stem,
        kind="module",
        file_path=file_path,
        language="javascript",
    ))

    for m in _JS_CLASS.finditer(content):
        name = m.group(1)
        extends = m.group(2)
        line = content[:m.start()].count("\n")
        node_id = _make_node_id(file_path, name, "class")
        result.nodes.append(ExtractedNode(
            id=node_id, name=name, kind="class",
            file_path=file_path, language="javascript",
            start_line=line,
            source_snippet=_extract_snippet(content, line, line + 30),
        ))
        result.edges.append(ExtractedEdge(module_id, node_id, "defines"))
        if extends:
            result.edges.append(ExtractedEdge(
                node_id, f"*::{extends}", "inherits",
            ))

    for m in _JS_FUNC.finditer(content):
        name = m.group(1) or m.group(2)
        if not name:
            continue
        line = content[:m.start()].count("\n")
        node_id = _make_node_id(file_path, name, "function")
        result.nodes.append(ExtractedNode(
            id=node_id, name=name, kind="function",
            file_path=file_path, language="javascript",
            start_line=line,
            source_snippet=_extract_snippet(content, line, line + 15),
        ))
        result.edges.append(ExtractedEdge(module_id, node_id, "defines"))

    for m in _JS_IMPORT.finditer(content):
        target = m.group(1)
        target_id = f"*::module::{target}"
        result.edges.append(ExtractedEdge(module_id, target_id, "imports"))

    return result


def _extract_markdown(file_path: str, content: str) -> ExtractionResult:
    """Extract structural elements from Markdown files.

    Extracts headings as section nodes, creating a hierarchy.
    Cross-references (links) become edges.
    """
    result = ExtractionResult()
    doc_id = _make_node_id(file_path, Path(file_path).stem, "document")
    result.nodes.append(ExtractedNode(
        id=doc_id,
        name=Path(file_path).stem,
        kind="document",
        file_path=file_path,
        language="markdown",
        source_snippet=content,
    ))

    _MD_HEADING = re.compile(r"^(#{1,6})\s+(.+)", re.MULTILINE)
    _MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    lines = content.splitlines()
    headings: list[tuple[int, str, int]] = []  # (level, text, line_num)

    for i, line in enumerate(lines):
        m = _MD_HEADING.match(line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            headings.append((level, text, i))

    # Create section nodes from headings
    parent_stack: list[str] = [doc_id]
    parent_levels: list[int] = [0]

    for idx, (level, text, line_num) in enumerate(headings):
        section_id = _make_node_id(file_path, text, "section")

        # Determine section end
        end_line = headings[idx + 1][2] - 1 if idx + 1 < len(headings) else len(lines) - 1

        section_content = "\n".join(lines[line_num:end_line + 1])

        result.nodes.append(ExtractedNode(
            id=section_id,
            name=text,
            kind="section",
            file_path=file_path,
            language="markdown",
            start_line=line_num,
            end_line=end_line,
            source_snippet=section_content,
        ))

        # Find parent: pop stack until we find a level < current
        while len(parent_levels) > 1 and parent_levels[-1] >= level:
            parent_stack.pop()
            parent_levels.pop()

        result.edges.append(ExtractedEdge(parent_stack[-1], section_id, "defines"))
        parent_stack.append(section_id)
        parent_levels.append(level)

    # Extract cross-reference links
    for m in _MD_LINK.finditer(content):
        link_text = m.group(1)
        link_target = m.group(2)
        # Only track internal/relative links, not external URLs
        if not link_target.startswith(("http://", "https://", "mailto:")):
            target_name = Path(link_target.split("#")[0]).stem if link_target else link_text
            if target_name:
                result.edges.append(ExtractedEdge(
                    doc_id, f"*::document::{target_name}", "references",
                    confidence="INFERRED",
                ))

    return result


def _extract_pdf(file_path: str, content: str) -> ExtractionResult:
    """Extract text content from PDF files using pymupdf."""
    result = ExtractionResult()
    doc_id = _make_node_id(file_path, Path(file_path).stem, "document")
    result.nodes.append(ExtractedNode(
        id=doc_id,
        name=Path(file_path).stem,
        kind="document",
        file_path=file_path,
        language="pdf",
        source_snippet="[PDF document]",
    ))

    try:
        import pymupdf
    except ImportError:
        result.nodes[0].source_snippet = "[PDF — install pymupdf for text extraction]"
        return result

    try:
        doc = pymupdf.open(file_path)
    except Exception:
        return result

    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text().strip()
        if not text:
            continue

        section_id = _make_node_id(file_path, f"page_{page_num + 1}", "section")
        result.nodes.append(ExtractedNode(
            id=section_id,
            name=f"Page {page_num + 1}",
            kind="section",
            file_path=file_path,
            language="pdf",
            start_line=page_num,
            source_snippet=text,
        ))
        result.edges.append(ExtractedEdge(doc_id, section_id, "defines"))

    doc.close()
    return result


def _extract_html(file_path: str, content: str) -> ExtractionResult:
    """Extract text and structure from HTML files."""
    result = ExtractionResult()
    doc_id = _make_node_id(file_path, Path(file_path).stem, "document")
    result.nodes.append(ExtractedNode(
        id=doc_id,
        name=Path(file_path).stem,
        kind="document",
        file_path=file_path,
        language="html",
        source_snippet=content,
    ))

    try:
        from html.parser import HTMLParser
    except ImportError:
        return result

    class _HeadingParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self._in_heading = False
            self._heading_tag = ""
            self._heading_text = ""
            self._pos = 0
            self.headings: list[tuple[str, str, int]] = []

        def handle_starttag(self, tag, attrs):
            if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
                self._in_heading = True
                self._heading_tag = tag
                self._heading_text = ""
                self._pos = self.getpos()[0]

        def handle_data(self, data):
            if self._in_heading:
                self._heading_text += data

        def handle_endtag(self, tag):
            if self._in_heading and tag == self._heading_tag:
                self._in_heading = False
                text = self._heading_text.strip()
                if text:
                    self.headings.append((self._heading_tag, text, self._pos))

    parser = _HeadingParser()
    try:
        parser.feed(content)
    except Exception:
        return result

    for tag, text, line_num in parser.headings:
        section_id = _make_node_id(file_path, text, "section")
        result.nodes.append(ExtractedNode(
            id=section_id,
            name=text,
            kind="section",
            file_path=file_path,
            language="html",
            start_line=line_num,
            source_snippet=text,
        ))
        result.edges.append(ExtractedEdge(doc_id, section_id, "defines"))

    # Extract links
    _HTML_LINK = re.compile(r'href=["\']([^"\']+)["\']')
    for m in _HTML_LINK.finditer(content):
        href = m.group(1)
        if not href.startswith(("http://", "https://", "mailto:", "#", "javascript:")):
            target_name = Path(href.split("?")[0].split("#")[0]).stem
            if target_name:
                result.edges.append(ExtractedEdge(
                    doc_id, f"*::document::{target_name}", "references",
                    confidence="INFERRED",
                ))

    return result


def _extract_csv(file_path: str, content: str) -> ExtractionResult:
    """Extract structure from CSV/TSV files (headers as schema)."""
    import csv
    import io

    result = ExtractionResult()
    doc_id = _make_node_id(file_path, Path(file_path).stem, "document")

    ext = Path(file_path).suffix.lower()
    delimiter = "\t" if ext == ".tsv" else ","

    try:
        reader = csv.reader(io.StringIO(content), delimiter=delimiter)
        headers = next(reader, None)
    except Exception:
        headers = None

    row_count = content.count("\n")
    header_str = ", ".join(headers) if headers else ""
    snippet = f"Columns: {header_str}\nRows: ~{row_count}" if headers else content[:500]

    result.nodes.append(ExtractedNode(
        id=doc_id,
        name=Path(file_path).stem,
        kind="document",
        file_path=file_path,
        language="csv",
        source_snippet=snippet,
    ))

    if headers:
        for col in headers:
            col = col.strip()
            if col:
                col_id = _make_node_id(file_path, col, "variable")
                result.nodes.append(ExtractedNode(
                    id=col_id,
                    name=col,
                    kind="variable",
                    file_path=file_path,
                    language="csv",
                    source_snippet=f"Column: {col}",
                ))
                result.edges.append(ExtractedEdge(doc_id, col_id, "defines"))

    return result


_EXTRACTORS: dict[str, Any] = {
    "python": _extract_python,
    "javascript": _extract_javascript,
    "typescript": _extract_javascript,  # Close enough for regex fallback
    "markdown": _extract_markdown,
    "pdf": _extract_pdf,
    "html": _extract_html,
    "csv": _extract_csv,
}


def extract_file(file_path: str, language: str, content: str | None = None) -> ExtractionResult:
    """Extract structural elements from a single file.

    Args:
        file_path: Path to the source file.
        language: Programming language identifier.
        content: File content (read from disk if None).

    Returns:
        ExtractionResult with nodes and edges.
    """
    if content is None:
        if language == "pdf":
            content = ""  # PDF uses pymupdf to read binary directly
        else:
            content = Path(file_path).read_text(errors="replace")

    extractor = _EXTRACTORS.get(language)
    if extractor:
        return extractor(file_path, content)

    # Fallback: create a module node only
    result = ExtractionResult()
    module_id = _make_node_id(file_path, Path(file_path).stem, "module")
    result.nodes.append(ExtractedNode(
        id=module_id,
        name=Path(file_path).stem,
        kind="module",
        file_path=file_path,
        language=language,
        source_snippet=content,
    ))
    return result
