"""Pipeline orchestrator — runs the full code graph build pipeline.

detect → extract → build → embed → cluster → analyze → store
"""

from __future__ import annotations

import gc
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx

from hedwig_cg.core.analyze import AnalysisResult, analyze
from hedwig_cg.core.build import (
    build_graph,
    compute_edge_weights,
    compute_pagerank,
    merge_tier3_nodes,
)
from hedwig_cg.core.cluster import ClusterResult, hierarchical_cluster
from hedwig_cg.core.detect import DetectResult, detect
from hedwig_cg.core.extract import ExtractionResult
from hedwig_cg.core.ts_extract import extract_file_ts as extract_file
from hedwig_cg.storage.store import KnowledgeStore

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
    stage_timings: dict[str, float] = field(default_factory=dict)
    """Per-stage wall-clock seconds (e.g. {"detect": 0.12, "embed": 8.5})."""
    node_count: int = 0
    edge_count: int = 0

    def release_memory(self) -> None:
        """Free large in-memory objects after DB persistence.

        Call this after the pipeline completes and you no longer need
        the in-memory graph/cluster/analysis data (it's all in SQLite).
        """
        self.graph = None
        self.cluster_result = None
        self.analysis = None
        self.detect_result = None
        self.extractions.clear()
        self.pagerank.clear()
        gc.collect()


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
    lang: str = "auto",
) -> PipelineResult:
    """Run the full code graph build pipeline.

    Args:
        source_dir: Directory to analyze.
        output_dir: Where to store the database (default: source_dir/.hedwig-cg).
        embed: Whether to generate embeddings (requires sentence-transformers).
        model_name: Sentence-transformers model name.
        resolutions: Leiden resolution parameters for hierarchical clustering.
        max_file_size: Skip files larger than this.
        on_progress: Callback(stage: str, detail: str) for progress updates.
        incremental: Skip unchanged files (based on content hash).
        lang: Language mode — "auto" (detect from text nodes), "en" (English-only
            models), or "multilingual" (force multilingual text model).

    Returns:
        PipelineResult with all intermediate and final results.
    """
    source_dir = Path(source_dir).resolve()
    if output_dir is None:
        output_dir = source_dir / ".hedwig-cg"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = output_dir / "knowledge.db"
    store = KnowledgeStore(db_path)
    result = PipelineResult(db_path=str(db_path))

    def _progress(stage: str, detail: str = "") -> None:
        if on_progress:
            on_progress(stage, detail)

    _stage_start: float = 0.0

    def _start_stage(name: str) -> None:
        nonlocal _stage_start
        _stage_start = time.perf_counter()

    def _end_stage(name: str) -> None:
        elapsed = time.perf_counter() - _stage_start
        result.stage_timings[name] = elapsed
        _progress(name, f"completed in {elapsed:.1f}s")

    # Stage 1: Detect files
    _start_stage("detect")
    _progress("detect", f"Scanning {source_dir}")
    result.detect_result = detect(source_dir, max_file_size=max_file_size)
    _end_stage("detect")
    _progress("detect", f"Found {len(result.detect_result.files)} files")

    if not result.detect_result.files:
        store.set_meta("status", "empty")
        store.close()
        return result

    # Stage 2: Extract structures
    _start_stage("extract")
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

    _end_stage("extract")
    total_nodes = sum(len(e.nodes) for e in result.extractions)
    _progress("extract", f"Extracted {total_nodes} nodes")

    # Stage 3: Build graph
    _start_stage("build")
    _progress("build", "Building code graph")

    # Collect re-extracted file paths before clearing extractions
    re_extracted_files: set[str] = set()
    for ext in result.extractions:
        for node in ext.nodes:
            if node.file_path:
                re_extracted_files.add(node.file_path)

    new_graph = build_graph(result.extractions)
    new_graph = merge_tier3_nodes(new_graph)

    # For incremental builds, merge new extractions into existing graph
    if incremental and skipped_count > 0:
        existing = store.load_graph()
        if existing.number_of_nodes() > 0:
            # Remove nodes from re-extracted files (they'll be replaced)
            nodes_to_remove = [
                n for n, d in existing.nodes(data=True)
                if d.get("file_path", "") in re_extracted_files
            ]
            for n in nodes_to_remove:
                existing.remove_node(n)

            # Merge: add existing (unchanged) nodes/edges, then new ones
            result.graph = nx.compose(existing, new_graph)
            del existing
        else:
            result.graph = new_graph
    else:
        result.graph = new_graph
    del new_graph

    # Stage 3.5: Git co-change enrichment
    _start_stage("git_cochange")
    _progress("git_cochange", "Extracting co-change relationships from git history")
    try:
        from hedwig_cg.core.git_cochange import enrich_graph_with_cochange

        cochange_count = enrich_graph_with_cochange(
            result.graph,
            source_dir,
            on_progress=on_progress,
        )
        if cochange_count > 0:
            _progress("git_cochange", f"Added {cochange_count} co-change edges")
        else:
            _progress(
                "git_cochange",
                "No co-change edges (not a git repo or insufficient history)",
            )
    except Exception as e:
        _progress("git_cochange", f"Skipped: {e}")
        logger.debug("Git co-change extraction failed", exc_info=True)
    _end_stage("git_cochange")

    n, e = result.graph.number_of_nodes(), result.graph.number_of_edges()
    result.node_count = n
    result.edge_count = e
    _progress("build", f"Graph: {n} nodes, {e} edges")

    # Stage 4: PageRank
    _start_stage("pagerank")
    _progress("pagerank", "Computing importance scores")
    result.pagerank = compute_pagerank(result.graph)
    for node_id, score in result.pagerank.items():
        if result.graph.has_node(node_id):
            result.graph.nodes[node_id]["pagerank"] = score
    _end_stage("pagerank")

    # Stage 5: Embeddings (optional) — dual-model streaming
    _start_stage("embed")
    all_embeddings: dict = {}  # only kept for edge weight computation
    detected_lang = lang if lang != "auto" else "multilingual"
    effective_text_model = "intfloat/multilingual-e5-small"
    if embed:
        try:
            from hedwig_cg.query.embeddings import (
                CODE_MODEL,
                TEXT_MODEL,
                embed_nodes_streaming,
            )

            effective_text_model = TEXT_MODEL

            _progress("embed", f"Dual-model: code={CODE_MODEL}, text={effective_text_model}")

            # Incremental embedding: skip nodes that already have embeddings
            skip_ids: set[str] | None = None
            if incremental:
                existing_ids = store.get_embedded_node_ids()
                # Nodes from re-extracted files should NOT be skipped
                nodes_from_changed = {
                    n for n, d in result.graph.nodes(data=True)
                    if d.get("file_path", "") in re_extracted_files
                }
                skip_ids = existing_ids - nodes_from_changed
                if skip_ids:
                    _progress("embed", f"Incremental: reusing {len(skip_ids)} existing embeddings")

            # Free incremental tracking sets — no longer needed
            del re_extracted_files
            if skip_ids is not None:
                del existing_ids, nodes_from_changed

            total_count = 0
            code_count = 0
            text_count = 0
            for batch_ids, batch_vecs, model_type in embed_nodes_streaming(
                result.graph,
                text_model=effective_text_model,
                skip_ids=skip_ids,
            ):
                batch_dict = dict(zip(batch_ids, batch_vecs))
                model_label = CODE_MODEL if model_type == "code" else effective_text_model
                store.save_embeddings(
                    batch_dict, model_name=model_label, model_type=model_type,
                )
                all_embeddings.update(batch_dict)
                del batch_dict  # free batch immediately after use
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
    _end_stage("embed")

    # Stage 6: Cluster
    _start_stage("cluster")
    _progress("cluster", "Running hierarchical community detection")
    result.cluster_result = hierarchical_cluster(result.graph, resolutions=resolutions)
    _progress("cluster", f"Found {len(result.cluster_result.communities)} communities")

    # Annotate graph nodes with community IDs
    for node_id, comm_ids in result.cluster_result.node_to_community.items():
        if result.graph.has_node(node_id):
            result.graph.nodes[node_id]["community_ids"] = comm_ids

    # Generate community summaries for search indexing
    from hedwig_cg.core.cluster import summarize_communities
    summarize_communities(result.graph, result.cluster_result)
    _end_stage("cluster")
    _progress("cluster", "Community summaries generated")

    # Stage 7: Analyze
    _start_stage("analyze")
    _progress("analyze", "Running structural analysis")
    result.analysis = analyze(result.graph, pagerank=result.pagerank)
    _end_stage("analyze")
    _progress("analyze", f"Found {len(result.analysis.god_nodes)} god nodes")

    # Stage 8: Persist
    _start_stage("store")
    _progress("store", "Saving to database")
    store.save_graph(result.graph)
    store.save_communities(result.cluster_result.communities)
    store.set_meta("source_dir", str(source_dir))
    store.set_meta("model_name", model_name or "dual:bge-small+e5-small")
    store.set_meta("lang", detected_lang)
    store.set_meta("text_model", effective_text_model)
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

    # Clear search and query embedding caches after rebuild (stale results)
    try:
        from hedwig_cg.query.hybrid import clear_search_cache
        clear_search_cache()
    except ImportError:
        pass
    try:
        from hedwig_cg.query.embeddings import clear_query_cache
        clear_query_cache()
    except ImportError:
        pass

    store.close()
    _end_stage("store")

    total = sum(result.stage_timings.values())
    result.stage_timings["total"] = total
    _progress("done", f"Code graph saved to {db_path} ({total:.1f}s total)")

    return result
