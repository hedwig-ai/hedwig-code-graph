"""Embedding generation for knowledge graph nodes.

Dual-model architecture:
- Code nodes (function, class, method, module) → BAAI/bge-small-en-v1.5
- Text nodes (heading, section, docstring, etc.) → all-MiniLM-L6-v2

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
TEXT_MODEL = "all-MiniLM-L6-v2"

# Node kinds routed to the code model
CODE_KINDS = frozenset({
    "function", "class", "method", "module", "variable",
    "interface", "enum", "struct", "trait", "import",
    "constructor", "property", "decorator",
})

# Node kinds excluded from embedding (these are references to external
# libraries/symbols that lack source code, docstrings, and file paths,
# polluting the vector search space with low-information vectors).
SKIP_KINDS = frozenset({"external", "directory"})

# Memory budget: 2 GB max for embeddings pipeline
_MEMORY_LIMIT_BYTES = 2 * 1024 * 1024 * 1024

# Model cache directory: ~/.hedwig-kg/models/
_MODEL_CACHE_DIR = Path.home() / ".hedwig-kg" / "models"

# Lazy-loaded model cache (keyed by model name)
_models: dict[str, object] = {}


def _get_model(model_name: str):
    """Lazy-load sentence-transformers model, caching to ~/.hedwig-kg/models/."""
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
                    f"(first time only, saved to ~/.hedwig-kg/models/)...[/yellow]"
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


def _node_text(data: dict) -> str:
    """Build embedding text from node attributes.

    Includes file path context so queries like "store.py methods" or
    "functions in analyze.py" match via cosine similarity.
    Also extracts parent class context from dotted labels (e.g.
    "ClassName.method_name") so that method embeddings encode their
    class membership — enabling queries like "AuthHandler methods".
    """
    parts = []
    kind = data.get("kind", "")
    label = data.get("label", "")
    if kind:
        parts.append(kind)
    if label:
        parts.append(label)
    # Extract parent class context from dotted label (e.g. "MyClass.my_method")
    # This enriches method embeddings with class membership information.
    if kind in ("method", "constructor", "property") and "." in label:
        class_name = label.rsplit(".", 1)[0]
        parts.append(f"method of {class_name}")
    # Add filename for file-based query matching (e.g. "store.py methods")
    fp = data.get("file_path", "")
    if fp:
        # Extract just the filename from absolute/relative paths
        from pathlib import PurePosixPath
        fname = PurePosixPath(fp).name
        if fname:
            parts.append(f"in {fname}")
    if data.get("signature"):
        parts.append(data["signature"])
    if data.get("docstring"):
        parts.append(data["docstring"])
    if data.get("source_snippet"):
        parts.append(data["source_snippet"][:300])
    return " ".join(parts)


def is_code_node(kind: str) -> bool:
    """Return True if this node kind should use the code embedding model."""
    return kind.lower() in CODE_KINDS


def _encode_batch(
    model_name: str,
    texts: list[str],
    batch_size: int = 64,
) -> np.ndarray:
    """Encode texts with the specified model."""
    model = _get_model(model_name)
    return model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
        normalize_embeddings=True,
    )


def embed_nodes_streaming(
    G: "nx.DiGraph",
    code_model: str = CODE_MODEL,
    text_model: str = TEXT_MODEL,
    batch_size: int = 64,
) -> Generator[tuple[list[str], np.ndarray, str], None, None]:
    """Generate embeddings in memory-bounded batches with dual-model routing.

    Nodes are classified as code or text based on their 'kind' attribute,
    then embedded with the appropriate model.

    Yields:
        (node_ids_batch, vectors_batch, model_type) tuples.
        model_type is "code" or "text".
    """
    code_ids, code_texts = [], []
    text_ids, text_texts = [], []

    skipped = 0
    for node_id, data in G.nodes(data=True):
        kind = data.get("kind", "")
        # Skip external/directory nodes — they lack source code and pollute
        # the vector index with low-information embeddings.
        if kind.lower() in SKIP_KINDS:
            skipped += 1
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

    logger.debug(
        "Dual-model split: %d code nodes, %d text nodes, %d skipped",
        len(code_ids), len(text_ids), skipped,
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
        vectors = _encode_batch(text_model, text_texts[i : i + batch_size], batch_size)
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
    model = _get_model(model_name or TEXT_MODEL)
    return model.encode(query, normalize_embeddings=True)


def embed_query_dual(query: str) -> dict[str, np.ndarray]:
    """Embed query with both models for dual-index search.

    Uses an LRU cache to avoid re-encoding identical queries.

    Returns:
        {"code": code_vector, "text": text_vector}
    """
    if query in _query_cache:
        return _query_cache[query]

    result = {
        "code": _get_model(CODE_MODEL).encode(query, normalize_embeddings=True),
        "text": _get_model(TEXT_MODEL).encode(query, normalize_embeddings=True),
    }

    _query_cache[query] = result
    _query_cache_order.append(query)
    if len(_query_cache_order) > _QUERY_CACHE_MAX:
        evict = _query_cache_order.pop(0)
        _query_cache.pop(evict, None)

    return result


def _memory_guard():
    """Trigger GC if memory exceeds budget."""
    rss = _get_process_rss()
    if rss > _MEMORY_LIMIT_BYTES:
        gc.collect()
        logger.warning(
            "Memory usage %.1f GB exceeds %.1f GB limit, GC triggered",
            rss / (1024**3),
            _MEMORY_LIMIT_BYTES / (1024**3),
        )
