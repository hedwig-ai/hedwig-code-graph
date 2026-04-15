"""Universal tree-sitter tags.scm based extraction.

Uses the standard @definition.* / @reference.* captures from each language's
tags.scm file to extract structural nodes and edges without per-language
AST walking code.  Supplementary queries (imports, inheritance) are added
per-language as small query snippets.

Requires py-tree-sitter >= 0.23 (QueryCursor API).
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any

from tree_sitter import Language, Parser, Query, QueryCursor

from hedwig_cg.core.extract import (
    MAX_SNIPPET_CHARS,
    ExtractedEdge,
    ExtractedNode,
    ExtractionResult,
    _make_node_id,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Capture name → ExtractedNode.kind mapping (language-agnostic)
# ---------------------------------------------------------------------------

_CAPTURE_TO_KIND: dict[str, str] = {
    "definition.function": "function",
    "definition.class": "class",
    "definition.method": "method",
    "definition.interface": "interface",
    "definition.module": "module",
    "definition.constant": "variable",
    "definition.macro": "function",
    "definition.type": "class",
}

_REFERENCE_CAPTURES: dict[str, tuple[str, str]] = {
    # capture_name → (edge_relation, target_prefix)
    "reference.call": ("calls", "*::"),
    "reference.class": ("references", "*::class::"),
    "reference.implementation": ("implements", "*::interface::"),
}

# ---------------------------------------------------------------------------
# Language name → tree_sitter package name mapping
# ---------------------------------------------------------------------------

_LANG_TO_PACKAGE: dict[str, str] = {
    "cpp": "cpp",
    "c_sharp": "c_sharp",
    "csharp": "c_sharp",
    "typescript": "typescript",
    "php": "php",
    "objc": "objc",
    "objective-c": "objc",
    "kotlin": "kotlin",
}

# Packages that use non-standard language() function names
_LANG_FUNC_NAME: dict[str, str] = {
    "typescript": "language_typescript",
    "php": "language_php",
}

# ---------------------------------------------------------------------------
# Supplementary queries: imports & inheritance per language
# ---------------------------------------------------------------------------

_IMPORT_QUERIES: dict[str, str] = {
    "python": """
        (import_statement
          name: (dotted_name) @name) @_import
        (import_from_statement
          module_name: (dotted_name) @name) @_import
    """,
    "javascript": """
        (import_statement
          source: (string) @name) @_import
    """,
    "typescript": """
        (import_statement
          source: (string) @name) @_import
    """,
    "go": """
        (import_spec
          path: (interpreted_string_literal) @name) @_import
    """,
    "rust": """
        (use_declaration
          argument: (_) @name) @_import
    """,
    "java": """
        (import_declaration
          (scoped_identifier) @name) @_import
    """,
    "ruby": """
        (call
          method: (identifier) @_method
          arguments: (argument_list (string) @name)
          (#match? @_method "^require"))
    """,
    "c": """
        (preproc_include
          path: (_) @name) @_import
    """,
    "cpp": """
        (preproc_include
          path: (_) @name) @_import
    """,
    "php": """
        (namespace_use_declaration
          (namespace_use_clause (qualified_name) @name)) @_import
    """,
    "swift": """
        (import_declaration
          (identifier) @name) @_import
    """,
    "scala": """
        (import_declaration
          path: (_) @name) @_import
    """,
    "lua": """
        (function_call
          name: (identifier) @_fn
          arguments: (arguments (string) @name)
          (#match? @_fn "^require$"))
    """,
    "elixir": """
        (call
          target: (identifier) @_fn
          (arguments (alias) @name)
          (#match? @_fn "^(import|use|alias|require)$"))
    """,
    "c_sharp": """
        (using_directive
          (_) @name) @_import
    """,
    "kotlin": """
        (import
          (qualified_identifier) @name) @_import
    """,
    "objc": """
        (preproc_include
          path: (_) @name) @_import
    """,
}

_INHERITANCE_QUERIES: dict[str, str] = {
    "python": """
        (class_definition
          superclasses: (argument_list
            (identifier) @name)) @_inherits
    """,
    "javascript": """
        (class_declaration
          (class_heritage
            (identifier) @name)) @_inherits
        (class
          (class_heritage
            (identifier) @name)) @_inherits
    """,
    "typescript": """
        (class_declaration
          (class_heritage
            (identifier) @name)) @_inherits
    """,
    "java": """
        (class_declaration
          (superclass
            (type_identifier) @name)) @_inherits
        (class_declaration
          (super_interfaces
            (type_list
              (type_identifier) @name))) @_inherits
    """,
    "rust": """
        (impl_item
          trait: (type_identifier) @name) @_inherits
    """,
    "go": """
        (type_declaration
          (type_spec
            type: (struct_type
              (field_declaration_list
                (field_declaration
                  type: (type_identifier) @name))))) @_inherits
    """,
    "ruby": """
        (class
          superclass: (superclass
            (scope_resolution) @name)) @_inherits
    """,
    "cpp": """
        (class_specifier
          (base_class_clause
            (type_identifier) @name)) @_inherits
    """,
    "swift": """
        (class_declaration
          (type_identifier) @name) @_inherits
    """,
    "scala": """
        (class_definition
          extend: (extends_clause
            (type_identifier) @name)) @_inherits
    """,
    "php": """
        (class_declaration
          (base_clause
            (qualified_name) @name)) @_inherits
    """,
    "c_sharp": """
        (class_declaration
          (base_list (_) @name)) @_inherits
    """,
    "kotlin": """
        (class_declaration
          (delegation_specifiers
            (delegation_specifier
              (user_type
                (identifier) @name)))) @_inherits
    """,
    "objc": """
        (class_interface
          superclass: (identifier) @name) @_inherits
    """,
}

# ---------------------------------------------------------------------------
# Lazy-loaded parsers and tag queries cache
# ---------------------------------------------------------------------------

_cache: dict[str, dict[str, Any] | None] = {}


def _get_lang_resources(language: str) -> dict[str, Any] | None:
    """Load parser, Language object, and TAGS_QUERY for a language.

    Handles three cases:
    1. Standard packages: mod.language() + mod.TAGS_QUERY
    2. Special packages (TS/PHP): mod.language_typescript() etc.
    3. Packages with tags.scm file but no TAGS_QUERY attribute

    Returns dict with keys: parser, lang_obj, tags_query_str, or None.
    """
    if language in _cache:
        return _cache[language]

    pkg_name = _LANG_TO_PACKAGE.get(language, language)

    try:
        mod = importlib.import_module(f"tree_sitter_{pkg_name}")
    except ImportError:
        _cache[language] = None
        return None

    try:
        # Get the language function (standard or custom name)
        lang_func_name = _LANG_FUNC_NAME.get(language, "language")
        lang_func = getattr(mod, lang_func_name, None)
        if lang_func is None:
            _cache[language] = None
            return None

        lang_obj = Language(lang_func())
        parser = Parser(lang_obj)

        # Try getting TAGS_QUERY: attribute first, then file fallback
        tags_query_str = getattr(mod, "TAGS_QUERY", None)

        # TypeScript: combine JS tags (has class/function) + TS tags (has interface/type)
        if language == "typescript":
            tags_query_str = _build_typescript_tags()

        if tags_query_str is None:
            # Try loading from queries/tags.scm file in the package
            tags_query_str = _load_tags_file(pkg_name)

        if tags_query_str is None:
            _cache[language] = None
            return None

        res: dict[str, Any] = {
            "parser": parser,
            "lang_obj": lang_obj,
            "tags_query_str": tags_query_str,
        }
        _cache[language] = res
        return res
    except Exception as e:
        logger.debug("Failed to load tree-sitter for %s: %s", language, e)
        _cache[language] = None
        return None


def _build_typescript_tags() -> str | None:
    """Build a TS tags query from TS-native tags + simplified JS patterns.

    TS's own tags.scm only covers .d.ts patterns (signatures, abstract).
    JS tags.scm has richer patterns but uses #select-adjacent! predicates
    that fail with the TS parser.  We use stripped-down JS patterns instead.
    """
    try:
        import tree_sitter_typescript
        ts_tags = getattr(tree_sitter_typescript, "TAGS_QUERY", "")
    except ImportError:
        return None

    # Simplified JS-compatible patterns (no #select-adjacent! predicates)
    js_compat = """
; --- JS-compatible patterns for TypeScript ---

(method_definition
  name: (property_identifier) @name) @definition.method

[
  (class
    name: (_) @name)
  (class_declaration
    name: (_) @name)
] @definition.class

[
  (function_expression
    name: (identifier) @name)
  (function_declaration
    name: (identifier) @name)
  (generator_function
    name: (identifier) @name)
  (generator_function_declaration
    name: (identifier) @name)
] @definition.function

(lexical_declaration
  (variable_declarator
    name: (identifier) @name
    value: [(arrow_function) (function_expression)])) @definition.function

(variable_declaration
  (variable_declarator
    name: (identifier) @name
    value: [(arrow_function) (function_expression)])) @definition.function

(assignment_expression
  left: [
    (identifier) @name
    (member_expression
      property: (property_identifier) @name)
  ]
  right: [(arrow_function) (function_expression)]
) @definition.function

(pair
  key: (property_identifier) @name
  value: [(arrow_function) (function_expression)]) @definition.function

(call_expression
  function: (identifier) @name) @reference.call

(call_expression
  function: (member_expression
    property: (property_identifier) @name)
  arguments: (_) @reference.call)

(new_expression
  constructor: (_) @name) @reference.class

(export_statement value: (assignment_expression left: (identifier) @name right: ([
 (number)
 (string)
 (identifier)
 (undefined)
 (null)
 (new_expression)
 (binary_expression)
 (call_expression)
]))) @definition.constant
"""
    combined = js_compat + "\n" + ts_tags
    return combined if combined.strip() else None


def _load_tags_file(pkg_name: str) -> str | None:
    """Load tags.scm from a package's queries/ directory or local fallback.

    Search order:
    1. tree_sitter_{pkg_name}/queries/tags.scm (inside installed package)
    2. hedwig_cg/queries/{pkg_name}-tags.scm (local custom queries)
    """
    # Try installed package first
    try:
        from importlib.resources import files
        tags_path = files(f"tree_sitter_{pkg_name}") / "queries" / "tags.scm"
        if tags_path.is_file():
            return tags_path.read_text()
    except Exception:
        pass

    # Fallback: local queries directory
    try:
        local_path = Path(__file__).parent.parent / "queries" / f"{pkg_name}-tags.scm"
        if local_path.is_file():
            return local_path.read_text()
    except Exception:
        pass

    return None


def _make_query(lang_obj: Language, query_str: str) -> Query | None:
    """Compile a tree-sitter query, returning None on error."""
    try:
        return Query(lang_obj, query_str)
    except Exception as e:
        logger.debug("Query compile failed: %s  query=%r", e, query_str[:80])
        return None


def _run_matches(
    query: Query, root_node: Any,
) -> list[tuple[int, dict[str, list[Any]]]]:
    """Run query.matches() via QueryCursor."""
    cursor = QueryCursor(query)
    return cursor.matches(root_node)


def _run_captures(
    query: Query, root_node: Any,
) -> dict[str, list[Any]]:
    """Run query.captures() via QueryCursor."""
    cursor = QueryCursor(query)
    return cursor.captures(root_node)


def _node_text(node: Any, source_bytes: bytes) -> str:
    """Extract text from a tree-sitter node."""
    return source_bytes[node.start_byte:node.end_byte].decode(
        "utf-8", errors="replace",
    )


# ---------------------------------------------------------------------------
# Core extraction logic
# ---------------------------------------------------------------------------

def extract_file_tags(
    file_path: str,
    language: str,
    content: str | None = None,
) -> ExtractionResult | None:
    """Extract nodes and edges using tags.scm captures.

    Uses QueryCursor.matches() which returns each pattern match with
    its captures grouped together (e.g. @definition.function + @name
    come as a single match).

    Returns ExtractionResult, or None if the language has no tags.scm.
    """
    res = _get_lang_resources(language)
    if res is None:
        return None

    parser: Parser = res["parser"]
    lang_obj: Language = res["lang_obj"]
    tags_query_str: str = res["tags_query_str"]

    tags_query = _make_query(lang_obj, tags_query_str)
    if tags_query is None:
        return None

    if content is None:
        content = Path(file_path).read_text(errors="replace")

    source_bytes = content.encode("utf-8")
    tree = parser.parse(source_bytes)
    root = tree.root_node

    result = ExtractionResult()

    # Module node
    module_id = _make_node_id(file_path, Path(file_path).stem, "module")
    result.nodes.append(ExtractedNode(
        id=module_id,
        name=Path(file_path).stem,
        kind="module",
        file_path=file_path,
        language=language,
    ))

    # --- Phase 1: tags.scm matches ---
    try:
        matches = _run_matches(tags_query, root)
    except Exception as e:
        logger.debug("tags.scm match failed for %s: %s", file_path, e)
        return None

    # Collect definitions and references from matches
    definitions: list[dict[str, Any]] = []

    for _pattern_idx, match_dict in matches:
        # Each match_dict maps capture names → list[Node]
        # Find which capture is a definition or reference
        def_capture = None
        def_kind = None
        ref_capture = None
        ref_info = None
        name_text = ""
        doc_text = ""

        for cap_name, nodes in match_dict.items():
            if cap_name == "name" and nodes:
                name_text = _node_text(nodes[0], source_bytes)
            elif cap_name == "doc" and nodes:
                raw = _node_text(nodes[0], source_bytes)
                # Clean comment markers
                for prefix in ("/**", "/*", "*/", "///", "//", "#"):
                    raw = raw.strip(prefix)
                doc_text = raw.strip().strip("*").strip()
            elif cap_name in _CAPTURE_TO_KIND and nodes:
                def_capture = nodes[0]
                def_kind = _CAPTURE_TO_KIND[cap_name]
            elif cap_name in _REFERENCE_CAPTURES and nodes:
                ref_capture = nodes[0]
                ref_info = _REFERENCE_CAPTURES[cap_name]

        if not name_text:
            continue

        # Process definition
        if def_capture is not None and def_kind is not None:
            node_id = _make_node_id(
                file_path, name_text, def_kind,
                start_line=def_capture.start_point[0] + 1,  # 1-based行番号
            )

            # Full source for the node (no snippet limit)
            full_source = _node_text(def_capture, source_bytes)

            # Extract signature from AST (parameters node)
            signature = _extract_signature(def_capture, source_bytes)

            result.nodes.append(ExtractedNode(
                id=node_id,
                name=name_text,
                kind=def_kind,
                file_path=file_path,
                language=language,
                start_line=def_capture.start_point[0],
                end_line=def_capture.end_point[0],
                docstring=doc_text,
                signature=signature,
                # ソーススニペットを最大文字数で切り詰める
                source_snippet=full_source[:MAX_SNIPPET_CHARS],
            ))
            definitions.append({
                "node_id": node_id,
                "name": name_text,
                "kind": def_kind,
                "start_byte": def_capture.start_byte,
                "end_byte": def_capture.end_byte,
            })

        # Process reference
        elif ref_capture is not None and ref_info is not None:
            relation, target_prefix = ref_info
            clean_name = (
                name_text.split(".")[-1] if "." in name_text else name_text
            )
            # Find enclosing definition as the caller
            caller_id = _find_enclosing(
                ref_capture, definitions, module_id,
            )
            result.edges.append(ExtractedEdge(
                caller_id,
                f"{target_prefix}{clean_name}",
                relation,
                confidence="INFERRED",
            ))

    # Build containment edges (parent → child via byte range nesting)
    # Also prefix method/function names with parent class name (e.g. Dog.bark)
    defs_sorted = sorted(definitions, key=lambda d: d["start_byte"])
    stack: list[dict[str, Any]] = []
    for d in defs_sorted:
        while stack and stack[-1]["end_byte"] <= d["start_byte"]:
            stack.pop()
        parent = stack[-1] if stack else None
        parent_id = parent["node_id"] if parent else module_id

        # Prefix method names with parent class/interface (e.g. "bark" → "Dog.bark")
        is_container = parent and parent["kind"] in ("class", "interface")
        if is_container and d["kind"] in ("method", "function"):
            old_name = d["name"]
            new_name = f"{parent['name']}.{old_name}"
            old_id = d["node_id"]
            # リネームされたメソッドの開始行を取得（1-based行番号で渡す）
            _rename_start = 1
            for node in result.nodes:
                if node.id == old_id:
                    _rename_start = node.start_line + 1
                    break
            new_id = _make_node_id(file_path, new_name, d["kind"], start_line=_rename_start)
            # Update the node in result
            for node in result.nodes:
                if node.id == old_id:
                    node.name = new_name
                    node.id = new_id
                    break
            d["node_id"] = new_id
            d["name"] = new_name

        result.edges.append(ExtractedEdge(parent_id, d["node_id"], "defines"))
        stack.append(d)

    # --- Phase 2: Supplementary constants (JS/TS: const UPPER_CASE = ...) ---
    _extract_constants(lang_obj, root, source_bytes, file_path, language,
                       defs_sorted, module_id, result)

    # --- Phase 3: Supplementary imports ---
    _extract_imports(lang_obj, root, source_bytes, module_id, language, result)

    # --- Phase 4: Supplementary inheritance ---
    _extract_inheritance(
        lang_obj, root, source_bytes, defs_sorted, module_id, language, result,
    )

    # --- Phase 5: Supplementary type declarations (type_alias, enum) ---
    _extract_type_decls(
        lang_obj, root, source_bytes, file_path, language,
        defs_sorted, module_id, result,
    )

    # --- Phase 6: Interface extends (uses "extends" relation for compat) ---
    _extract_interface_extends(
        lang_obj, root, source_bytes, defs_sorted, module_id, language, result,
    )

    return result


# ---------------------------------------------------------------------------
# Supplementary extraction helpers
# ---------------------------------------------------------------------------

_CONSTANT_QUERIES: dict[str, str] = {
    "javascript": """
        (lexical_declaration
          (variable_declarator
            name: (identifier) @name)) @_const
    """,
    "typescript": """
        (lexical_declaration
          (variable_declarator
            name: (identifier) @name)) @_const
    """,
    "python": """
        (module
          (expression_statement
            (assignment
              left: (identifier) @name))) @_const
    """,
}


def _extract_constants(
    lang_obj: Language,
    root: Any,
    source_bytes: bytes,
    file_path: str,
    language: str,
    defs_sorted: list[dict[str, Any]],
    module_id: str,
    result: ExtractionResult,
) -> None:
    """Extract top-level constant/variable definitions not caught by tags.scm."""
    query_str = _CONSTANT_QUERIES.get(language)
    if not query_str:
        return
    query = _make_query(lang_obj, query_str)
    if not query:
        return
    try:
        captures = _run_captures(query, root)
        existing_names = {n.name for n in result.nodes}
        for node in captures.get("name", []):
            name = _node_text(node, source_bytes)
            # Only add UPPER_CASE or _PREFIXED constants not already captured
            if name in existing_names:
                continue
            if not (name.isupper() or name.startswith("_")):
                continue
            node_id = _make_node_id(file_path, name, "variable", start_line=node.start_point[0] + 1)
            const_node = node.parent  # variable_declarator or assignment
            if const_node and const_node.parent:
                const_node = const_node.parent  # lexical_declaration
            start_line = node.start_point[0]
            end_line = const_node.end_point[0] if const_node else start_line
            result.nodes.append(ExtractedNode(
                id=node_id,
                name=name,
                kind="variable",
                file_path=file_path,
                language=language,
                start_line=start_line,
                end_line=end_line,
                # 定数ノードのスニペットを最大文字数で切り詰める
                source_snippet=(
                    _node_text(const_node, source_bytes) if const_node else name
                )[:MAX_SNIPPET_CHARS],
            ))
            parent_id = _find_enclosing(node, defs_sorted, module_id)
            result.edges.append(ExtractedEdge(parent_id, node_id, "defines"))
    except Exception as e:
        logger.debug("Constant query failed for %s: %s", language, e)


def _extract_imports(
    lang_obj: Language,
    root: Any,
    source_bytes: bytes,
    module_id: str,
    language: str,
    result: ExtractionResult,
) -> None:
    """Extract import edges using per-language supplementary queries."""
    query_str = _IMPORT_QUERIES.get(language)
    if not query_str:
        return
    query = _make_query(lang_obj, query_str)
    if not query:
        return
    try:
        captures = _run_captures(query, root)
        for node in captures.get("name", []):
            mod_name = _node_text(node, source_bytes).strip("\"'")
            if mod_name:
                result.edges.append(ExtractedEdge(
                    module_id,
                    f"*::module::{mod_name}",
                    "imports",
                ))
    except Exception as e:
        logger.debug("Import query failed for %s: %s", language, e)


def _extract_inheritance(
    lang_obj: Language,
    root: Any,
    source_bytes: bytes,
    defs_sorted: list[dict[str, Any]],
    module_id: str,
    language: str,
    result: ExtractionResult,
) -> None:
    """Extract inheritance edges using per-language supplementary queries."""
    query_str = _INHERITANCE_QUERIES.get(language)
    if not query_str:
        return
    query = _make_query(lang_obj, query_str)
    if not query:
        return
    try:
        captures = _run_captures(query, root)
        for node in captures.get("name", []):
            base_name = _node_text(node, source_bytes)
            class_id = _find_enclosing(
                node, defs_sorted, module_id, kind_filter="class",
            )
            result.edges.append(ExtractedEdge(
                class_id,
                f"*::class::{base_name}",
                "inherits",
            ))
    except Exception as e:
        logger.debug("Inheritance query failed for %s: %s", language, e)


def _extract_signature(node: Any, source_bytes: bytes) -> str:
    """Extract function/method signature from AST node.

    Looks for a 'parameters' or 'formal_parameters' child node and
    optionally a return type annotation.
    """
    params_text = ""
    return_type = ""
    for child in node.children:
        if child.type in ("parameters", "formal_parameters",
                          "parameter_list", "argument_list"):
            params_text = _node_text(child, source_bytes)
        elif child.type in ("return_type", "type"):
            # Python return type annotation, etc.
            return_type = _node_text(child, source_bytes)
    if params_text:
        if return_type:
            return f"{params_text} -> {return_type}"
        return params_text
    return ""


# Supplementary type declarations (type_alias, enum) not in tags.scm
_TYPE_DECL_QUERIES: dict[str, str] = {
    "typescript": """
        (type_alias_declaration
          name: (type_identifier) @name) @_type_alias
        (enum_declaration
          name: (identifier) @name) @_enum
    """,
    "javascript": """
        (enum_declaration
          name: (identifier) @name) @_enum
    """,
}

_ENUM_MEMBER_QUERIES: dict[str, str] = {
    "typescript": """
        (enum_body
          (enum_assignment
            name: (property_identifier) @name)) @_member
    """,
    "javascript": """
        (enum_body
          (enum_assignment
            name: (property_identifier) @name)) @_member
    """,
}

_INTERFACE_EXTENDS_QUERIES: dict[str, str] = {
    "typescript": """
        (extends_type_clause
          (type_identifier) @name) @_extends
    """,
    "javascript": """
        (extends_type_clause
          (type_identifier) @name) @_extends
    """,
}


def _extract_type_decls(
    lang_obj: Language,
    root: Any,
    source_bytes: bytes,
    file_path: str,
    language: str,
    defs_sorted: list[dict[str, Any]],
    module_id: str,
    result: ExtractionResult,
) -> None:
    """Extract type aliases and enums not captured by tags.scm."""
    query_str = _TYPE_DECL_QUERIES.get(language)
    if not query_str:
        return
    query = _make_query(lang_obj, query_str)
    if not query:
        return
    try:
        matches = _run_matches(query, root)
        existing_names = {n.name for n in result.nodes}
        for _pat_idx, match_dict in matches:
            name_nodes = match_dict.get("name", [])
            if not name_nodes:
                continue
            name = _node_text(name_nodes[0], source_bytes)
            if name in existing_names:
                continue

            # Determine kind from which capture matched
            kind = "type_alias"
            if "_enum" in match_dict:
                kind = "enum"

            decl_node = match_dict.get("_type_alias", match_dict.get("_enum", [None]))[0]
            if decl_node is None:
                continue

            node_id = _make_node_id(file_path, name, kind, start_line=decl_node.start_point[0] + 1)
            result.nodes.append(ExtractedNode(
                id=node_id,
                name=name,
                kind=kind,
                file_path=file_path,
                language=language,
                start_line=decl_node.start_point[0],
                end_line=decl_node.end_point[0],
                # 宣言ノードのスニペットを最大文字数で切り詰める
                source_snippet=_node_text(decl_node, source_bytes)[:MAX_SNIPPET_CHARS],
            ))
            parent_id = _find_enclosing(decl_node, defs_sorted, module_id)
            result.edges.append(ExtractedEdge(parent_id, node_id, "defines"))
            existing_names.add(name)

            # Extract enum members
            if kind == "enum":
                _extract_enum_members(
                    lang_obj, decl_node, source_bytes, file_path,
                    language, node_id, result,
                )
    except Exception as e:
        logger.debug("Type decl query failed for %s: %s", language, e)


def _extract_enum_members(
    lang_obj: Language,
    enum_node: Any,
    source_bytes: bytes,
    file_path: str,
    language: str,
    enum_id: str,
    result: ExtractionResult,
) -> None:
    """Extract enum member definitions as variable nodes under the enum."""
    query_str = _ENUM_MEMBER_QUERIES.get(language)
    if not query_str:
        return
    query = _make_query(lang_obj, query_str)
    if not query:
        return
    try:
        captures = _run_captures(query, enum_node)
        # enum_idからenum名を取得（file:line形式なのでグラフから検索）
        enum_name = ""
        for n in result.nodes:
            if n.id == enum_id:
                enum_name = n.name
                break
        for node in captures.get("name", []):
            member_name = _node_text(node, source_bytes)
            full_name = f"{enum_name}.{member_name}"
            member_id = _make_node_id(
                file_path, full_name, "variable",
                start_line=node.start_point[0] + 1,  # 1-based行番号
            )
            result.nodes.append(ExtractedNode(
                id=member_id,
                name=full_name,
                kind="variable",
                file_path=file_path,
                language=language,
                start_line=node.start_point[0],
            ))
            result.edges.append(ExtractedEdge(enum_id, member_id, "defines"))
    except Exception as e:
        logger.debug("Enum member query failed: %s", e)


def _extract_interface_extends(
    lang_obj: Language,
    root: Any,
    source_bytes: bytes,
    defs_sorted: list[dict[str, Any]],
    module_id: str,
    language: str,
    result: ExtractionResult,
) -> None:
    """Extract interface extends edges (uses 'extends' relation for backward compat).

    Uses AST walking instead of query to avoid cross-parser compatibility issues
    with `extends_type_clause` node types.
    """
    if language not in ("typescript", "javascript"):
        return
    try:
        _walk_extends(root, source_bytes, defs_sorted, module_id, result)
    except Exception as e:
        logger.debug("Interface extends walk failed for %s: %s", language, e)


def _walk_extends(
    node: Any,
    source_bytes: bytes,
    defs_sorted: list[dict[str, Any]],
    module_id: str,
    result: ExtractionResult,
) -> None:
    """Walk AST to find extends_type_clause nodes inside interface declarations."""
    if node.type == "interface_declaration":
        iface_name = ""
        for child in node.children:
            if child.type == "type_identifier" and not iface_name:
                iface_name = _node_text(child, source_bytes)
            elif child.type == "extends_type_clause":
                # Find base type(s)
                for sub in child.children:
                    if sub.type == "type_identifier":
                        base_name = _node_text(sub, source_bytes)
                        # Find matching interface node id
                        iface_id = module_id
                        for d in defs_sorted:
                            if d["kind"] == "interface" and d["name"] == iface_name:
                                iface_id = d["node_id"]
                                break
                        result.edges.append(ExtractedEdge(
                            iface_id,
                            f"*::interface::{base_name}",
                            "extends",
                        ))
    for child in node.children:
        _walk_extends(child, source_bytes, defs_sorted, module_id, result)


def _find_enclosing(
    node: Any,
    defs_sorted: list[dict[str, Any]],
    module_id: str,
    kind_filter: str | None = None,
) -> str:
    """Find the innermost definition that encloses the given node."""
    node_start = node.start_byte
    node_end = node.end_byte
    best = module_id
    for d in defs_sorted:
        if kind_filter and d["kind"] != kind_filter:
            continue
        if d["start_byte"] <= node_start and node_end <= d["end_byte"]:
            best = d["node_id"]
    return best


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def supported_languages() -> list[str]:
    """Return list of languages with tags.scm support available."""
    candidates = [
        "python", "javascript", "typescript", "go", "rust", "java",
        "c", "cpp", "c_sharp", "ruby", "swift", "scala", "lua",
        "php", "elixir", "kotlin", "objc",
    ]
    return [lang for lang in candidates if _get_lang_resources(lang) is not None]
