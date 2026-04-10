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


def _extract_snippet(content: str, start: int, end: int, max_lines: int = 10) -> str:
    lines = content.splitlines()
    snippet_lines = lines[start:min(end, start + max_lines)]
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
        source_snippet=content[:500],
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

        section_content = "\n".join(lines[line_num:min(line_num + 15, end_line + 1)])

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


_EXTRACTORS: dict[str, Any] = {
    "python": _extract_python,
    "javascript": _extract_javascript,
    "typescript": _extract_javascript,  # Close enough for regex fallback
    "markdown": _extract_markdown,
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
        source_snippet=content[:500],
    ))
    return result
