"""Hybrid search engine: vector similarity + graph traversal + RRF re-ranking.

Implements the HybridRAG pattern:
1. Code vector search → semantic entry points (code model)
2. Text vector search → semantic entry points (text model)
3. Graph expansion → N-hop neighbors
4. Keyword matching → exact term hits (with stopword filtering)
5. Community matching → community-level boosting
6. Weighted RRF fusion → unified ranking with per-signal weights
"""

from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import networkx as nx

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from hedwig_kg.storage.store import KnowledgeStore


# --- Stopwords for keyword search filtering ---
# Common English stopwords that add noise to FTS5 keyword search.
STOPWORDS: frozenset[str] = frozenset({
    "the", "is", "at", "which", "on", "a", "an", "and", "or", "but",
    "in", "with", "to", "for", "of", "not", "no", "can", "had", "has",
    "have", "was", "were", "been", "being", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "must", "need",
    "this", "that", "these", "those", "it", "its", "from", "by", "as",
    "are", "be", "if", "so", "than", "too", "very", "just", "about",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "then", "once",
    "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such",
    "only", "own", "same", "also", "what", "who", "whom",
})


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


# --- LRU search cache ---
_search_cache: OrderedDict[str, list[SearchResult]] = OrderedDict()
_CACHE_MAX_SIZE = 128


def _cache_key(query: str, top_k: int, graph_hops: int) -> str:
    """Generate a deterministic cache key for a search query."""
    raw = f"{query}|{top_k}|{graph_hops}"
    return hashlib.md5(raw.encode()).hexdigest()


def clear_search_cache() -> None:
    """Clear the search result cache (call after graph rebuild)."""
    _search_cache.clear()


def reciprocal_rank_fusion(
    *ranked_lists: list[tuple[str, float]],
    k: int = 60,
    weights: list[float] | None = None,
) -> list[tuple[str, float]]:
    """Combine multiple ranked lists using Weighted Reciprocal Rank Fusion.

    RRF score = sum(w_i / (k + rank_i)) for each list where item appears.

    Args:
        ranked_lists: Each list is [(item_id, score), ...] sorted by score desc.
        k: RRF constant (default 60, as in the original paper).
        weights: Per-signal weights. If None, all signals weighted equally (1.0).

    Returns:
        Fused ranking as [(item_id, rrf_score), ...].
    """
    if weights is None:
        weights = [1.0] * len(ranked_lists)

    scores: dict[str, float] = {}
    for w, rlist in zip(weights, ranked_lists):
        for rank, (item_id, _) in enumerate(rlist):
            scores[item_id] = scores.get(item_id, 0) + w / (k + rank + 1)

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return fused


# Default signal weights: [code_vector, text_vector, graph, keyword, community]
# Code/text vectors are primary signals; graph adds structural context;
# keyword provides exact-match precision; community gives thematic boost.
DEFAULT_WEIGHTS = [1.2, 1.2, 0.8, 1.0, 0.6]


def extract_search_terms(query: str) -> list[str]:
    """Extract meaningful search terms by filtering stopwords and short tokens."""
    return [
        t.lower() for t in query.split()
        if len(t) > 2 and t.lower() not in STOPWORDS
    ]


def hybrid_search(
    query: str,
    store: "KnowledgeStore",
    G: nx.DiGraph,
    top_k: int = 10,
    graph_hops: int = 2,
    vector_candidates: int = 20,
    weights: list[float] | None = None,
    use_cache: bool = True,
) -> list[SearchResult]:
    """Execute hybrid search combining vector, graph, and keyword signals.

    Args:
        query: Natural language query.
        store: KnowledgeStore with embeddings loaded.
        G: The knowledge graph.
        top_k: Number of final results.
        graph_hops: How many hops to expand from vector hits.
        vector_candidates: Number of initial vector candidates.
        weights: Per-signal weights [code_vec, text_vec, graph, keyword, community].
            Defaults to DEFAULT_WEIGHTS.
        use_cache: Whether to use LRU search result caching.

    Returns:
        Ranked list of SearchResult.
    """
    # Check cache first
    if use_cache:
        key = _cache_key(query, top_k, graph_hops)
        if key in _search_cache:
            _search_cache.move_to_end(key)
            return _search_cache[key]

    from hedwig_kg.query.embeddings import embed_query_dual

    signal_weights = weights or DEFAULT_WEIGHTS

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
    # Convert to undirected once (avoids O(N) copy per iteration)
    G_undirected = G.to_undirected(as_view=True)
    graph_hits: list[tuple[str, float]] = []
    expanded_nodes: set[str] = set()
    for node_id, vscore in vector_hits[:5]:  # Expand top 5
        if not G.has_node(node_id):
            continue
        try:
            ego = nx.ego_graph(G_undirected, node_id, radius=graph_hops)
            for neighbor in ego.nodes():
                if neighbor not in expanded_nodes:
                    expanded_nodes.add(neighbor)
                    # Score decays with distance via BFS depth
                    try:
                        dist = nx.shortest_path_length(G_undirected, node_id, neighbor)
                    except nx.NetworkXNoPath:
                        dist = graph_hops
                    gscore = vscore * (1.0 / (1 + dist))
                    graph_hits.append((neighbor, gscore))
        except Exception:
            logger.debug("Graph expansion failed for %s", node_id, exc_info=True)
            continue

    graph_hits.sort(key=lambda x: x[1], reverse=True)
    graph_hits = graph_hits[:vector_candidates]

    # Stage 3: Keyword search (with stopword filtering)
    terms = extract_search_terms(query)
    keyword_results = store.keyword_search(terms, top_k=vector_candidates) if terms else []
    keyword_hits = [(r["id"], r["score"]) for r in keyword_results]

    # Stage 4: Community search — boost nodes in matching communities
    community_hits: list[tuple[str, float]] = []
    if terms:
        try:
            comm_results = store.community_search(terms, top_k=3)
            for comm in comm_results:
                cscore = comm["score"] / max(len(terms), 1)
                for node_id in comm["node_ids"][:10]:
                    community_hits.append((node_id, cscore))
        except Exception:
            logger.debug("Community search failed", exc_info=True)

    # Stage 5: Weighted RRF fusion (5 signals with configurable weights)
    fused = reciprocal_rank_fusion(
        code_vector_hits, text_vector_hits, graph_hits, keyword_hits, community_hits,
        weights=signal_weights,
    )

    # Build final results (skip external/directory nodes without source context)
    results = []
    seen = 0
    for node_id, rrf_score in fused:
        if seen >= top_k:
            break
        data = G.nodes.get(node_id, {})
        if not data:
            continue
        # External nodes (stdlib/library refs) lack file paths and source —
        # they add noise to results. Skip them in the final ranking.
        kind = data.get("kind", "")
        if kind in ("external", "directory"):
            continue
        seen += 1

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

    # Store in cache
    if use_cache:
        key = _cache_key(query, top_k, graph_hops)
        _search_cache[key] = results
        if len(_search_cache) > _CACHE_MAX_SIZE:
            _search_cache.popitem(last=False)

    return results
