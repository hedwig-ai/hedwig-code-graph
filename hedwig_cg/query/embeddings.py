"""Embedding generation for code graph nodes.

Dual-model architecture:
- Code nodes (function, class, method, module) → BAAI/bge-small-en-v1.5
- Text nodes (heading, section, docstring, etc.) → intfloat/multilingual-e5-small

Both models output 384-dim vectors, enabling a single FAISS index.
Memory-bounded: yields batches to avoid loading all vectors into RAM at once.
"""

from __future__ import annotations

import gc
import logging
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import networkx as nx

logger = logging.getLogger(__name__)

# --- Model configuration ---

CODE_MODEL = "BAAI/bge-small-en-v1.5"
TEXT_MODEL = "intfloat/multilingual-e5-small"

# Legacy alias for backward compatibility
MULTILINGUAL_TEXT_MODEL = TEXT_MODEL

# Models that require instruction prefixes (E5 family)
_PREFIX_MODELS: dict[str, dict[str, str]] = {
    "intfloat/multilingual-e5-small": {"query": "query: ", "passage": "passage: "},
    "intfloat/multilingual-e5-base": {"query": "query: ", "passage": "passage: "},
    "intfloat/multilingual-e5-large": {"query": "query: ", "passage": "passage: "},
}

# Node kinds routed to the code model
CODE_KINDS = frozenset({
    "function", "class", "method", "module", "variable",
    "interface", "enum", "struct", "trait", "import",
    "constructor", "property", "decorator", "type_alias",
})

# Node kinds excluded from embedding (these are references to external
# libraries/symbols that lack source code, docstrings, and file paths,
# polluting the vector search space with low-information vectors).
SKIP_KINDS = frozenset({"external", "directory"})

# Memory budget: 4 GB max for entire pipeline
_MEMORY_LIMIT_BYTES = 4 * 1024 * 1024 * 1024

# Model cache directory: ~/.hedwig-cg/models/
_MODEL_CACHE_DIR = Path.home() / ".hedwig-cg" / "models"

# Lazy-loaded model cache (keyed by model name)
_models: dict[str, object] = {}


def _get_model(model_name: str):
    """Lazy-load sentence-transformers model, caching to ~/.hedwig-cg/models/."""
    if model_name not in _models:
        from sentence_transformers import SentenceTransformer

        cache_dir = _MODEL_CACHE_DIR
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Check if model is already in our local cache
        safe_name = model_name.replace("/", "--")
        local_path = cache_dir / safe_name
        is_cached = local_path.exists() and any(local_path.iterdir())

        if is_cached:
            logger.debug("Loading cached model '%s' from %s", model_name, local_path)
            _models[model_name] = SentenceTransformer(str(local_path))
        else:
            logger.info("Downloading embedding model '%s' (first time only)...", model_name)
            try:
                from rich.console import Console
                Console(stderr=True).print(
                    f"[yellow]⬇ Downloading embedding model '{model_name}' "
                    f"(first time only, saved to ~/.hedwig-cg/models/)...[/yellow]"
                )
            except ImportError:
                pass

            model = SentenceTransformer(model_name)
            # Save to local cache for future use
            model.save(str(local_path))
            logger.info("Model saved to %s", local_path)
            _models[model_name] = model

    return _models[model_name]


def _get_process_rss() -> int:
    """Return current process RSS in bytes (0 if unavailable)."""
    try:
        import platform
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if platform.system() == "Darwin":
            return rss  # already bytes on macOS
        return rss * 1024  # KB to bytes on Linux
    except Exception:
        return 0


# --- Cross-Encoder Reranker ---

RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_reranker = None


def _get_reranker():
    """Lazy-load Cross-Encoder reranker model."""
    global _reranker  # noqa: PLW0603
    if _reranker is None:
        from sentence_transformers import CrossEncoder

        safe_name = RERANKER_MODEL.replace("/", "--")
        local_path = _MODEL_CACHE_DIR / safe_name
        if local_path.exists() and any(local_path.iterdir()):
            _reranker = CrossEncoder(str(local_path))
        else:
            _MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _reranker = CrossEncoder(RERANKER_MODEL)
            _reranker.save(str(local_path))
    return _reranker


def rerank(
    query: str, candidates: list[tuple[str, str]], top_k: int = 10,
) -> list[tuple[int, float]]:
    """Rerank (query, passage) pairs using a Cross-Encoder.

    Args:
        query: The search query.
        candidates: List of (node_id, passage_text) tuples.
        top_k: Number of results to return.

    Returns:
        List of (original_index, reranker_score) sorted by score descending.
    """
    if not candidates:
        return []
    model = _get_reranker()
    pairs = [[query, text] for _, text in candidates]
    scores = model.predict(pairs)
    indexed = list(enumerate(scores))
    indexed.sort(key=lambda x: x[1], reverse=True)
    return indexed[:top_k]


def _node_text(data: dict) -> str:
    """Build embedding text from node attributes.

    Only semantic information is included — label, signature, docstring,
    and source snippet. Structural information (kind, file path, decorators,
    class membership) is intentionally excluded because the graph signal
    already covers structural relationships via edges and community detection.
    Keeping embeddings purely semantic improves vector discrimination:
    without shared structural tokens (e.g. "function" on every function node),
    cosine similarity better reflects actual meaning differences.
    """
    parts = []
    label = data.get("label", "")
    if label:
        parts.append(label)
    if data.get("signature"):
        parts.append(data["signature"])
    if data.get("docstring"):
        parts.append(data["docstring"])
    if data.get("source_snippet"):
        parts.append(data["source_snippet"])
    return " ".join(parts)


def is_code_node(kind: str) -> bool:
    """Return True if this node kind should use the code embedding model."""
    return kind.lower() in CODE_KINDS


def _add_prefix(model_name: str, texts: list[str], mode: str = "passage") -> list[str]:
    """Add instruction prefix if required by the model (e.g. E5 family)."""
    prefixes = _PREFIX_MODELS.get(model_name)
    if not prefixes:
        return texts
    prefix = prefixes.get(mode, "")
    return [prefix + t for t in texts]


def _encode_batch(
    model_name: str,
    texts: list[str],
    batch_size: int = 64,
    prefix_mode: str = "passage",
) -> np.ndarray:
    """Encode texts with the specified model."""
    model = _get_model(model_name)
    prefixed = _add_prefix(model_name, texts, prefix_mode)
    return model.encode(
        prefixed,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,
    )


def embed_nodes_streaming(
    G: "nx.DiGraph",
    code_model: str = CODE_MODEL,
    text_model: str | None = None,
    batch_size: int = 64,
    skip_ids: set[str] | None = None,
) -> Generator[tuple[list[str], np.ndarray, str], None, None]:
    """Generate embeddings in memory-bounded batches with dual-model routing.

    Nodes are classified as code or text based on their 'kind' attribute,
    then embedded with the appropriate model.

    Args:
        text_model: Override text model (e.g. multilingual-e5-small).
        skip_ids: Node IDs to skip (already embedded). Used for incremental builds.

    Yields:
        (node_ids_batch, vectors_batch, model_type) tuples.
        model_type is "code" or "text".
    """
    effective_text = text_model or TEXT_MODEL
    code_ids, code_texts = [], []
    text_ids, text_texts = [], []

    skipped = 0
    skipped_incremental = 0
    for node_id, data in G.nodes(data=True):
        kind = data.get("kind", "")
        # Skip external/directory nodes — they lack source code and pollute
        # the vector index with low-information embeddings.
        if kind.lower() in SKIP_KINDS:
            skipped += 1
            continue
        # Skip nodes that already have embeddings (incremental build)
        if skip_ids and node_id in skip_ids:
            skipped_incremental += 1
            continue
        text = _node_text(data)
        if not text.strip():
            continue
        if is_code_node(kind):
            code_ids.append(node_id)
            code_texts.append(text)
        else:
            text_ids.append(node_id)
            text_texts.append(text)

    if skipped_incremental:
        logger.info(
            "Incremental embedding: skipped %d already-embedded nodes",
            skipped_incremental,
        )

    logger.debug(
        "Dual-model split: %d code nodes, %d text nodes, %d skipped, %d incremental-skip",
        len(code_ids), len(text_ids), skipped, skipped_incremental,
    )

    # Embed code nodes
    for i in range(0, len(code_texts), batch_size):
        batch_ids = code_ids[i : i + batch_size]
        vectors = _encode_batch(code_model, code_texts[i : i + batch_size], batch_size)
        yield batch_ids, vectors, "code"
        _memory_guard()

    # Embed text nodes
    for i in range(0, len(text_texts), batch_size):
        batch_ids = text_ids[i : i + batch_size]
        vectors = _encode_batch(effective_text, text_texts[i : i + batch_size], batch_size)
        yield batch_ids, vectors, "text"
        _memory_guard()


def embed_nodes(
    G: "nx.DiGraph",
    model_name: str | None = None,
    batch_size: int = 64,
) -> dict[str, np.ndarray]:
    """Generate embeddings for all nodes (legacy single-dict interface).

    If model_name is given, uses a single model for all nodes (backward compat).
    Otherwise uses dual-model routing.
    """
    if model_name is not None:
        # Legacy single-model path
        result = {}
        node_ids, texts = [], []
        for node_id, data in G.nodes(data=True):
            text = _node_text(data)
            if text.strip():
                node_ids.append(node_id)
                texts.append(text)
        if not texts:
            return result
        model = _get_model(model_name)
        vectors = model.encode(
            texts, batch_size=batch_size, show_progress_bar=False,
            normalize_embeddings=True,
        )
        return dict(zip(node_ids, vectors))

    # Dual-model path
    result = {}
    for batch_ids, batch_vecs, _ in embed_nodes_streaming(G, batch_size=batch_size):
        for nid, vec in zip(batch_ids, batch_vecs):
            result[nid] = vec
    return result


# --- Query embedding LRU cache ---
# Caches encoded query vectors to avoid re-encoding identical queries.
# Separate from the hybrid_search result cache: this cache is reusable
# even when search parameters (top_k, weights) change.
_query_cache: dict[str, dict[str, np.ndarray]] = {}
_QUERY_CACHE_MAX = 256
_query_cache_order: list[str] = []


def clear_query_cache() -> None:
    """Clear the query embedding cache."""
    _query_cache.clear()
    _query_cache_order.clear()


def embed_query(
    query: str,
    model_name: str | None = None,
) -> np.ndarray:
    """Embed a single query string using the text model (default)."""
    effective_model = model_name or TEXT_MODEL
    model = _get_model(effective_model)
    prefixed = _add_prefix(effective_model, [query], "query")[0]
    return model.encode(prefixed, normalize_embeddings=True)


def embed_query_dual(
    query: str,
    text_model: str | None = None,
) -> dict[str, np.ndarray]:
    """Embed query with both models for dual-index search.

    Uses an LRU cache to avoid re-encoding identical queries.

    Args:
        text_model: Override text model (e.g. multilingual-e5-small).

    Returns:
        {"code": code_vector, "text": text_vector}
    """
    effective_text = text_model or TEXT_MODEL
    cache_key = f"{query}|{effective_text}"
    if cache_key in _query_cache:
        return _query_cache[cache_key]

    code_query = _add_prefix(CODE_MODEL, [query], "query")[0]
    text_query = _add_prefix(effective_text, [query], "query")[0]

    result = {
        "code": _get_model(CODE_MODEL).encode(code_query, normalize_embeddings=True),
        "text": _get_model(effective_text).encode(text_query, normalize_embeddings=True),
    }

    _query_cache[cache_key] = result
    _query_cache_order.append(cache_key)
    if len(_query_cache_order) > _QUERY_CACHE_MAX:
        evict = _query_cache_order.pop(0)
        _query_cache.pop(evict, None)

    return result


def _memory_guard():
    """Trigger GC if memory exceeds 75% of budget, warn at limit."""
    rss = _get_process_rss()
    if rss <= 0:
        return
    threshold_75 = int(_MEMORY_LIMIT_BYTES * 0.75)
    if rss > threshold_75:
        gc.collect()
        rss_after = _get_process_rss()
        if rss > _MEMORY_LIMIT_BYTES:
            logger.warning(
                "Memory %.1f GB exceeds %.1f GB limit (%.1f GB after GC)",
                rss / (1024**3),
                _MEMORY_LIMIT_BYTES / (1024**3),
                rss_after / (1024**3),
            )
        else:
            logger.debug(
                "Memory %.1f GB > 75%% threshold, GC freed %.1f MB",
                rss / (1024**3),
                (rss - rss_after) / (1024**2),
            )


def get_memory_limit_bytes() -> int:
    """Return the current memory budget in bytes."""
    return _MEMORY_LIMIT_BYTES
