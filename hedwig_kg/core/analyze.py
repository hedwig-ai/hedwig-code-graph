"""Graph analysis module — structural and semantic analysis.

Identifies god nodes, surprising connections, and computes quality metrics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import networkx as nx

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    god_nodes: list[dict] = field(default_factory=list)
    surprising_connections: list[dict] = field(default_factory=list)
    quality_metrics: dict = field(default_factory=dict)
    hub_nodes: list[dict] = field(default_factory=list)


def analyze(
    G: nx.DiGraph,
    pagerank: dict[str, float] | None = None,
    top_k: int = 10,
) -> AnalysisResult:
    """Run structural analysis on the knowledge graph.

    Args:
        G: The knowledge graph.
        pagerank: Pre-computed PageRank scores.
        top_k: Number of top results per category.

    Returns:
        AnalysisResult with findings.
    """
    result = AnalysisResult()

    if len(G) == 0:
        return result

    # God nodes: high degree + high PageRank
    pr = pagerank or nx.pagerank(G, max_iter=200)
    degree = dict(G.degree())

    scored = []
    for node in G.nodes():
        d = degree.get(node, 0)
        p = pr.get(node, 0)
        scored.append({
            "id": node,
            "label": G.nodes[node].get("label", node),
            "kind": G.nodes[node].get("kind", ""),
            "degree": d,
            "pagerank": round(p, 6),
            "score": d * p,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    result.god_nodes = scored[:top_k]

    # Hub nodes: high betweenness centrality
    try:
        bc = nx.betweenness_centrality(G, k=min(100, len(G)))
        hub_scored = [
            {
                "id": n,
                "label": G.nodes[n].get("label", n),
                "betweenness": round(v, 6),
            }
            for n, v in bc.items()
        ]
        hub_scored.sort(key=lambda x: x["betweenness"], reverse=True)
        result.hub_nodes = hub_scored[:top_k]
    except Exception:
        logger.debug("Betweenness centrality computation failed", exc_info=True)

    # Surprising connections: edges between different communities/file groups
    file_groups: dict[str, set[str]] = {}
    for node in G.nodes():
        fp = G.nodes[node].get("file_path", "")
        if fp not in file_groups:
            file_groups[fp] = set()
        file_groups[fp].add(node)

    for u, v, data in G.edges(data=True):
        u_file = G.nodes[u].get("file_path", "")
        v_file = G.nodes[v].get("file_path", "")
        if u_file and v_file and u_file != v_file:
            conf = data.get("confidence", "EXTRACTED")
            if conf in ("INFERRED", "AMBIGUOUS"):
                result.surprising_connections.append({
                    "source": G.nodes[u].get("label", u),
                    "target": G.nodes[v].get("label", v),
                    "relation": data.get("relation", ""),
                    "confidence": conf,
                    "source_file": u_file,
                    "target_file": v_file,
                })

    result.surprising_connections = result.surprising_connections[:top_k * 2]

    # Quality metrics
    result.quality_metrics = _compute_quality(G)

    return result


def _compute_quality(G: nx.DiGraph) -> dict:
    """Compute graph quality metrics."""
    total_edges = G.number_of_edges()
    if total_edges == 0:
        return {"coverage": 0, "density": 0}

    conf_counts = {"EXTRACTED": 0, "INFERRED": 0, "AMBIGUOUS": 0}
    for _, _, data in G.edges(data=True):
        c = data.get("confidence", "EXTRACTED")
        if c in conf_counts:
            conf_counts[c] += 1

    isolated = len([n for n in G if G.degree(n) == 0])

    return {
        "nodes": G.number_of_nodes(),
        "edges": total_edges,
        "density": round(nx.density(G), 6),
        "isolated_nodes": isolated,
        "extracted_ratio": round(conf_counts["EXTRACTED"] / max(total_edges, 1), 4),
        "inferred_ratio": round(conf_counts["INFERRED"] / max(total_edges, 1), 4),
        "ambiguous_ratio": round(conf_counts["AMBIGUOUS"] / max(total_edges, 1), 4),
        "weakly_connected_components": nx.number_weakly_connected_components(G),
    }
