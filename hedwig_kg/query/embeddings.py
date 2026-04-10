"""Embedding generation for knowledge graph nodes.

Uses sentence-transformers for local, privacy-preserving embeddings.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    import networkx as nx


# Lazy-loaded model cache
_model = None
_model_name = ""


def _get_model(model_name: str = "all-MiniLM-L6-v2"):
    """Lazy-load sentence-transformers model."""
    global _model, _model_name
    if _model is None or _model_name != model_name:
        import logging

        from sentence_transformers import SentenceTransformer

        logger = logging.getLogger(__name__)

        # Check if the model is already cached locally
        try:
            from huggingface_hub import try_to_load_from_cache
            cached = try_to_load_from_cache(model_name, "config.json")
            is_cached = isinstance(cached, str)
        except Exception:
            is_cached = False

        if not is_cached:
            logger.info(
                "Downloading embedding model '%s' (first time only, ~80MB)...",
                model_name,
            )
            try:
                from rich.console import Console
                Console(stderr=True).print(
                    f"[yellow]⬇ Downloading embedding model '{model_name}' "
                    f"(first time only, ~80MB)...[/yellow]"
                )
            except ImportError:
                pass

        _model = SentenceTransformer(model_name)
        _model_name = model_name
    return _model


def _node_text(data: dict) -> str:
    """Build embedding text from node attributes."""
    parts = []
    if data.get("kind"):
        parts.append(data["kind"])
    if data.get("label"):
        parts.append(data["label"])
    if data.get("signature"):
        parts.append(data["signature"])
    if data.get("docstring"):
        parts.append(data["docstring"])
    if data.get("source_snippet"):
        parts.append(data["source_snippet"][:300])
    return " ".join(parts)


def embed_nodes(
    G: "nx.DiGraph",
    model_name: str = "all-MiniLM-L6-v2",
    batch_size: int = 64,
) -> dict[str, np.ndarray]:
    """Generate embeddings for all nodes in the graph.

    Args:
        G: Knowledge graph with node attributes.
        model_name: Sentence-transformers model to use.
        batch_size: Batch size for encoding.

    Returns:
        Dict mapping node_id to embedding vector.
    """
    model = _get_model(model_name)

    node_ids = []
    texts = []
    for node_id, data in G.nodes(data=True):
        text = _node_text(data)
        if text.strip():
            node_ids.append(node_id)
            texts.append(text)

    if not texts:
        return {}

    vectors = model.encode(
        texts, batch_size=batch_size, show_progress_bar=False,
        normalize_embeddings=True,
    )

    return dict(zip(node_ids, vectors))


def embed_query(query: str, model_name: str = "all-MiniLM-L6-v2") -> np.ndarray:
    """Embed a single query string."""
    model = _get_model(model_name)
    return model.encode(query, normalize_embeddings=True)
