"""Tree-sitter based AST extraction for accurate structural analysis.

Replaces regex-based extraction with proper AST parsing.
Supports Python, JavaScript, TypeScript with full method/class/import resolution.
Falls back to regex extractor for unsupported languages.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from hedwig_kg.core.extract import (
    ExtractedEdge,
    ExtractedNode,
    ExtractionResult,
    _extract_snippet,
    _make_node_id,
)
from hedwig_kg.core.extract import (
    extract_file as regex_extract_file,
)

logger = logging.getLogger(__name__)

# Lazy-loaded parsers
_parsers: dict[str, Any] = {}
_languages: dict[str, Any] = {}


def _ensure_parser(language: str) -> bool:
    """Initialize tree-sitter parser for a language. Returns True if available."""
    if language in _parsers:
        return True

    try:
        from tree_sitter import Language, Parser

        lang_obj = None

        # Try language-specific packages
        try:
            if language == "python":
                import tree_sitter_python as tslang
                lang_obj = Language(tslang.language())
            elif language == "javascript":
                import tree_sitter_javascript as tslang
                lang_obj = Language(tslang.language())
            elif language == "typescript":
                try:
                    import tree_sitter_typescript as tslang
                    if hasattr(tslang, 'language_typescript'):
                        lang_obj = Language(tslang.language_typescript())
                    else:
                        lang_obj = Language(tslang.language())
                except ImportError:
                    # Fall back to javascript parser for typescript
                    import tree_sitter_javascript as tslang
                    lang_obj = Language(tslang.language())
                    language = "javascript"
        except ImportError:
            pass

        # Fallback: try tree_sitter_language_pack
        if lang_obj is None:
            try:
                from tree_sitter_language_pack import get_language
                lang_obj = get_language(language)
            except ImportError:
                pass

        if lang_obj is None:
            return False

        parser = Parser(lang_obj)
        _parsers[language] = parser
        _languages[language] = lang_obj
        return True

    except Exception as e:
        logger.debug(f"tree-sitter not available for {language}: {e}")
        return False


def _get_node_text(node, source_bytes: bytes) -> str:
    """Extract text from a tree-sitter node."""
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _find_docstring(node, source_bytes: bytes) -> str:
    """Extract docstring from a function/class body."""
    body = None
    for child in node.children:
        if child.type == "block" or child.type == "statement_block":
            body = child
            break

    if body is None:
        return ""

    for child in body.children:
        if child.type == "expression_statement":
            for sub in child.children:
                if sub.type == "string" or sub.type == "concatenated_string":
                    text = _get_node_text(sub, source_bytes)
                    # Strip triple quotes
                    for q in ('"""', "'''", '"""', "'''"):
                        if text.startswith(q) and text.endswith(q):
                            return text[3:-3].strip()
                    return text.strip("\"'").strip()
        elif child.type not in ("comment", "newline", "NEWLINE", "INDENT", "DEDENT"):
            break
    return ""


def _extract_python_ts(file_path: str, content: str) -> ExtractionResult:
    """Extract Python structures using tree-sitter AST."""
    parser = _parsers["python"]
    source_bytes = content.encode("utf-8")
    tree = parser.parse(source_bytes)
    root = tree.root_node

    result = ExtractionResult()
    module_id = _make_node_id(file_path, Path(file_path).stem, "module")
    result.nodes.append(ExtractedNode(
        id=module_id,
        name=Path(file_path).stem,
        kind="module",
        file_path=file_path,
        language="python",
    ))

    def _process_class(node, parent_id: str, prefix: str = ""):
        """Process a class definition, including nested classes and methods."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _get_node_text(name_node, source_bytes)
        full_name = f"{prefix}{name}" if prefix else name
        node_id = _make_node_id(file_path, full_name, "class")

        # Decorators live on the parent decorated_definition, not on class_definition
        decorators = []
        parent = node.parent
        if parent and parent.type == "decorated_definition":
            for child in parent.children:
                if child.type == "decorator":
                    decorators.append(_get_node_text(child, source_bytes).lstrip("@"))

        # Bases
        bases_node = node.child_by_field_name("superclasses")
        if bases_node is None:
            # Try argument_list for bases
            for child in node.children:
                if child.type == "argument_list":
                    bases_node = child
                    break

        result.nodes.append(ExtractedNode(
            id=node_id,
            name=full_name,
            kind="class",
            file_path=file_path,
            language="python",
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            docstring=_find_docstring(node, source_bytes),
            source_snippet=_extract_snippet(content, node.start_point[0], node.end_point[0]),
            decorators=decorators,
        ))
        result.edges.append(ExtractedEdge(parent_id, node_id, "defines"))

        # Inheritance edges
        if bases_node:
            for child in bases_node.children:
                if child.type in ("identifier", "attribute"):
                    base_name = _get_node_text(child, source_bytes)
                    if base_name not in (",", "(", ")"):
                        result.edges.append(ExtractedEdge(
                            node_id, f"*::class::{base_name}", "inherits"
                        ))

        # Process body for methods and nested classes
        for child in node.children:
            if child.type == "block":
                for stmt in child.children:
                    if stmt.type == "function_definition":
                        _process_function(stmt, node_id, prefix=f"{full_name}.")
                    elif stmt.type == "class_definition":
                        _process_class(stmt, node_id, prefix=f"{full_name}.")
                    elif stmt.type == "decorated_definition":
                        for sub in stmt.children:
                            if sub.type == "function_definition":
                                _process_function(sub, node_id, prefix=f"{full_name}.")
                            elif sub.type == "class_definition":
                                _process_class(sub, node_id, prefix=f"{full_name}.")

    def _process_function(node, parent_id: str, prefix: str = ""):
        """Process a function/method definition."""
        name_node = node.child_by_field_name("name")
        if not name_node:
            return
        name = _get_node_text(name_node, source_bytes)
        full_name = f"{prefix}{name}" if prefix else name

        # Determine kind
        kind = "method" if parent_id and "::class::" in parent_id else "function"

        node_id = _make_node_id(file_path, full_name, kind)

        # Decorators (collected from the parent decorated_definition node)
        decorators = []
        parent = node.parent
        if parent and parent.type == "decorated_definition":
            for child in parent.children:
                if child.type == "decorator":
                    decorators.append(_get_node_text(child, source_bytes).lstrip("@"))

        # Parameters
        params_node = node.child_by_field_name("parameters")
        sig = _get_node_text(params_node, source_bytes) if params_node else "()"

        # Return type
        return_type = ""
        ret_node = node.child_by_field_name("return_type")
        if ret_node:
            return_type = _get_node_text(ret_node, source_bytes)

        result.nodes.append(ExtractedNode(
            id=node_id,
            name=full_name,
            kind=kind,
            file_path=file_path,
            language="python",
            start_line=node.start_point[0],
            end_line=node.end_point[0],
            docstring=_find_docstring(node, source_bytes),
            signature=f"{sig} -> {return_type}" if return_type else sig,
            source_snippet=_extract_snippet(content, node.start_point[0], node.end_point[0]),
            decorators=decorators,
        ))
        result.edges.append(ExtractedEdge(parent_id, node_id, "defines"))

        # Extract function calls within the body
        _extract_calls(node, node_id, source_bytes)

    def _extract_calls(node, caller_id: str, source_bytes: bytes):
        """Extract function/method calls from a node's body."""
        for child in node.children:
            if child.type == "call":
                func_node = child.child_by_field_name("function")
                if func_node:
                    call_name = _get_node_text(func_node, source_bytes)
                    # Skip common builtins
                    if call_name not in ("print", "len", "str", "int", "float", "bool",
                                         "list", "dict", "set", "tuple", "range", "type",
                                         "isinstance", "issubclass", "getattr", "setattr",
                                         "hasattr", "super", "property", "staticmethod",
                                         "classmethod", "enumerate", "zip", "map", "filter",
                                         "sorted", "reversed", "min", "max", "sum", "any", "all"):
                        # Use the last part for method calls (e.g., self.foo -> foo)
                        target_name = call_name.split(".")[-1] if "." in call_name else call_name
                        result.edges.append(ExtractedEdge(
                            caller_id, f"*::{target_name}", "calls",
                            confidence="INFERRED",
                        ))
            _extract_calls(child, caller_id, source_bytes)

    def _process_import(node):
        """Process import statements."""
        if node.type == "import_statement":
            for child in node.children:
                if child.type == "dotted_name":
                    mod = _get_node_text(child, source_bytes)
                    result.edges.append(ExtractedEdge(
                        module_id, f"*::module::{mod}", "imports"
                    ))
        elif node.type == "import_from_statement":
            module_name = ""
            for child in node.children:
                if child.type == "dotted_name" or child.type == "relative_import":
                    module_name = _get_node_text(child, source_bytes)
                    break
            # Get imported names
            for child in node.children:
                if child.type == "import_prefix":
                    continue
                if child.type in ("dotted_name", "identifier") and child != node.children[1]:
                    imp_name = _get_node_text(child, source_bytes)
                    if imp_name not in ("import", "from", ",", module_name):
                        target = f"{module_name}.{imp_name}" if module_name else imp_name
                        result.edges.append(ExtractedEdge(
                            module_id, f"*::module::{target}", "imports"
                        ))

    # Walk top-level statements
    for child in root.children:
        if child.type == "class_definition":
            _process_class(child, module_id)
        elif child.type == "function_definition":
            _process_function(child, module_id)
        elif child.type == "decorated_definition":
            for sub in child.children:
                if sub.type == "class_definition":
                    _process_class(sub, module_id)
                elif sub.type == "function_definition":
                    _process_function(sub, module_id)
        elif child.type in ("import_statement", "import_from_statement"):
            _process_import(child)
        elif child.type == "expression_statement":
            # Top-level assignments (constants, etc.)
            for sub in child.children:
                if sub.type == "assignment":
                    left = sub.child_by_field_name("left")
                    if left and left.type == "identifier":
                        var_name = _get_node_text(left, source_bytes)
                        if var_name.isupper() or var_name.startswith("_"):
                            var_id = _make_node_id(file_path, var_name, "variable")
                            result.nodes.append(ExtractedNode(
                                id=var_id,
                                name=var_name,
                                kind="variable",
                                file_path=file_path,
                                language="python",
                                start_line=sub.start_point[0],
                                source_snippet=_extract_snippet(
                                    content, sub.start_point[0],
                                    sub.start_point[0] + 3),
                            ))
                            result.edges.append(ExtractedEdge(module_id, var_id, "defines"))

    return result


def _extract_js_ts(file_path: str, content: str, language: str) -> ExtractionResult:
    """Extract JS/TS structures using tree-sitter AST."""
    parser = _parsers[language]
    source_bytes = content.encode("utf-8")
    tree = parser.parse(source_bytes)
    root = tree.root_node

    result = ExtractionResult()
    module_id = _make_node_id(file_path, Path(file_path).stem, "module")
    result.nodes.append(ExtractedNode(
        id=module_id,
        name=Path(file_path).stem,
        kind="module",
        file_path=file_path,
        language=language,
    ))

    # JS/TS builtins to skip in call extraction
    _JS_BUILTINS = frozenset({
        "console", "require", "parseInt", "parseFloat", "isNaN", "isFinite",
        "setTimeout", "setInterval", "clearTimeout", "clearInterval",
        "JSON", "Object", "Array", "String", "Number", "Boolean", "Symbol",
        "Promise", "Map", "Set", "WeakMap", "WeakSet", "Date", "Math",
        "Error", "TypeError", "RangeError", "RegExp",
    })

    def _extract_js_calls(node, caller_id: str):
        """Extract function/method calls from a JS/TS node's body."""
        for child in node.children:
            if child.type == "call_expression":
                func_node = child.child_by_field_name("function")
                if func_node:
                    call_text = _get_node_text(func_node, source_bytes)
                    # Get the base name for filtering
                    parts = call_text.split(".")
                    base = parts[0]
                    target = parts[-1] if len(parts) > 1 else base
                    # Skip builtins and common patterns
                    if base not in _JS_BUILTINS and target not in _JS_BUILTINS:
                        result.edges.append(ExtractedEdge(
                            caller_id, f"*::{target}", "calls",
                            confidence="INFERRED",
                        ))
            _extract_js_calls(child, caller_id)

    def _process_node(node, parent_id: str, prefix: str = ""):
        """Recursively process AST nodes."""
        if node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _get_node_text(name_node, source_bytes)
                full_name = f"{prefix}{name}" if prefix else name
                node_id = _make_node_id(file_path, full_name, "class")
                result.nodes.append(ExtractedNode(
                    id=node_id, name=full_name, kind="class",
                    file_path=file_path, language=language,
                    start_line=node.start_point[0],
                    end_line=node.end_point[0],
                    source_snippet=_extract_snippet(
                        content, node.start_point[0], node.end_point[0]),
                ))
                result.edges.append(ExtractedEdge(parent_id, node_id, "defines"))

                # Heritage (extends/implements)
                for child in node.children:
                    if child.type == "class_heritage":
                        for sub in child.children:
                            if sub.type == "identifier":
                                base = _get_node_text(sub, source_bytes)
                                if base not in ("extends", "implements"):
                                    result.edges.append(ExtractedEdge(
                                        node_id, f"*::class::{base}", "inherits"
                                    ))

                # Process class body
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        _process_node(child, node_id, prefix=f"{full_name}.")

        elif node.type in ("function_declaration", "method_definition",
                           "arrow_function", "function"):
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _get_node_text(name_node, source_bytes)
            elif node.parent and node.parent.type == "variable_declarator":
                name_n = node.parent.child_by_field_name("name")
                name = _get_node_text(name_n, source_bytes) if name_n else None
            else:
                name = None

            if name:
                full_name = f"{prefix}{name}" if prefix else name
                kind = "method" if "::class::" in parent_id else "function"
                node_id = _make_node_id(file_path, full_name, kind)

                params_node = node.child_by_field_name("parameters")
                sig = _get_node_text(params_node, source_bytes) if params_node else "()"

                result.nodes.append(ExtractedNode(
                    id=node_id, name=full_name, kind=kind,
                    file_path=file_path, language=language,
                    start_line=node.start_point[0],
                    end_line=node.end_point[0],
                    signature=sig,
                    source_snippet=_extract_snippet(
                        content, node.start_point[0], node.end_point[0]),
                ))
                result.edges.append(ExtractedEdge(parent_id, node_id, "defines"))

                # Extract function/method calls within the body
                _extract_js_calls(node, node_id)

        elif node.type == "import_statement":
            source_node = node.child_by_field_name("source")
            if source_node:
                mod = _get_node_text(source_node, source_bytes).strip("\"'")
                result.edges.append(ExtractedEdge(
                    module_id, f"*::module::{mod}", "imports"
                ))

        elif node.type == "lexical_declaration" or node.type == "variable_declaration":
            for child in node.children:
                if child.type == "variable_declarator":
                    name_node = child.child_by_field_name("name")
                    value_node = child.child_by_field_name("value")
                    if name_node:
                        name = _get_node_text(name_node, source_bytes)
                        # Check if it's an arrow function or function expression
                        if value_node and value_node.type in ("arrow_function", "function"):
                            _process_node(value_node, parent_id, prefix)
                        elif name.upper() == name and len(name) > 1:
                            # Constants
                            var_id = _make_node_id(file_path, name, "variable")
                            result.nodes.append(ExtractedNode(
                                id=var_id, name=name, kind="variable",
                                file_path=file_path, language=language,
                                start_line=node.start_point[0],
                                source_snippet=_extract_snippet(
                                    content, node.start_point[0],
                                    node.start_point[0] + 3),
                            ))
                            result.edges.append(ExtractedEdge(parent_id, var_id, "defines"))

        elif node.type == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _get_node_text(name_node, source_bytes)
                full_name = f"{prefix}{name}" if prefix else name
                node_id = _make_node_id(file_path, full_name, "interface")
                result.nodes.append(ExtractedNode(
                    id=node_id, name=full_name, kind="interface",
                    file_path=file_path, language=language,
                    start_line=node.start_point[0],
                    end_line=node.end_point[0],
                    source_snippet=_extract_snippet(
                        content, node.start_point[0], node.end_point[0]),
                ))
                result.edges.append(ExtractedEdge(parent_id, node_id, "defines"))

                # extends clause
                for child in node.children:
                    if child.type == "extends_type_clause":
                        for sub in child.children:
                            if sub.type in ("type_identifier", "identifier"):
                                base = _get_node_text(sub, source_bytes)
                                if base != "extends":
                                    result.edges.append(ExtractedEdge(
                                        node_id, f"*::interface::{base}",
                                        "extends",
                                    ))

                # Process interface body for method signatures
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        if child.type in ("method_signature",
                                          "property_signature"):
                            sig_name = child.child_by_field_name("name")
                            if sig_name:
                                sname = _get_node_text(sig_name, source_bytes)
                                sfull = f"{full_name}.{sname}"
                                skind = ("method" if child.type
                                         == "method_signature"
                                         else "property")
                                sid = _make_node_id(
                                    file_path, sfull, skind)
                                result.nodes.append(ExtractedNode(
                                    id=sid, name=sfull, kind=skind,
                                    file_path=file_path, language=language,
                                    start_line=child.start_point[0],
                                ))
                                result.edges.append(ExtractedEdge(
                                    node_id, sid, "defines"))

        elif node.type == "type_alias_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _get_node_text(name_node, source_bytes)
                full_name = f"{prefix}{name}" if prefix else name
                node_id = _make_node_id(file_path, full_name, "type_alias")
                result.nodes.append(ExtractedNode(
                    id=node_id, name=full_name, kind="type_alias",
                    file_path=file_path, language=language,
                    start_line=node.start_point[0],
                    end_line=node.end_point[0],
                    source_snippet=_extract_snippet(
                        content, node.start_point[0], node.end_point[0]),
                ))
                result.edges.append(ExtractedEdge(parent_id, node_id, "defines"))

        elif node.type == "enum_declaration":
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _get_node_text(name_node, source_bytes)
                full_name = f"{prefix}{name}" if prefix else name
                node_id = _make_node_id(file_path, full_name, "enum")
                result.nodes.append(ExtractedNode(
                    id=node_id, name=full_name, kind="enum",
                    file_path=file_path, language=language,
                    start_line=node.start_point[0],
                    end_line=node.end_point[0],
                    source_snippet=_extract_snippet(
                        content, node.start_point[0], node.end_point[0]),
                ))
                result.edges.append(ExtractedEdge(parent_id, node_id, "defines"))

                # Enum members
                body = node.child_by_field_name("body")
                if body:
                    for child in body.children:
                        if child.type == "enum_assignment":
                            mem_name = child.child_by_field_name("name")
                            if mem_name:
                                mname = _get_node_text(mem_name, source_bytes)
                                mfull = f"{full_name}.{mname}"
                                mid = _make_node_id(
                                    file_path, mfull, "variable")
                                result.nodes.append(ExtractedNode(
                                    id=mid, name=mfull, kind="variable",
                                    file_path=file_path, language=language,
                                    start_line=child.start_point[0],
                                ))
                                result.edges.append(ExtractedEdge(
                                    node_id, mid, "defines"))

        elif node.type == "export_statement":
            for child in node.children:
                _process_node(child, parent_id, prefix)

        # Recurse into other compound statements
        elif node.type in ("program", "statement_block", "if_statement",
                           "for_statement", "while_statement", "try_statement"):
            for child in node.children:
                _process_node(child, parent_id, prefix)

    for child in root.children:
        _process_node(child, module_id)

    return result


def extract_file_ts(file_path: str, language: str, content: str | None = None) -> ExtractionResult:
    """Extract structural elements using tree-sitter when available, regex as fallback.

    Args:
        file_path: Path to the source file.
        language: Programming language identifier.
        content: File content (read from disk if None).

    Returns:
        ExtractionResult with nodes and edges.
    """
    if content is None:
        content = Path(file_path).read_text(errors="replace")

    # Try tree-sitter first
    ts_lang = language
    if language == "typescript":
        # Try as javascript if typescript parser not available
        if not _ensure_parser("typescript"):
            ts_lang = "javascript"

    if _ensure_parser(ts_lang):
        try:
            if ts_lang == "python":
                return _extract_python_ts(file_path, content)
            elif ts_lang in ("javascript", "typescript"):
                return _extract_js_ts(file_path, content, ts_lang)
        except Exception as e:
            logger.warning(
                "tree-sitter extraction failed for %s: %s, "
                "falling back to regex", file_path, e)

    # Fallback to regex extraction
    return regex_extract_file(file_path, language, content)
