"""Graph build module — assembles extracted nodes/edges into a NetworkX graph.

Handles node deduplication, edge merging, and cross-file relationship resolution.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath

import networkx as nx

from hedwig_cg.core.extract import ExtractedEdge, ExtractionResult


def build_graph(extractions: list[ExtractionResult]) -> nx.DiGraph:
    """Build a unified directed graph from multiple extraction results.

    Three-phase deduplication:
    1. Intra-file: merge identical nodes within a file
    2. Inter-file: resolve wildcard references (*::name) across files
    3. Semantic: (handled later by embeddings module)

    Args:
        extractions: List of per-file extraction results.

    Returns:
        Unified NetworkX directed graph.
    """
    G = nx.DiGraph()
    name_index: dict[str, list[str]] = defaultdict(list)  # name -> [node_ids]
    wildcard_edges: list[ExtractedEdge] = []

    # Phase 1: Add all nodes
    for ext in extractions:
        for node in ext.nodes:
            if G.has_node(node.id):
                continue
            G.add_node(
                node.id,
                label=node.name,
                kind=node.kind,
                file_path=node.file_path,
                language=node.language,
                start_line=node.start_line,
                end_line=node.end_line,
                docstring=node.docstring,
                signature=node.signature,
                source_snippet=node.source_snippet,
                decorators=node.decorators,
            )
            name_index[node.name].append(node.id)

    # Phase 2: Add edges, collecting wildcards for resolution
    for ext in extractions:
        for edge in ext.edges:
            if edge.target.startswith("*::"):
                wildcard_edges.append(edge)
            elif G.has_node(edge.source) and G.has_node(edge.target):
                G.add_edge(
                    edge.source, edge.target,
                    relation=edge.relation,
                    confidence=edge.confidence,
                )

    # Phase 3: Resolve wildcard references
    for edge in wildcard_edges:
        # Extract target name from wildcard pattern like *::class::ClassName
        parts = edge.target.split("::")
        target_name = parts[-1]

        candidates = name_index.get(target_name, [])
        if len(candidates) == 1:
            confidence = "EXTRACTED"
        elif len(candidates) > 1:
            # Multiple candidates: ambiguous reference — skip entirely.
            # AMBIGUOUS edges connect unrelated nodes sharing a common name
            # (e.g. "logger", "Config"), creating false bridges that inflate
            # community sizes and degrade search quality.
            continue
        else:
            # Create a placeholder external node
            ext_id = f"external::{target_name}"
            if not G.has_node(ext_id):
                G.add_node(ext_id, label=target_name, kind="external", file_path="", language="")
            candidates = [ext_id]
            confidence = "INFERRED"

        for candidate in candidates:
            if G.has_node(edge.source):
                G.add_edge(
                    edge.source, candidate,
                    relation=edge.relation,
                    confidence=confidence,
                )

    # Phase 4: Build directory hierarchy
    _add_directory_nodes(G)

    return G


def _add_directory_nodes(G: nx.DiGraph) -> None:
    """Create directory nodes and connect them to files and parent directories."""
    file_paths: set[str] = set()
    for _, data in G.nodes(data=True):
        fp = data.get("file_path", "")
        if fp and data.get("kind") in ("module", "document"):
            file_paths.add(fp)

    dir_nodes: set[str] = set()

    for fp in file_paths:
        parts = PurePosixPath(fp).parts
        # Create directory nodes for each level (skip the filename)
        for i in range(1, len(parts)):
            dir_path = str(PurePosixPath(*parts[:i]))
            dir_id = f"dir::{dir_path}"

            if dir_id not in dir_nodes:
                dir_nodes.add(dir_id)
                if not G.has_node(dir_id):
                    G.add_node(
                        dir_id,
                        label=parts[i - 1],
                        kind="directory",
                        file_path=dir_path,
                        language="",
                        start_line=0,
                        end_line=0,
                        docstring="",
                        signature="",
                        source_snippet=f"Directory: {dir_path}",
                    )

            # Connect parent → child directory
            if i >= 2:
                parent_path = str(PurePosixPath(*parts[:i - 1]))
                parent_id = f"dir::{parent_path}"
                if G.has_node(parent_id) and not G.has_edge(parent_id, dir_id):
                    G.add_edge(parent_id, dir_id, relation="contains",
                               confidence="EXTRACTED")

        # Connect deepest directory → file (module/document node)
        if len(parts) >= 2:
            parent_dir = str(PurePosixPath(*parts[:-1]))
            parent_id = f"dir::{parent_dir}"
            # Find the module/document node for this file
            for node_id, data in G.nodes(data=True):
                if (data.get("file_path") == fp
                        and data.get("kind") in ("module", "document")
                        and not G.has_edge(parent_id, node_id)):
                    G.add_edge(parent_id, node_id, relation="contains",
                               confidence="EXTRACTED")


# Tier 3: マージ/削除対象ノード種別
MERGE_KINDS = frozenset({
    "constructor", "property", "variable", "decorator", "type_alias",
})


def merge_tier3_nodes(G: nx.DiGraph) -> nx.DiGraph:
    """Tier 3ノードを親ノードにマージし、エッジをリダイレクト。

    - constructor → classにsig/doc統合
    - property → classのメンバーリストに追加
    - variable → moduleのメンバーリストに追加
    - decorator → 親のdecoratorsリストに追加
    - type_alias → moduleのメンバーリストに追加
    - external → 削除（エッジも削除）
    """
    nodes_to_remove: list[str] = []

    for node_id in list(G.nodes()):
        data = G.nodes[node_id]
        kind = data.get("kind", "")

        if kind not in MERGE_KINDS:
            continue

        # 親ノードを探す（incoming "defines" or "contains" エッジ）
        parent_id = None
        for pred in G.predecessors(node_id):
            edge_data = G.edges[pred, node_id]
            if edge_data.get("relation") in ("defines", "contains"):
                parent_id = pred
                break

        if parent_id is None:
            # 親がなければノードだけ削除
            nodes_to_remove.append(node_id)
            continue

        parent_data = G.nodes[parent_id]
        _merge_into_parent(parent_data, data, kind)

        # このノードの他のエッジを親にリダイレクト
        for _, target, edata in list(G.out_edges(node_id, data=True)):
            if target != parent_id and not G.has_edge(parent_id, target):
                G.add_edge(parent_id, target, **edata)
        for source, _, edata in list(G.in_edges(node_id, data=True)):
            if source != parent_id and not G.has_edge(source, parent_id):
                G.add_edge(source, parent_id, **edata)

        nodes_to_remove.append(node_id)

    # externalノードも削除
    for node_id in list(G.nodes()):
        if G.nodes[node_id].get("kind") == "external":
            nodes_to_remove.append(node_id)

    G.remove_nodes_from(nodes_to_remove)
    return G


def _merge_into_parent(parent: dict, child: dict, kind: str) -> None:
    """子ノードの情報を親ノードにマージ。"""
    if kind == "constructor":
        # constructorのsignature/docstringをclassに統合
        if child.get("signature") and not parent.get("signature"):
            parent["signature"] = child["signature"]
        if child.get("docstring"):
            existing = parent.get("docstring", "")
            if existing:
                parent["docstring"] = f"{existing}\n\n{child['docstring']}"
            else:
                parent["docstring"] = child["docstring"]
    elif kind in ("property", "variable", "type_alias"):
        # メンバー名をリストとして追加
        members = parent.get("merged_members", [])
        label = child.get("label", "")
        if label:
            members.append(label)
        parent["merged_members"] = members
    elif kind == "decorator":
        # デコレータを親の属性リストに追加
        decorators = parent.get("decorators", [])
        label = child.get("label", "")
        if label and label not in decorators:
            decorators.append(label)
        parent["decorators"] = decorators


_CONFIDENCE_SCORES: dict[str, float] = {
    "EXTRACTED": 1.0,
    "INFERRED": 0.5,
    "AMBIGUOUS": 0.3,
}


def compute_edge_weights(
    G: nx.DiGraph,
    embeddings: dict[str, list[float]] | None = None,
) -> None:
    """Compute composite edge weights combining multiple signals.

    weight = 0.4 * semantic + 0.3 * confidence + 0.2 * proximity + 0.1 * bidirectional

    Args:
        G: The code graph (modified in-place).
        embeddings: Optional node_id -> embedding vector mapping for semantic similarity.
    """
    import numpy as np

    # Precompute: which edges are bidirectional
    bidir_pairs: set[tuple[str, str]] = set()
    for u, v in G.edges():
        if G.has_edge(v, u):
            bidir_pairs.add((u, v))
            bidir_pairs.add((v, u))

    for u, v, data in G.edges(data=True):
        # 1. Semantic similarity (cosine) — 0.0 if no embeddings
        semantic = 0.0
        if embeddings and u in embeddings and v in embeddings:
            vec_u = np.array(embeddings[u], dtype=np.float32)
            vec_v = np.array(embeddings[v], dtype=np.float32)
            norm_u = np.linalg.norm(vec_u)
            norm_v = np.linalg.norm(vec_v)
            if norm_u > 0 and norm_v > 0:
                semantic = float(np.dot(vec_u, vec_v) / (norm_u * norm_v))
                semantic = max(0.0, semantic)  # clamp negative

        # 2. Confidence score
        confidence = _CONFIDENCE_SCORES.get(data.get("confidence", "EXTRACTED"), 0.5)

        # 3. Proximity score (based on file paths)
        u_path = G.nodes[u].get("file_path", "") if G.has_node(u) else ""
        v_path = G.nodes[v].get("file_path", "") if G.has_node(v) else ""
        if u_path and v_path and u_path == v_path:
            proximity = 1.0
        elif u_path and v_path:
            u_dir = str(PurePosixPath(u_path).parent)
            v_dir = str(PurePosixPath(v_path).parent)
            proximity = 0.7 if u_dir == v_dir else 0.4
        else:
            proximity = 0.4

        # 4. Bidirectional bonus
        bidir = 1.0 if (u, v) in bidir_pairs else 0.0

        # Composite weight
        weight = (0.4 * semantic + 0.3 * confidence + 0.2 * proximity + 0.1 * bidir)
        data["weight"] = round(weight, 4)
        data["semantic_similarity"] = round(semantic, 4)


def compute_pagerank(
    G: nx.DiGraph, personalization: dict[str, float] | None = None,
) -> dict[str, float]:
    """Compute PageRank importance scores for all nodes.

    Args:
        G: The code graph.
        personalization: Optional per-node bias (e.g., recency weighting).

    Returns:
        Dict mapping node_id to importance score.
    """
    if len(G) == 0:
        return {}
    try:
        return nx.pagerank(G, personalization=personalization, max_iter=200)
    except nx.PowerIterationFailedConvergence:
        return {n: 1.0 / len(G) for n in G}


def graph_stats(G: nx.DiGraph) -> dict:
    """Compute basic graph statistics."""
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "density": nx.density(G),
        "components": nx.number_weakly_connected_components(G),
        "isolates": len(list(nx.isolates(G))),
    }
