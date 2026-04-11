"""Hybrid search engine: vector similarity + graph traversal + RRF re-ranking.

Implements the HybridRAG pattern:
1. Vector search → semantic entry points
2. Graph expansion → N-hop neighbors
3. Keyword matching → exact term hits
4. RRF fusion → unified ranking
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import networkx as nx

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from hedwig_kg.storage.store import KnowledgeStore


@dataclass
class SearchResult:
    node_id: str
    label: str
    kind: str
    file_path: str
    score: float
    source: str  # "vector", "graph", "keyword", "fused"
    snippet: str = ""
    neighbors: list[str] = field(default_factory=list)


def reciprocal_rank_fusion(
    *ranked_lists: list[tuple[str, float]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Combine multiple ranked lists using Reciprocal Rank Fusion.

    RRF score = sum(1 / (k + rank_i)) for each list where item appears.

    Args:
        ranked_lists: Each list is [(item_id, score), ...] sorted by score desc.
        k: RRF constant (default 60, as in the original paper).

    Returns:
        Fused ranking as [(item_id, rrf_score), ...].
    """
    scores: dict[str, float] = {}
    for rlist in ranked_lists:
        for rank, (item_id, _) in enumerate(rlist):
            scores[item_id] = scores.get(item_id, 0) + 1.0 / (k + rank + 1)

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return fused


def hybrid_search(
    query: str,
    store: "KnowledgeStore",
    G: nx.DiGraph,
    top_k: int = 10,
    graph_hops: int = 2,
    vector_candidates: int = 20,
) -> list[SearchResult]:
    """Execute hybrid search combining vector, graph, and keyword signals.

    Args:
        query: Natural language query.
        store: KnowledgeStore with embeddings loaded.
        G: The knowledge graph.
        top_k: Number of final results.
        graph_hops: How many hops to expand from vector hits.
        vector_candidates: Number of initial vector candidates.

    Returns:
        Ranked list of SearchResult.
    """
    from hedwig_kg.query.embeddings import embed_query_dual

    # Stage 1: Dual vector search (code + text models)
    query_vecs = embed_query_dual(query)
    code_vector_hits = store.vector_search(
        query_vecs["code"], top_k=vector_candidates, model_type="code",
    )
    text_vector_hits = store.vector_search(
        query_vecs["text"], top_k=vector_candidates, model_type="text",
    )
    # Combined for graph expansion
    vector_hits = sorted(
        code_vector_hits + text_vector_hits, key=lambda x: x[1], reverse=True,
    )[:vector_candidates]

    # Stage 2: Graph expansion from vector hits
    graph_hits: list[tuple[str, float]] = []
    expanded_nodes: set[str] = set()
    for node_id, vscore in vector_hits[:5]:  # Expand top 5
        if not G.has_node(node_id):
            continue
        try:
            ego = nx.ego_graph(G.to_undirected(), node_id, radius=graph_hops)
            for neighbor in ego.nodes():
                if neighbor not in expanded_nodes:
                    expanded_nodes.add(neighbor)
                    # Score decays with distance
                    try:
                        dist = nx.shortest_path_length(G.to_undirected(), node_id, neighbor)
                    except nx.NetworkXNoPath:
                        dist = graph_hops
                    gscore = vscore * (1.0 / (1 + dist))
                    graph_hits.append((neighbor, gscore))
        except Exception:
            logger.debug("Graph expansion failed for %s", node_id, exc_info=True)
            continue

    graph_hits.sort(key=lambda x: x[1], reverse=True)
    graph_hits = graph_hits[:vector_candidates]

    # Stage 3: Keyword search
    terms = [t.lower() for t in query.split() if len(t) > 2]
    keyword_results = store.keyword_search(terms, top_k=vector_candidates)
    keyword_hits = [(r["id"], r["score"]) for r in keyword_results]

    # Stage 4: Community search — boost nodes in matching communities
    community_hits: list[tuple[str, float]] = []
    try:
        comm_results = store.community_search(terms, top_k=3)
        for comm in comm_results:
            cscore = comm["score"] / max(len(terms), 1)
            for node_id in comm["node_ids"][:10]:
                community_hits.append((node_id, cscore))
    except Exception:
        logger.debug("Community search failed", exc_info=True)

    # Stage 5: RRF fusion (5 signals: code_vector + text_vector + graph + keyword + community)
    fused = reciprocal_rank_fusion(
        code_vector_hits, text_vector_hits, graph_hits, keyword_hits, community_hits,
    )

    # Build final results
    results = []
    for node_id, rrf_score in fused[:top_k]:
        data = G.nodes.get(node_id, {})
        if not data:
            continue

        # Get immediate neighbors for context
        neighbors = []
        if G.has_node(node_id):
            for n in list(G.successors(node_id))[:3] + list(G.predecessors(node_id))[:3]:
                neighbors.append(G.nodes[n].get("label", n))

        results.append(SearchResult(
            node_id=node_id,
            label=data.get("label", node_id),
            kind=data.get("kind", ""),
            file_path=data.get("file_path", ""),
            score=rrf_score,
            source="fused",
            snippet=data.get("source_snippet", "")[:200],
            neighbors=neighbors,
        ))

    return results
