"""Graph build module — assembles extracted nodes/edges into a NetworkX graph.

Handles node deduplication, edge merging, and cross-file relationship resolution.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath

import networkx as nx

from hedwig_kg.core.extract import ExtractedEdge, ExtractionResult


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
            confidence = "AMBIGUOUS"
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


def compute_pagerank(
    G: nx.DiGraph, personalization: dict[str, float] | None = None,
) -> dict[str, float]:
    """Compute PageRank importance scores for all nodes.

    Args:
        G: The knowledge graph.
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
