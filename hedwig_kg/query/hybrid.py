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
    start_line: int = 0
    end_line: int = 0
    signature: str = ""
    docstring: str = ""
    neighbors: list[str] = field(default_factory=list)
    signal_contributions: dict[str, float] = field(default_factory=dict)
    """Per-signal RRF contribution breakdown (e.g. {"code_vector": 0.018, "keyword": 0.012})."""


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


SIGNAL_NAMES = ["code_vector", "text_vector", "graph", "keyword", "community"]


def reciprocal_rank_fusion(
    *ranked_lists: list[tuple[str, float]],
    k: int = 60,
    weights: list[float] | None = None,
    signal_names: list[str] | None = None,
) -> tuple[list[tuple[str, float]], dict[str, dict[str, float]]]:
    """Combine multiple ranked lists using Weighted Reciprocal Rank Fusion.

    RRF score = sum(w_i / (k + rank_i)) for each list where item appears.

    Args:
        ranked_lists: Each list is [(item_id, score), ...] sorted by score desc.
        k: RRF constant (default 60, as in the original paper).
        weights: Per-signal weights. If None, all signals weighted equally (1.0).
        signal_names: Names for each signal (for breakdown tracking).

    Returns:
        Tuple of (fused ranking, per-item signal breakdowns).
    """
    if weights is None:
        weights = [1.0] * len(ranked_lists)
    if signal_names is None:
        signal_names = SIGNAL_NAMES[:len(ranked_lists)]

    scores: dict[str, float] = {}
    breakdowns: dict[str, dict[str, float]] = {}
    for w, rlist, sname in zip(weights, ranked_lists, signal_names):
        for rank, (item_id, _) in enumerate(rlist):
            contribution = w / (k + rank + 1)
            scores[item_id] = scores.get(item_id, 0) + contribution
            if item_id not in breakdowns:
                breakdowns[item_id] = {}
            breakdowns[item_id][sname] = breakdowns[item_id].get(sname, 0) + contribution

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return fused, breakdowns


# Default signal weights: [code_vector, text_vector, graph, keyword, community]
# Tuned via empirical testing on code search queries:
# - Vector signals (1.0): primary semantic matching
# - Graph (0.8): structural context from call/inheritance edges
# - Keyword (1.5): boosted for precise term matching — ensures code entities
#   with exact name matches rank above loosely-similar document nodes
# - Community (0.7): thematic grouping boost
DEFAULT_WEIGHTS = [1.0, 1.0, 0.8, 1.5, 0.7]


# --- Relation-type weights for graph expansion ---
# Edges representing direct code relationships (calls, inherits) are more
# semantically valuable for expansion than structural containment edges.
RELATION_WEIGHTS: dict[str, float] = {
    "calls": 1.0,
    "inherits": 1.0,
    "extends": 1.0,
    "imports": 0.7,
    "references": 0.6,
    "defines": 0.5,
    "contains": 0.5,
}
_DEFAULT_RELATION_WEIGHT = 0.5


def _weighted_expand(
    G: nx.DiGraph,
    seed: str,
    seed_score: float,
    max_hops: int,
    seen: set[str],
    out: list[tuple[str, float]],
) -> None:
    """BFS expansion that weights edges by relation type and stored weight.

    Instead of treating all edges uniformly, this multiplies the propagated
    score by ``edge_weight * relation_weight`` so that high-confidence,
    semantically similar, structurally important edges propagate more score
    to their neighbors.
    """
    # BFS frontier: list of (node_id, accumulated_score, hops_remaining)
    frontier: list[tuple[str, float, int]] = [(seed, seed_score, max_hops)]

    while frontier:
        node_id, score, hops = frontier.pop(0)
        if node_id in seen:
            continue
        seen.add(node_id)
        out.append((node_id, score))

        if hops <= 0:
            continue

        # Expand both successors and predecessors (treat as undirected)
        neighbors: list[tuple[str, dict]] = []
        for _, nbr, data in G.out_edges(node_id, data=True):
            neighbors.append((nbr, data))
        for nbr, _, data in G.in_edges(node_id, data=True):
            neighbors.append((nbr, data))

        for nbr, edata in neighbors:
            if nbr in seen:
                continue
            # Edge weight from compute_edge_weights (semantic+confidence+proximity)
            edge_w = edata.get("weight", 0.5)
            # Relation-type boost
            rel = edata.get("relation", "")
            rel_w = RELATION_WEIGHTS.get(rel, _DEFAULT_RELATION_WEIGHT)
            # Propagated score decays by edge quality
            nbr_score = score * edge_w * rel_w
            frontier.append((nbr, nbr_score, hops - 1))


def extract_search_terms(query: str) -> list[str]:
    """Extract meaningful search terms by filtering stopwords and short tokens."""
    return [
        t.lower() for t in query.split()
        if len(t) > 2 and t.lower() not in STOPWORDS
    ]


def _query_relevant_snippet(source: str, terms: list[str], max_len: int = 200) -> str:
    """Extract the most query-relevant portion of source code as snippet.

    Instead of blindly truncating from the start, finds the region with the
    highest density of query terms and centers the snippet around it.
    Falls back to the first ``max_len`` chars if no terms match.
    """
    if not source or not terms:
        return source[:max_len] if source else ""

    src_lower = source.lower()
    # Find all term positions
    positions: list[int] = []
    for term in terms:
        idx = 0
        while True:
            idx = src_lower.find(term, idx)
            if idx == -1:
                break
            positions.append(idx)
            idx += len(term)

    if not positions:
        return source[:max_len]

    # Pick the densest region: center on the median position
    positions.sort()
    median_pos = positions[len(positions) // 2]
    start = max(0, median_pos - max_len // 3)
    end = start + max_len

    snippet = source[start:end]
    # Clean up: don't start mid-word
    if start > 0:
        space_idx = snippet.find(" ")
        if 0 < space_idx < 20:
            snippet = "..." + snippet[space_idx + 1:]
    if end < len(source):
        space_idx = snippet.rfind(" ")
        if space_idx > max_len - 20:
            snippet = snippet[:space_idx] + "..."

    return snippet


def hybrid_search(
    query: str,
    store: "KnowledgeStore",
    G: nx.DiGraph,
    top_k: int = 10,
    graph_hops: int = 2,
    vector_candidates: int = 40,
    weights: list[float] | None = None,
    use_cache: bool = True,
    fast: bool = False,
    text_model: str | None = None,
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
        fast: If True, use only the text model (skips code model loading).
            Reduces cold-start latency from ~2.8s to ~0.2s.
        text_model: Override text model name (e.g. multilingual-e5-small).
            Read from DB metadata at search time.

    Returns:
        Ranked list of SearchResult.
    """
    # Check cache first
    if use_cache:
        key = _cache_key(query, top_k, graph_hops)
        if key in _search_cache:
            _search_cache.move_to_end(key)
            return _search_cache[key]

    signal_weights = weights or DEFAULT_WEIGHTS

    # Stage 1: Vector search
    if fast:
        # Fast mode: text model only (cold start ~0.2s vs ~2.8s)
        from hedwig_kg.query.embeddings import TEXT_MODEL, embed_query
        effective_text = text_model or TEXT_MODEL
        query_vec = embed_query(query, effective_text)
        text_vector_hits = store.vector_search(
            query_vec, top_k=vector_candidates, model_type="text",
        )
        code_vector_hits = store.vector_search(
            query_vec, top_k=vector_candidates, model_type="code",
        )
    else:
        # Full dual-model search
        from hedwig_kg.query.embeddings import embed_query_dual
        query_vecs = embed_query_dual(query, text_model=text_model)
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

    # Stage 2: Weight-aware graph expansion from vector hits
    # Traverses edges using computed weights (semantic + confidence + proximity)
    # so high-quality edges (CALLS, INHERITS with high similarity) are preferred
    # over low-quality edges (AMBIGUOUS imports to external nodes).
    graph_hits: list[tuple[str, float]] = []
    expanded_nodes: set[str] = set()
    for node_id, vscore in vector_hits[:8]:  # Expand top 8 seeds
        if not G.has_node(node_id):
            continue
        try:
            _weighted_expand(
                G, node_id, vscore, graph_hops,
                expanded_nodes, graph_hits,
            )
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
    fused, breakdowns = reciprocal_rank_fusion(
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
            start_line=data.get("start_line", 0),
            end_line=data.get("end_line", 0),
            signature=data.get("signature", ""),
            docstring=data.get("docstring", ""),
            neighbors=neighbors,
            signal_contributions=breakdowns.get(node_id, {}),
        ))

    # Store in cache
    if use_cache:
        key = _cache_key(query, top_k, graph_hops)
        _search_cache[key] = results
        if len(_search_cache) > _CACHE_MAX_SIZE:
            _search_cache.popitem(last=False)

    return results


def expanded_search(
    query: str,
    store: "KnowledgeStore",
    G: nx.DiGraph,
    top_k: int = 10,
    graph_hops: int = 2,
    vector_candidates: int = 40,
    weights: list[float] | None = None,
    fast: bool = False,
    text_model: str | None = None,
) -> list[SearchResult]:
    """Two-stage query expansion: search, collect neighbor terms, re-search.

    Stage 1: Run standard hybrid_search.
    Stage 2: Extract service/module names from neighbors of top results,
             append them to the query, and re-search for broader recall.

    This helps discover cross-service relationships that share no keywords
    (e.g. "payment" query finding "payperview" via neighbor expansion).
    """
    # Stage 1: Initial search
    first_results = hybrid_search(
        query, store, G,
        top_k=top_k,
        graph_hops=graph_hops,
        vector_candidates=vector_candidates,
        weights=weights,
        use_cache=False,
        fast=fast,
        text_model=text_model,
    )

    if not first_results:
        return first_results

    # Collect neighbor labels from top results for query expansion
    neighbor_terms: set[str] = set()
    existing_labels = {r.label.lower() for r in first_results}
    for result in first_results[:5]:
        for nbr_label in result.neighbors:
            # Only add terms that aren't already in results
            label_lower = nbr_label.lower().replace(".", "_")
            if label_lower not in existing_labels and len(label_lower) > 2:
                neighbor_terms.add(nbr_label)

    if not neighbor_terms:
        return first_results

    # Stage 2: Re-search with expanded query
    expansion = " ".join(list(neighbor_terms)[:8])  # Limit expansion size
    expanded_query = f"{query} {expansion}"
    logger.debug("Query expansion: '%s' -> '%s'", query, expanded_query)

    second_results = hybrid_search(
        expanded_query, store, G,
        top_k=top_k,
        graph_hops=graph_hops,
        vector_candidates=vector_candidates,
        weights=weights,
        use_cache=False,
        fast=fast,
        text_model=text_model,
    )

    # Merge: keep first results' order, append new discoveries from second pass
    seen_ids = {r.node_id for r in first_results}
    merged = list(first_results)
    for r in second_results:
        if r.node_id not in seen_ids and len(merged) < top_k:
            merged.append(r)
            seen_ids.add(r.node_id)

    return merged[:top_k]
