"""Pipeline orchestrator — runs the full knowledge graph build pipeline.

detect → extract → build → embed → cluster → analyze → store
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

from hedwig_kg.core.analyze import AnalysisResult, analyze
from hedwig_kg.core.build import build_graph, compute_edge_weights, compute_pagerank
from hedwig_kg.core.cluster import ClusterResult, hierarchical_cluster
from hedwig_kg.core.detect import DetectResult, detect
from hedwig_kg.core.extract import ExtractionResult
from hedwig_kg.core.ts_extract import extract_file_ts as extract_file
from hedwig_kg.storage.store import KnowledgeStore

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    detect_result: DetectResult | None = None
    extractions: list[ExtractionResult] = field(default_factory=list)
    graph: nx.DiGraph | None = None
    pagerank: dict[str, float] = field(default_factory=dict)
    cluster_result: ClusterResult | None = None
    analysis: AnalysisResult | None = None
    embeddings_count: int = 0
    db_path: str = ""


def _file_hash(path: Path) -> str:
    """Compute SHA-256 hash of file content for incremental builds."""
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run_pipeline(
    source_dir: str | Path,
    output_dir: str | Path | None = None,
    embed: bool = True,
    model_name: str | None = None,
    resolutions: list[float] | None = None,
    max_file_size: int = 1_000_000,
    on_progress: callable | None = None,
    incremental: bool = False,
) -> PipelineResult:
    """Run the full knowledge graph build pipeline.

    Args:
        source_dir: Directory to analyze.
        output_dir: Where to store the database (default: source_dir/.hedwig-kg).
        embed: Whether to generate embeddings (requires sentence-transformers).
        model_name: Sentence-transformers model name.
        resolutions: Leiden resolution parameters for hierarchical clustering.
        max_file_size: Skip files larger than this.
        on_progress: Callback(stage: str, detail: str) for progress updates.
        incremental: Skip unchanged files (based on content hash).

    Returns:
        PipelineResult with all intermediate and final results.
    """
    source_dir = Path(source_dir).resolve()
    if output_dir is None:
        output_dir = source_dir / ".hedwig-kg"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = output_dir / "knowledge.db"
    store = KnowledgeStore(db_path)
    result = PipelineResult(db_path=str(db_path))

    def _progress(stage: str, detail: str = "") -> None:
        if on_progress:
            on_progress(stage, detail)

    # Stage 1: Detect files
    _progress("detect", f"Scanning {source_dir}")
    result.detect_result = detect(source_dir, max_file_size=max_file_size)
    _progress("detect", f"Found {len(result.detect_result.files)} files")

    if not result.detect_result.files:
        store.set_meta("status", "empty")
        store.close()
        return result

    # Stage 2: Extract structures
    _progress("extract", f"Extracting from {len(result.detect_result.files)} files")

    # Load previous file hashes for incremental build
    prev_hashes: dict[str, str] = {}
    if incremental:
        raw = store.get_meta("file_hashes", "{}")
        try:
            prev_hashes = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            prev_hashes = {}

    new_hashes: dict[str, str] = {}
    skipped_count = 0

    for f in result.detect_result.files:
        try:
            fpath = str(f.path)
            if incremental:
                fhash = _file_hash(f.path)
                new_hashes[fpath] = fhash
                if prev_hashes.get(fpath) == fhash:
                    skipped_count += 1
                    continue

            ext = extract_file(fpath, f.language)
            result.extractions.append(ext)
        except Exception as e:
            _progress("extract", f"Error in {f.path}: {e}")

    if incremental and skipped_count > 0:
        _progress(
            "extract",
            f"Skipped {skipped_count} unchanged files",
        )

    _progress("extract", f"Extracted {sum(len(e.nodes) for e in result.extractions)} nodes")

    # Stage 3: Build graph
    _progress("build", "Building knowledge graph")
    new_graph = build_graph(result.extractions)

    # For incremental builds, merge new extractions into existing graph
    if incremental and skipped_count > 0:
        existing = store.load_graph()
        if existing.number_of_nodes() > 0:
            # Remove nodes from re-extracted files (they'll be replaced)
            re_extracted_files = set()
            for ext in result.extractions:
                for node in ext.nodes:
                    if node.file_path:
                        re_extracted_files.add(node.file_path)

            nodes_to_remove = [
                n for n, d in existing.nodes(data=True)
                if d.get("file_path", "") in re_extracted_files
            ]
            for n in nodes_to_remove:
                existing.remove_node(n)

            # Merge: add existing (unchanged) nodes/edges, then new ones
            result.graph = nx.compose(existing, new_graph)
        else:
            result.graph = new_graph
    else:
        result.graph = new_graph

    n, e = result.graph.number_of_nodes(), result.graph.number_of_edges()
    _progress("build", f"Graph: {n} nodes, {e} edges")

    # Stage 4: PageRank
    _progress("pagerank", "Computing importance scores")
    result.pagerank = compute_pagerank(result.graph)
    for node_id, score in result.pagerank.items():
        if result.graph.has_node(node_id):
            result.graph.nodes[node_id]["pagerank"] = score

    # Stage 5: Embeddings (optional) — dual-model streaming
    all_embeddings: dict = {}  # only kept for edge weight computation
    if embed:
        try:
            from hedwig_kg.query.embeddings import (
                CODE_MODEL,
                TEXT_MODEL,
                embed_nodes_streaming,
            )

            _progress("embed", f"Dual-model: code={CODE_MODEL}, text={TEXT_MODEL}")

            total_count = 0
            code_count = 0
            text_count = 0
            for batch_ids, batch_vecs, model_type in embed_nodes_streaming(
                result.graph
            ):
                batch_dict = dict(zip(batch_ids, batch_vecs))
                model_label = CODE_MODEL if model_type == "code" else TEXT_MODEL
                store.save_embeddings(
                    batch_dict, model_name=model_label, model_type=model_type,
                )
                all_embeddings.update(batch_dict)
                total_count += len(batch_ids)
                if model_type == "code":
                    code_count += len(batch_ids)
                else:
                    text_count += len(batch_ids)
                _progress(
                    "embed",
                    f"Embedded {total_count} nodes (code:{code_count} text:{text_count})",
                )

            result.embeddings_count = total_count
            _progress(
                "embed",
                f"Generated {total_count} embeddings (code:{code_count} text:{text_count})",
            )

            _progress("embed", "Computing edge weights")
            compute_edge_weights(result.graph, embeddings=all_embeddings)
            del all_embeddings
        except ImportError:
            _progress("embed", "sentence-transformers not available, skipping embeddings")
            compute_edge_weights(result.graph)
        except Exception as e:
            _progress("embed", f"Embedding error: {e}")
            compute_edge_weights(result.graph)
    else:
        compute_edge_weights(result.graph)

    # Stage 6: Cluster
    _progress("cluster", "Running hierarchical community detection")
    result.cluster_result = hierarchical_cluster(result.graph, resolutions=resolutions)
    _progress("cluster", f"Found {len(result.cluster_result.communities)} communities")

    # Annotate graph nodes with community IDs
    for node_id, comm_ids in result.cluster_result.node_to_community.items():
        if result.graph.has_node(node_id):
            result.graph.nodes[node_id]["community_ids"] = comm_ids

    # Generate community summaries for search indexing
    from hedwig_kg.core.cluster import summarize_communities
    summarize_communities(result.graph, result.cluster_result)
    _progress("cluster", "Community summaries generated")

    # Stage 7: Analyze
    _progress("analyze", "Running structural analysis")
    result.analysis = analyze(result.graph, pagerank=result.pagerank)
    _progress("analyze", f"Found {len(result.analysis.god_nodes)} god nodes")

    # Stage 8: Persist
    _progress("store", "Saving to database")
    store.save_graph(result.graph)
    store.save_communities(result.cluster_result.communities)
    store.set_meta("source_dir", str(source_dir))
    store.set_meta("model_name", model_name or "dual:bge-small+MiniLM")
    store.set_meta("status", "complete")

    # Save file hashes for incremental builds
    if new_hashes:
        # Merge with previous hashes (keep unchanged files)
        all_hashes = {**prev_hashes, **new_hashes}
        store.set_meta("file_hashes", json.dumps(all_hashes))

    # Build vector index
    if result.embeddings_count > 0:
        try:
            store.build_vector_index()
            _progress("store", "Vector index built")
        except Exception:
            logger.debug("Vector index build failed", exc_info=True)

    store.close()
    _progress("done", f"Knowledge base saved to {db_path}")

    return result
