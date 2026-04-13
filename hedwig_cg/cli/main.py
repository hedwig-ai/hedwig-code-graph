"""CLI interface for hedwig-cg.

Usage:
    hedwig-cg build <source_dir> [--output <dir>] [--model <name>]
    hedwig-cg search <query> [--db <path>] [--top-k <n>]
    hedwig-cg stats [--db <path>]
    hedwig-cg export [--db <path>] [--format json|graphml]
"""

from __future__ import annotations

from pathlib import Path

import click

from ._helpers import (
    human_fail,
    human_ok,
    human_warn,
    json_error,
    json_out,
    resolve_db,
    suppress_library_logs,
)
from .integrations import register_integration_commands


@click.group()
@click.version_option(version=None, prog_name="hedwig-cg", package_name="hedwig-cg")
@click.pass_context
def cli(ctx):
    """hedwig-cg: Local-first code graph with hybrid search."""
    ctx.ensure_object(dict)
    suppress_library_logs()


@cli.command()
@click.argument("source_dir", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output directory for the database")
@click.option("--model", default=None,
              help="Override embedding model (default: dual-model, code=bge-small + text=MiniLM)")
@click.option("--max-file-size", default=1_000_000, type=int, help="Max file size in bytes")
@click.option("--incremental", is_flag=True, help="Skip unchanged files (faster rebuilds)")
@click.pass_context
def build(
    ctx, source_dir: str, output: str | None,
    model: str, max_file_size: int, incremental: bool,
):
    """Build code graph from a source directory."""
    from hedwig_cg.core.pipeline import run_pipeline

    result = run_pipeline(
        source_dir=source_dir,
        output_dir=output,
        embed=True,
        model_name=model,
        max_file_size=max_file_size,
        on_progress=None,
        incremental=incremental,
        lang="auto",
    )

    # Capture summary values before releasing memory
    files_detected = len(result.detect_result.files) if result.detect_result else 0
    files_skipped = len(result.detect_result.skipped) if result.detect_result else 0
    nodes = result.node_count
    edges = result.edge_count
    communities = len(result.cluster_result.communities) if result.cluster_result else 0
    embeddings = result.embeddings_count
    db_path = result.db_path
    stage_timings = result.stage_timings or {}

    # Release large in-memory objects (all data is persisted in SQLite)
    result.release_memory()

    json_out({
        "files_detected": files_detected,
        "files_skipped": files_skipped,
        "nodes": nodes,
        "edges": edges,
        "communities": communities,
        "embeddings": embeddings,
        "database": db_path,
        "stage_timings": stage_timings,
    })


@cli.command()
@click.argument("query")
@click.option("--db", type=click.Path(), default=None, help="Path to knowledge.db")
@click.option("--top-k", default=30, type=int, help="Number of results")
@click.option("--source-dir", type=click.Path(), default=".",
              help="Source dir (to find default DB)")
@click.option("--fast", is_flag=True, default=False,
              help="Fast mode: text model only (lower latency, slightly reduced accuracy)")
@click.option("--expand", is_flag=True, default=False,
              help="Two-stage query expansion: re-search with neighbor terms for broader recall")
@click.pass_context
def search(ctx, query: str, db: str | None, top_k: int, source_dir: str, fast: bool, expand: bool):
    """Search the code graph with hybrid vector + graph + keyword search."""
    from hedwig_cg.query.hybrid import expanded_search, extract_result_edges, hybrid_search
    from hedwig_cg.storage.store import KnowledgeStore

    db_path = resolve_db(db, source_dir)
    if not db_path:
        json_error("No knowledge base found. Run 'hedwig-cg build' first.")

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    if G.number_of_nodes() == 0:
        json_out([])
        store.close()
        return

    # Build vector index
    try:
        store.build_vector_index()
    except Exception:
        pass

    # Read text model from DB metadata (set during build)
    text_model = store.get_meta("text_model", None)
    search_fn = expanded_search if expand else hybrid_search
    results = search_fn(
        query, store, G, top_k=top_k, fast=fast, text_model=text_model,
    )

    # Compact output: omit empty fields, use relative paths, round floats
    source_dir_str = str(Path(source_dir).resolve()) + "/" if source_dir else ""

    def _compact_result(r):
        rel_path = r.file_path
        if source_dir_str and rel_path.startswith(source_dir_str):
            rel_path = rel_path[len(source_dir_str):]
        d = {
            "label": r.label,
            "kind": r.kind,
            "file": rel_path,
            "lines": [r.start_line, getattr(r, "end_line", 0)],
            "score": round(r.score, 3),
        }
        sig = getattr(r, "signature", "")
        if sig:
            d["sig"] = sig
        doc = getattr(r, "docstring", "")
        if doc:
            d["doc"] = doc
        return d

    edges = extract_result_edges(G, results)
    json_out({
        "results": [_compact_result(r) for r in results],
        "edges": edges,
    })
    store.close()


# --- Per-signal search commands ---

def _signal_options(fn):
    """Common options for per-signal search commands."""
    fn = click.argument("query")(fn)
    fn = click.option("--db", type=click.Path(), default=None)(fn)
    fn = click.option("--top-k", default=30, type=int, help="Number of results")(fn)
    fn = click.option("--source-dir", type=click.Path(), default=".")(fn)
    return fn


def _node_dict(G, node_id: str, source_dir_str: str) -> dict | None:
    """Build a compact dict for a node ID."""
    data = G.nodes.get(node_id)
    if not data:
        return None
    rel_path = data.get("file_path", "")
    if source_dir_str and rel_path.startswith(source_dir_str):
        rel_path = rel_path[len(source_dir_str):]
    d = {
        "label": data.get("label", node_id),
        "kind": data.get("kind", ""),
        "file": rel_path,
        "lines": [data.get("start_line", 0), data.get("end_line", 0)],
    }
    sig = data.get("signature", "")
    if sig:
        d["sig"] = sig
    return d


@cli.command(name="search-vector")
@_signal_options
def search_vector(query: str, db: str | None, top_k: int, source_dir: str):
    """Search using code + text vector similarity only (FAISS cosine)."""
    from hedwig_cg.query.embeddings import embed_query_dual
    from hedwig_cg.storage.store import KnowledgeStore

    db_path = resolve_db(db, source_dir)
    if not db_path:
        json_error("No knowledge base found.")
    store = KnowledgeStore(db_path)
    G = store.load_graph()
    try:
        store.build_vector_index()
    except Exception:
        pass

    text_model = store.get_meta("text_model", None)
    vecs = embed_query_dual(query, text_model=text_model)
    source_dir_str = str(Path(source_dir).resolve()) + "/"

    results = []
    for model_type, vec in [("code", vecs["code"]), ("text", vecs["text"])]:
        if vec is not None:
            hits = store.vector_search(vec, top_k=top_k, model_type=model_type)
            for nid, score in hits:
                d = _node_dict(G, nid, source_dir_str)
                if d:
                    d["score"] = round(float(score), 3)
                    d["model"] = model_type
                    results.append(d)

    # Deduplicate, keep highest score
    seen = {}
    for r in results:
        key = r["label"]
        if key not in seen or r["score"] > seen[key]["score"]:
            seen[key] = r
    json_out(sorted(seen.values(), key=lambda x: x["score"], reverse=True)[:top_k])
    store.close()


@cli.command(name="search-keyword")
@_signal_options
def search_keyword(query: str, db: str | None, top_k: int, source_dir: str):
    """Search using FTS5 keyword matching only (BM25 ranking)."""
    from hedwig_cg.query.hybrid import extract_search_terms
    from hedwig_cg.storage.store import KnowledgeStore

    db_path = resolve_db(db, source_dir)
    if not db_path:
        json_error("No knowledge base found.")
    store = KnowledgeStore(db_path)
    source_dir_str = str(Path(source_dir).resolve()) + "/"

    terms = extract_search_terms(query)
    if not terms:
        json_out([])
        store.close()
        return

    hits = store.keyword_search(terms, top_k=top_k)
    results = []
    for h in hits:
        rel_path = h.get("file_path", "")
        if source_dir_str and rel_path.startswith(source_dir_str):
            rel_path = rel_path[len(source_dir_str):]
        results.append({
            "label": h.get("label", h.get("node_id", "")),
            "kind": h.get("kind", ""),
            "file": rel_path,
            "score": round(h.get("score", 0), 3),
        })
    json_out(results)
    store.close()


@cli.command(name="search-graph")
@_signal_options
def search_graph(query: str, db: str | None, top_k: int, source_dir: str):
    """Search using graph expansion only (BFS from vector seeds)."""
    from hedwig_cg.query.embeddings import embed_query_dual
    from hedwig_cg.query.hybrid import _weighted_expand
    from hedwig_cg.storage.store import KnowledgeStore

    db_path = resolve_db(db, source_dir)
    if not db_path:
        json_error("No knowledge base found.")
    store = KnowledgeStore(db_path)
    G = store.load_graph()
    try:
        store.build_vector_index()
    except Exception:
        pass

    text_model = store.get_meta("text_model", None)
    vecs = embed_query_dual(query, text_model=text_model)
    source_dir_str = str(Path(source_dir).resolve()) + "/"

    # Get vector seeds first
    seeds = []
    for model_type, vec in [("code", vecs["code"]), ("text", vecs["text"])]:
        if vec is not None:
            hits = store.vector_search(vec, top_k=5, model_type=model_type)
            seeds.extend(hits)

    # BFS expand from seeds
    seen: set[str] = set()
    expanded: list[tuple[str, float]] = []
    for nid, score in seeds:
        _weighted_expand(G, nid, score, max_hops=2, seen=seen, out=expanded)

    expanded.sort(key=lambda x: x[1], reverse=True)
    results = []
    for nid, score in expanded[:top_k]:
        d = _node_dict(G, nid, source_dir_str)
        if d:
            d["score"] = round(score, 3)
            results.append(d)
    json_out(results)
    store.close()


@cli.command(name="search-community")
@_signal_options
def search_community(query: str, db: str | None, top_k: int, source_dir: str):
    """Search using community cluster matching only."""
    from hedwig_cg.query.hybrid import extract_search_terms
    from hedwig_cg.storage.store import KnowledgeStore

    db_path = resolve_db(db, source_dir)
    if not db_path:
        json_error("No knowledge base found.")
    store = KnowledgeStore(db_path)
    G = store.load_graph()
    source_dir_str = str(Path(source_dir).resolve()) + "/"

    terms = extract_search_terms(query)
    if not terms:
        json_out([])
        store.close()
        return

    comm_results = store.community_search(terms, top_k=10)
    results = []
    seen = set()
    for comm in comm_results:
        for nid in comm.get("node_ids", []):
            if nid in seen:
                continue
            seen.add(nid)
            d = _node_dict(G, nid, source_dir_str)
            if d:
                d["community"] = comm.get("community_id", "")
                d["community_summary"] = comm.get("summary", "")[:100]
                results.append(d)
    json_out(results[:top_k])
    store.close()


@cli.command()
@click.option("--db", type=click.Path(), default=None)
@click.option("--source-dir", type=click.Path(), default=".", help="Source dir")
@click.pass_context
def stats(ctx, db: str | None, source_dir: str):
    """Show code graph statistics."""
    from hedwig_cg.storage.store import KnowledgeStore

    db_path = resolve_db(db, source_dir)
    if not db_path:
        json_error("No knowledge base found. Run 'hedwig-cg build' first.")

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    # Node kinds
    kinds: dict[str, int] = {}
    for _, data in G.nodes(data=True):
        k = data.get("kind", "unknown")
        kinds[k] = kinds.get(k, 0) + 1

    # Edge confidence
    conf: dict[str, int] = {}
    for _, _, data in G.edges(data=True):
        c = data.get("confidence", "EXTRACTED")
        conf[c] = conf.get(c, 0) + 1

    import networkx as nx

    density = None
    components = None
    avg_clustering = None
    if G.number_of_nodes() > 0:
        density = nx.density(G)
        undirected = G.to_undirected()
        components = nx.number_connected_components(undirected)
        try:
            avg_clustering = nx.average_clustering(undirected)
        except Exception:
            pass

    comm_count = store.conn.execute("SELECT COUNT(*) FROM communities").fetchone()[0]
    emb_count = store.conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]

    json_out({
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "node_kinds": kinds,
        "edge_confidence": conf,
        "density": density,
        "connected_components": components,
        "avg_clustering_coeff": avg_clustering,
        "communities": comm_count,
        "embeddings": emb_count,
        "database": str(db_path),
        "source": store.get_meta("source_dir", "unknown"),
    })
    store.close()


@cli.command()
@click.option("--db", type=click.Path(), default=None)
@click.option("--source-dir", type=click.Path(), default=".", help="Source dir")
@click.option("--level", type=int, default=None, help="Filter by hierarchy level")
@click.option("--search", "query", type=str, default=None, help="Search community summaries")
@click.pass_context
def communities(ctx, db: str | None, source_dir: str, level: int | None, query: str | None):
    """List and search communities in the code graph."""
    from hedwig_cg.storage.store import KnowledgeStore

    db_path = resolve_db(db, source_dir)
    if not db_path:
        json_error("No knowledge base found. Run 'hedwig-cg build' first.")

    store = KnowledgeStore(db_path)

    if query:
        terms = [t.lower() for t in query.split() if len(t) > 2]
        results = store.community_search(terms, top_k=10)
        json_out([
            {
                "community_id": r["community_id"],
                "level": r["level"],
                "node_count": len(r["node_ids"]),
                "score": r["score"],
                "summary": r["summary"],
                "node_ids": r["node_ids"],
            }
            for r in results
        ])
        store.close()
        return

    sql = "SELECT id, level, resolution, summary FROM communities"
    params: list = []
    if level is not None:
        sql += " WHERE level = ?"
        params.append(level)
    sql += " ORDER BY level, id"
    rows = store.conn.execute(sql, params).fetchall()

    json_out([
        {
            "id": row["id"],
            "level": row["level"],
            "resolution": row["resolution"],
            "summary": row["summary"],
        }
        for row in rows
    ])
    store.close()


@cli.command()
@click.option("--db", type=click.Path(), default=None)
@click.option("--source-dir", type=click.Path(), default=".")
@click.option("--format", "fmt", type=click.Choice(["json", "graphml", "d3"]), default="json")
@click.option("--output", "-o", type=click.Path(), default=None)
def export(db: str | None, source_dir: str, fmt: str, output: str | None):
    """Export the code graph."""
    import json

    import networkx as nx

    from hedwig_cg.storage.store import KnowledgeStore

    db_path = resolve_db(db, source_dir)
    if not db_path:
        json_error("No knowledge base found.")

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    if fmt == "d3":
        data = _graph_to_d3(G)
        out = output or "code_graph_d3.json"
        Path(out).write_text(json.dumps(data, indent=2, default=str))
    elif fmt == "json":
        data = nx.node_link_data(G)
        out = output or "code_graph.json"
        Path(out).write_text(json.dumps(data, indent=2, default=str))
    elif fmt == "graphml":
        # GraphML doesn't support list attributes, convert them
        G2 = G.copy()
        for n in G2.nodes():
            for k, v in list(G2.nodes[n].items()):
                if isinstance(v, (list, dict)):
                    G2.nodes[n][k] = str(v)
        out = output or "code_graph.graphml"
        nx.write_graphml(G2, out)

    json_out({"exported": str(out), "format": fmt})
    store.close()


def _graph_to_d3(G) -> dict:
    """Convert NetworkX DiGraph to D3.js force-directed graph format.

    Output: {nodes: [{id, label, kind, group, size, ...}],
             links: [{source, target, relation, value}]}
    """
    # Assign group IDs by kind for D3 color grouping
    kinds = sorted({d.get("kind", "unknown") for _, d in G.nodes(data=True)})
    kind_to_group = {k: i for i, k in enumerate(kinds)}

    # Compute PageRank range for node sizing
    pageranks = [d.get("pagerank", 0.0) for _, d in G.nodes(data=True)]
    pr_max = max(pageranks) if pageranks else 1.0

    nodes = []
    for node_id, data in G.nodes(data=True):
        pr = data.get("pagerank", 0.0)
        nodes.append({
            "id": node_id,
            "label": data.get("label", node_id),
            "kind": data.get("kind", "unknown"),
            "group": kind_to_group.get(data.get("kind", "unknown"), 0),
            "size": 4 + 16 * (pr / pr_max) if pr_max > 0 else 4,
            "file_path": data.get("file_path", ""),
            "community_ids": data.get("community_ids", []),
        })

    links = []
    for u, v, data in G.edges(data=True):
        links.append({
            "source": u,
            "target": v,
            "relation": data.get("relation", ""),
            "value": data.get("weight", 1.0),
        })

    return {
        "nodes": nodes,
        "links": links,
        "metadata": {
            "node_count": len(nodes),
            "link_count": len(links),
            "kind_groups": {k: i for k, i in kind_to_group.items()},
        },
    }


@cli.command()
@click.option("--db", type=click.Path(), default=None)
@click.option("--source-dir", type=click.Path(), default=".", help="Source dir")
@click.option("--output", "-o", type=click.Path(), default=None)
@click.option("--max-nodes", default=500, type=int,
              help="Max nodes to include (by PageRank)")
@click.option("--offline", is_flag=True,
              help="Inline D3.js for airgapped/offline use (adds ~280KB)")
def visualize(
    db: str | None, source_dir: str, output: str | None,
    max_nodes: int, offline: bool,
):
    """Generate an interactive HTML visualization of the code graph."""
    from hedwig_cg.storage.store import KnowledgeStore

    db_path = resolve_db(db, source_dir)
    if not db_path:
        json_error("No knowledge base found. Run 'hedwig-cg build' first.")

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    # Trim to top N nodes by PageRank for browser performance
    if G.number_of_nodes() > max_nodes:
        ranked = sorted(G.nodes(data=True), key=lambda x: x[1].get("pagerank", 0), reverse=True)
        keep = {n for n, _ in ranked[:max_nodes]}
        G = G.subgraph(keep).copy()

    d3_data = _graph_to_d3(G)
    html = _build_viz_html(d3_data, offline=offline)

    out = output or "code_graph.html"
    Path(out).write_text(html)

    json_out({
        "saved": str(out),
        "nodes": d3_data["metadata"]["node_count"],
        "links": d3_data["metadata"]["link_count"],
        "offline": offline,
        "url": f"file://{Path(out).resolve()}",
    })
    store.close()


@cli.command()
@click.option("--source-dir", type=click.Path(), default=".",
              help="Source directory whose .hedwig-cg/ to remove")
@click.option("--db", type=click.Path(), default=None,
              help="Specific database file to remove")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def clean(source_dir: str, db: str | None, yes: bool):
    """Remove the knowledge base database and associated data."""
    import shutil

    if db:
        target = Path(db)
        if not target.exists():
            click.echo("Database not found.")
            return
        if not yes:
            click.confirm(f"Delete {target}?", abort=True)
        target.unlink()
        click.echo(f"Removed {target}")
    else:
        kb_dir = Path(source_dir).resolve() / ".hedwig-cg"
        if not kb_dir.exists():
            click.echo("No .hedwig-cg/ directory found.")
            return
        if not yes:
            click.confirm(f"Delete {kb_dir}/?", abort=True)
        shutil.rmtree(kb_dir)
        click.echo(f"Removed {kb_dir}/")


@cli.command()
@click.option("--db", type=click.Path(), default=None, help="Path to knowledge.db")
@click.option("--source-dir", type=click.Path(), default=".", help="Source dir")
@click.option("--top-k", default=30, type=int, help="Number of results per query")
def query(db: str | None, source_dir: str, top_k: int):
    """Interactive search REPL for exploring the code graph.

    Launches an interactive session where you can run multiple searches
    without reloading the graph. Type 'quit' or 'exit' to leave.

    Special commands:
      :node <id>   - Show node details
      :stats       - Show graph statistics
      :quit        - Exit the REPL
    """
    from hedwig_cg.query.hybrid import hybrid_search
    from hedwig_cg.storage.store import KnowledgeStore

    db_path = resolve_db(db, source_dir)
    if not db_path:
        json_error("No knowledge base found. Run 'hedwig-cg build' first.")

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    if G.number_of_nodes() == 0:
        json_out({"message": "Knowledge base is empty."})
        store.close()
        return

    try:
        store.build_vector_index()
    except Exception:
        pass

    # Preload embedding models in background thread so first search is fast
    import threading
    def _preload_models():
        try:
            from hedwig_cg.query.embeddings import CODE_MODEL, TEXT_MODEL, _get_model
            _get_model(CODE_MODEL)
            _get_model(TEXT_MODEL)
        except Exception:
            pass
    threading.Thread(target=_preload_models, daemon=True).start()

    json_out({"status": "ready", "nodes": G.number_of_nodes(),
               "edges": G.number_of_edges()})

    while True:
        try:
            user_input = click.prompt("hedwig-cg", prompt_suffix="> ")
        except (EOFError, KeyboardInterrupt):
            break

        user_input = user_input.strip()
        if not user_input:
            continue
        if user_input.lower() in (":quit", ":exit", "quit", "exit"):
            break

        if user_input.startswith(":node "):
            node_id = user_input[6:].strip()
            _repl_show_node(G, node_id)
        elif user_input == ":stats":
            json_out({"nodes": G.number_of_nodes(),
                        "edges": G.number_of_edges()})
        else:
            results = hybrid_search(user_input, store, G, top_k=top_k)
            json_out([{"label": r.label, "kind": r.kind, "score": round(r.score, 3)}
                       for r in results])

    store.close()
    json_out({"status": "session_ended"})


def _repl_show_node(G, node_id: str) -> None:
    """Show node details in REPL mode."""
    if node_id not in G:
        matches = [n for n in G.nodes() if node_id.lower() in n.lower()]
        if not matches:
            json_out({"error": f"Node '{node_id}' not found."})
            return
        node_id = matches[0]

    data = G.nodes[node_id]
    json_out({
        "node_id": node_id,
        "label": data.get("label", node_id),
        "kind": data.get("kind", ""),
        "file_path": data.get("file_path", ""),
        "pagerank": data.get("pagerank", 0),
        "outgoing": len(list(G.out_edges(node_id))),
        "incoming": len(list(G.in_edges(node_id))),
    })


def _build_viz_html(d3_data: dict, *, offline: bool = False) -> str:
    """Build a self-contained HTML file with D3.js force-directed graph."""
    import json

    graph_json = json.dumps(d3_data, default=str)
    kind_groups = d3_data["metadata"]["kind_groups"]
    legend_items = "".join(
        f'<span style="color: hsl('
        f'{i * 360 // max(len(kind_groups), 1)}, 70%, 50%)'
        f'">● {kind}</span>&nbsp;&nbsp;'
        for kind, i in kind_groups.items()
    )

    template_path = Path(__file__).parent / "viz_template.html"
    template = template_path.read_text()

    # Offline mode: replace CDN script tag with inlined D3.js
    if offline:
        d3_path = Path(__file__).parent / "d3.v7.min.js"
        if d3_path.exists():
            d3_source = d3_path.read_text()
            template = template.replace(
                '<script src="https://d3js.org/d3.v7.min.js"></script>',
                f"<script>{d3_source}</script>",
            )

    html = template.replace(
        "/* GRAPH_DATA_PLACEHOLDER */ {}", graph_json,
    ).replace(
        "<!-- LEGEND_PLACEHOLDER -->", legend_items,
    )
    return html



@cli.command(name="node")
@click.argument("node_id")
@click.option("--db", type=click.Path(), default=None)
@click.option("--source-dir", type=click.Path(), default=".")
@click.pass_context
def show_node(ctx, node_id: str, db: str | None, source_dir: str):
    """Show details of a specific node."""
    from hedwig_cg.storage.store import KnowledgeStore

    db_path = resolve_db(db, source_dir)
    if not db_path:
        json_error("No knowledge base found.")

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    if node_id not in G:
        # Try fuzzy match
        matches = [n for n in G.nodes() if node_id.lower() in n.lower()]
        if not matches:
            json_error(f"Node '{node_id}' not found.")
        node_id = matches[0]

    data = G.nodes[node_id]

    json_out({
        "node_id": node_id,
        "label": data.get("label", node_id),
        "kind": data.get("kind", ""),
        "file_path": data.get("file_path", ""),
        "start_line": data.get("start_line"),
        "pagerank": data.get("pagerank", 0),
        "signature": data.get("signature"),
        "outgoing": [
            {
                "target": target,
                "target_label": G.nodes[target].get("label", target) if target in G else target,
                "relation": edata.get("relation", ""),
                "confidence": edata.get("confidence", ""),
            }
            for _, target, edata in G.out_edges(node_id, data=True)
        ],
        "incoming": [
            {
                "source": source,
                "source_label": G.nodes[source].get("label", source) if source in G else source,
                "relation": edata.get("relation", ""),
                "confidence": edata.get("confidence", ""),
            }
            for source, _, edata in G.in_edges(node_id, data=True)
        ],
    })
    store.close()


register_integration_commands(cli)



@cli.command()
def doctor():
    """Check hedwig-cg installation health and code graph integrity.

    Verifies dependencies, model availability, database integrity,
    and graph quality metrics. Useful for troubleshooting issues.
    """
    import importlib
    import sqlite3
    import sys

    counts = {"ok": 0, "fail": 0, "warn": 0}

    def ok(section: str, msg: str):
        counts["ok"] += 1
        human_ok(f"[{section}] {msg}")

    def fail(section: str, msg: str):
        counts["fail"] += 1
        human_fail(f"[{section}] {msg}")

    def warn(section: str, msg: str):
        counts["warn"] += 1
        human_warn(f"[{section}] {msg}")

    click.echo("hedwig-cg doctor\n")

    # 1. Python version
    v = sys.version_info
    if v >= (3, 10):
        ok("python", f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        fail("python", f"Python {v.major}.{v.minor}.{v.micro} (requires >= 3.10)")

    # 2. Core dependencies
    deps = [
        ("networkx", "networkx"),
        ("sentence_transformers", "sentence-transformers"),
        ("faiss", "faiss-cpu"),
        ("leidenalg", "leidenalg"),
        ("igraph", "igraph"),
        ("click", "click"),
        ("rich", "rich"),
    ]
    for mod_name, pip_name in deps:
        try:
            mod = importlib.import_module(mod_name)
            ver = getattr(mod, "__version__", "installed")
            ok("dependencies", f"{pip_name} ({ver})")
        except ImportError:
            fail("dependencies", f"{pip_name} — not installed (pip install {pip_name})")

    # 3. Tree-sitter parsers
    ts_langs = [
        ("tree_sitter", "tree-sitter"),
        ("tree_sitter_python", "tree-sitter-python"),
        ("tree_sitter_javascript", "tree-sitter-javascript"),
    ]
    for mod_name, pip_name in ts_langs:
        try:
            importlib.import_module(mod_name)
            ok("tree_sitter", pip_name)
        except ImportError:
            warn("tree_sitter", f"{pip_name} — not installed (optional, enables AST extraction)")

    # 4. MCP server dependency
    try:
        importlib.import_module("mcp")
        ok("mcp", "mcp (Model Context Protocol server available)")
    except ImportError:
        warn("mcp", "mcp — not installed (optional, install with: pip install mcp)")

    # 5. Embedding models
    model_cache = Path.home() / ".hedwig-cg" / "models"
    if model_cache.exists():
        cached_models = [d.name for d in model_cache.iterdir() if d.is_dir()]
        if cached_models:
            for m in cached_models:
                ok("models", f"Cached: {m}")
        else:
            warn("models", "Model cache exists but empty — models will download on first build")
    else:
        warn("models",
             "No model cache at ~/.hedwig-cg/models/ — models will download on first build")

    # 6. Code graph database
    cwd = Path.cwd()
    db_path = cwd / ".hedwig-cg" / "knowledge.db"
    if db_path.exists():
        ok("database", f"Database found: {db_path}")
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity == "ok":
                ok("database", "Database integrity: OK")
            else:
                fail("database", f"Database integrity: {integrity}")

            try:
                n_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
                n_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
                ok("database", f"Nodes: {n_nodes}, Edges: {n_edges}")
                if n_nodes == 0:
                    warn("database", "Graph is empty — run 'hedwig-cg build .' to populate")
            except sqlite3.OperationalError:
                fail("database", "Missing nodes/edges tables — database may be corrupted")

            try:
                conn.execute("SELECT COUNT(*) FROM nodes_fts").fetchone()
                ok("database", "FTS5 full-text search index: present")
            except sqlite3.OperationalError:
                warn("database", "FTS5 index missing — keyword search may not work")

            try:
                n_comm = conn.execute("SELECT COUNT(*) FROM communities").fetchone()[0]
                ok("database", f"Communities: {n_comm}")
            except sqlite3.OperationalError:
                warn("database", "Communities table missing — run build to generate")

            faiss_path = cwd / ".hedwig-cg" / "faiss_code.index"
            faiss_text_path = cwd / ".hedwig-cg" / "faiss_text.index"
            if faiss_path.exists() and faiss_text_path.exists():
                code_size = faiss_path.stat().st_size / 1024
                text_size = faiss_text_path.stat().st_size / 1024
                ok("database", f"FAISS code index: {code_size:.1f} KB")
                ok("database", f"FAISS text index: {text_size:.1f} KB")
            elif faiss_path.exists() or faiss_text_path.exists():
                warn("database", "Only one FAISS index found — dual-model search may be degraded")
            else:
                warn("database", "No FAISS indexes — run 'hedwig-cg build .' to generate embeddings")

            conn.close()
        except sqlite3.DatabaseError as e:
            fail("database", f"Cannot open database: {e}")
    else:
        warn("database", f"No database at {db_path} — run 'hedwig-cg build .' to create")

    total = counts["ok"] + counts["fail"] + counts["warn"]
    click.echo(
        f"\n{counts['ok']} passed, {counts['fail']} failed, "
        f"{counts['warn']} warnings (total {total})"
    )


@cli.command()
def mcp():
    """Start the hedwig-cg MCP server (stdio transport).

    Exposes code graph tools to AI agents via the Model Context Protocol.
    Tools: search, node, stats, communities, build.

    Configure in Claude Code:

        claude mcp add hedwig-cg -- hedwig-cg mcp

    Or in .cursor/mcp.json / .vscode/mcp.json:

        { "mcpServers": { "hedwig-cg": { "command": "hedwig-cg", "args": ["mcp"] } } }
    """
    from hedwig_cg.mcp_server import main as mcp_main
    mcp_main()


if __name__ == "__main__":
    cli()
