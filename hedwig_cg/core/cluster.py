"""Hierarchical community detection using Leiden algorithm.

Implements multi-resolution clustering to build a community hierarchy tree,
producing coarse-to-fine community layers for richer structural analysis.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import networkx as nx

logger = logging.getLogger(__name__)


@dataclass
class Community:
    id: int
    level: int  # 0=coarsest, higher=finer
    resolution: float
    node_ids: list[str] = field(default_factory=list)
    summary: str = ""
    parent_id: int | None = None
    children_ids: list[int] = field(default_factory=list)


@dataclass
class ClusterResult:
    communities: dict[int, Community] = field(default_factory=dict)
    # node -> [community_ids at each level]
    node_to_community: dict[str, list[int]] = field(default_factory=dict)
    hierarchy_levels: int = 0


def _detect_hub_nodes(
    G: nx.DiGraph,
    percentile: float = 97,
    min_threshold: int = 10,
) -> set[str]:
    """Detect hub nodes with abnormally high in-degree.

    Hub nodes (builtins like len/max, minified JS vars, common utilities)
    act as false bridges in community detection, merging unrelated clusters.

    Uses adaptive thresholding: P97 of in-degree distribution with a
    minimum floor of 10 to avoid over-filtering in small graphs.

    Args:
        G: The code graph.
        percentile: Percentile for outlier detection (default 97).
        min_threshold: Minimum in-degree to consider as hub.

    Returns:
        Set of node IDs to exclude from clustering.
    """
    import numpy as np

    if len(G) == 0:
        return set()

    in_degrees = [G.in_degree(n) for n in G.nodes()]
    threshold = max(np.percentile(in_degrees, percentile), min_threshold)

    return {
        n for n in G.nodes()
        if G.in_degree(n) > threshold
    }


def hierarchical_cluster(
    G: nx.DiGraph,
    resolutions: list[float] | None = None,
    min_community_size: int = 2,
) -> ClusterResult:
    """Run multi-resolution Leiden clustering to build a hierarchy.

    Args:
        G: The code graph.
        resolutions: List of resolution parameters (low=coarse, high=fine).
        min_community_size: Minimum nodes per community.

    Returns:
        ClusterResult with hierarchical community structure.
    """
    if resolutions is None:
        resolutions = [0.25, 0.5, 1.0, 2.0]

    if len(G) < min_community_size:
        return ClusterResult()

    result = ClusterResult(hierarchy_levels=len(resolutions))
    community_counter = 0

    # Filter hub nodes before clustering — nodes with abnormally high
    # in-degree (builtins like len/max, minified JS vars) act as false
    # bridges that merge unrelated communities into giant superclusters.
    hub_nodes = _detect_hub_nodes(G)
    if hub_nodes:
        logger.info(
            "Excluding %d hub nodes from clustering (in-degree outliers)",
            len(hub_nodes),
        )
    G_filtered = G.copy()
    G_filtered.remove_nodes_from(hub_nodes)

    # Convert to undirected for community detection
    G_undirected = G_filtered.to_undirected()

    try:
        import igraph as ig
        import leidenalg

        # Convert NetworkX to igraph
        node_list = list(G_undirected.nodes())
        node_index = {n: i for i, n in enumerate(node_list)}
        edges = [
            (node_index[u], node_index[v])
            for u, v in G_undirected.edges()
            if u in node_index and v in node_index
        ]
        ig_graph = ig.Graph(n=len(node_list), edges=edges, directed=False)

        prev_level_map: dict[str, int] = {}

        for level_idx, res in enumerate(resolutions):
            partition = leidenalg.find_partition(
                ig_graph,
                leidenalg.RBConfigurationVertexPartition,
                resolution_parameter=res,
            )

            level_communities: dict[int, list[str]] = {}
            for node_idx, comm_idx in enumerate(partition.membership):
                node_id = node_list[node_idx]
                if comm_idx not in level_communities:
                    level_communities[comm_idx] = []
                level_communities[comm_idx].append(node_id)

            for local_id, members in level_communities.items():
                if len(members) < min_community_size:
                    continue

                comm = Community(
                    id=community_counter,
                    level=level_idx,
                    resolution=res,
                    node_ids=members,
                )

                # Link to parent community from coarser level
                if prev_level_map:
                    parent_candidates: dict[int, int] = {}
                    for node_id in members:
                        if node_id in prev_level_map:
                            pid = prev_level_map[node_id]
                            parent_candidates[pid] = parent_candidates.get(pid, 0) + 1
                    if parent_candidates:
                        comm.parent_id = max(parent_candidates, key=parent_candidates.get)
                        result.communities[comm.parent_id].children_ids.append(community_counter)

                result.communities[community_counter] = comm

                for node_id in members:
                    if node_id not in result.node_to_community:
                        result.node_to_community[node_id] = []
                    result.node_to_community[node_id].append(community_counter)

                community_counter += 1

            # Update level map for next iteration
            prev_level_map = {}
            for comm_id, comm in result.communities.items():
                if comm.level == level_idx:
                    for node_id in comm.node_ids:
                        prev_level_map[node_id] = comm_id

    except ImportError:
        # Fallback: use NetworkX's built-in community detection
        try:
            from networkx.algorithms.community import louvain_communities

            communities = louvain_communities(G_undirected, resolution=1.0)
            for members_set in communities:
                members = list(members_set)
                if len(members) < min_community_size:
                    continue
                comm = Community(
                    id=community_counter,
                    level=0,
                    resolution=1.0,
                    node_ids=members,
                )
                result.communities[community_counter] = comm
                for node_id in members:
                    result.node_to_community[node_id] = [community_counter]
                community_counter += 1
            result.hierarchy_levels = 1
        except Exception:
            logger.debug("Louvain fallback failed", exc_info=True)

    return result


def get_community_nodes(G: nx.DiGraph, community: Community) -> nx.DiGraph:
    """Extract subgraph for a specific community."""
    return G.subgraph(community.node_ids).copy()


def community_label(G: nx.DiGraph, community: Community, max_labels: int = 5) -> str:
    """Generate a descriptive label for a community based on its top nodes."""
    subgraph = G.subgraph(community.node_ids)
    # Sort by degree centrality
    centrality = nx.degree_centrality(subgraph)
    top_nodes = sorted(centrality, key=centrality.get, reverse=True)[:max_labels]
    labels = [G.nodes[n].get("label", n) for n in top_nodes]
    return ", ".join(labels)


def summarize_communities(
    G: nx.DiGraph,
    cluster_result: ClusterResult,
    max_keywords: int = 10,
) -> ClusterResult:
    """Generate text summaries for each community for search indexing.

    Builds a keyword-rich summary from node labels, kinds, docstrings,
    and file paths. This enables community-level search without an LLM.

    Args:
        G: The code graph.
        cluster_result: Clustering output to enrich.
        max_keywords: Max keywords to extract per community.

    Returns:
        The same ClusterResult with summaries populated.
    """
    for comm_id, comm in cluster_result.communities.items():
        if comm.summary:
            continue

        subgraph = G.subgraph(comm.node_ids)
        centrality = nx.degree_centrality(subgraph)
        top_nodes = sorted(centrality, key=centrality.get, reverse=True)

        # Collect signals
        labels = []
        kinds: dict[str, int] = {}
        files: set[str] = set()
        docstrings: list[str] = []

        for node_id in top_nodes[:20]:
            data = G.nodes.get(node_id, {})
            label = data.get("label", "")
            if label:
                labels.append(label)
            kind = data.get("kind", "")
            if kind:
                kinds[kind] = kinds.get(kind, 0) + 1
            fp = data.get("file_path", "")
            if fp:
                from pathlib import Path
                files.add(Path(fp).name)
            doc = data.get("docstring", "")
            if doc:
                docstrings.append(doc[:100])

        # Build summary
        top_labels = labels[:max_keywords]
        kind_desc = ", ".join(
            f"{count} {kind}{'s' if count > 1 else ''}"
            for kind, count in sorted(kinds.items(), key=lambda x: -x[1])[:5]
        )
        file_list = ", ".join(sorted(files)[:5])

        parts = []
        if kind_desc:
            parts.append(f"Contains {kind_desc}.")
        if top_labels:
            parts.append(f"Key elements: {', '.join(top_labels)}.")
        if file_list:
            parts.append(f"Files: {file_list}.")
        if docstrings:
            parts.append(f"Context: {' | '.join(docstrings[:3])}")

        comm.summary = " ".join(parts)

        # Also generate a label if empty
        if not comm.summary:
            comm.summary = community_label(G, comm)

    return cluster_result
