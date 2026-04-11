"""CLI interface for hedwig-kg.

Usage:
    hedwig-kg build <source_dir> [--output <dir>] [--no-embed] [--model <name>]
    hedwig-kg search <query> [--db <path>] [--top-k <n>]
    hedwig-kg stats [--db <path>]
    hedwig-kg export [--db <path>] [--format json|graphml]
"""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


def _suppress_library_logs():
    """Suppress noisy library logs for JSON output mode."""
    import logging
    import os
    import warnings

    warnings.filterwarnings("ignore")
    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    # Disable tqdm progress bars (used by sentence-transformers "Loading weights")
    os.environ["TQDM_DISABLE"] = "1"
    for name in [
        "sentence_transformers", "transformers", "torch", "huggingface_hub",
        "filelock", "urllib3", "tqdm", "fsspec",
    ]:
        logging.getLogger(name).setLevel(logging.CRITICAL)


def _json_out(data) -> None:
    """Print JSON to stdout (no Rich formatting)."""
    import json
    click.echo(json.dumps(data, indent=2, default=str))


def _json_error(message: str) -> None:
    """Print error as JSON and exit with code 1."""
    import json
    click.echo(json.dumps({"error": message}))
    raise SystemExit(1)


@click.group()
@click.version_option(version=None, prog_name="hedwig-kg", package_name="hedwig-kg")
@click.option("--json", "json_output", is_flag=True, default=False,
              help="Output as JSON (for AI agent consumption). Suppresses all non-JSON output.")
@click.pass_context
def cli(ctx, json_output: bool):
    """hedwig-kg: Local-first knowledge graph with hybrid search."""
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_output
    if json_output:
        _suppress_library_logs()


@cli.command()
@click.argument("source_dir", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output directory for the database")
@click.option("--no-embed", is_flag=True, help="Skip embedding generation")
@click.option("--model", default=None,
              help="Override embedding model (default: dual-model, code=bge-small + text=MiniLM)")
@click.option("--max-file-size", default=1_000_000, type=int, help="Max file size in bytes")
@click.option("--incremental", is_flag=True, help="Skip unchanged files (faster rebuilds)")
@click.option(
    "--lang", default="auto",
    type=click.Choice(["auto", "en", "multilingual"], case_sensitive=False),
    help="Language mode: auto (detect), en (English models), multilingual (100+ languages)",
)
@click.pass_context
def build(
    ctx, source_dir: str, output: str | None, no_embed: bool,
    model: str, max_file_size: int, incremental: bool, lang: str,
):
    """Build knowledge graph from a source directory."""
    from hedwig_kg.core.pipeline import run_pipeline

    json_mode = ctx.obj.get("json", False) if ctx.obj else False

    if json_mode:
        result = run_pipeline(
            source_dir=source_dir,
            output_dir=output,
            embed=not no_embed,
            model_name=model,
            max_file_size=max_file_size,
            on_progress=None,
            incremental=incremental,
            lang=lang,
        )
    else:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Starting...", total=None)

            def on_progress(stage: str, detail: str):
                progress.update(task, description=f"[cyan]{stage}[/]: {detail}")

            result = run_pipeline(
                source_dir=source_dir,
                output_dir=output,
                embed=not no_embed,
                model_name=model,
                max_file_size=max_file_size,
                on_progress=on_progress,
                incremental=incremental,
                lang=lang,
            )

    if json_mode:
        _json_out({
            "files_detected": len(result.detect_result.files) if result.detect_result else 0,
            "files_skipped": len(result.detect_result.skipped) if result.detect_result else 0,
            "nodes": result.graph.number_of_nodes() if result.graph else 0,
            "edges": result.graph.number_of_edges() if result.graph else 0,
            "communities": len(result.cluster_result.communities) if result.cluster_result else 0,
            "embeddings": result.embeddings_count,
            "database": result.db_path,
            "stage_timings": result.stage_timings or {},
        })
        return

    # Summary (Rich mode)
    console.print()
    table = Table(title="Build Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    if result.detect_result:
        table.add_row("Files detected", str(len(result.detect_result.files)))
        table.add_row("Files skipped", str(len(result.detect_result.skipped)))
    if result.graph:
        table.add_row("Nodes", str(result.graph.number_of_nodes()))
        table.add_row("Edges", str(result.graph.number_of_edges()))
    if result.cluster_result:
        table.add_row("Communities", str(len(result.cluster_result.communities)))
    table.add_row("Embeddings", str(result.embeddings_count))
    table.add_row("Database", result.db_path)

    console.print(table)

    # Show per-stage timing breakdown
    if result.stage_timings:
        timing_table = Table(title="Stage Timings")
        timing_table.add_column("Stage", style="bold")
        timing_table.add_column("Time", justify="right")
        for stage, secs in result.stage_timings.items():
            if stage == "total":
                timing_table.add_row(f"[bold]{stage}[/bold]", f"[bold]{secs:.1f}s[/bold]")
            else:
                timing_table.add_row(stage, f"{secs:.1f}s")
        console.print(timing_table)


@cli.command()
@click.argument("query")
@click.option("--db", type=click.Path(), default=None, help="Path to knowledge.db")
@click.option("--top-k", default=15, type=int, help="Number of results")
@click.option("--source-dir", type=click.Path(), default=".",
              help="Source dir (to find default DB)")
@click.option("--fast", is_flag=True, default=False,
              help="Fast mode: text model only (lower latency, slightly reduced accuracy)")
@click.pass_context
def search(ctx, query: str, db: str | None, top_k: int, source_dir: str, fast: bool):
    """Search the knowledge graph with hybrid vector + graph + keyword search."""
    from hedwig_kg.query.hybrid import hybrid_search
    from hedwig_kg.storage.store import KnowledgeStore

    json_mode = ctx.obj.get("json", False) if ctx.obj else False

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        if json_mode:
            _json_error("No knowledge base found. Run 'hedwig-kg build' first.")
        console.print("[red]No knowledge base found. Run 'hedwig-kg build' first.[/]")
        raise SystemExit(1)

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    if G.number_of_nodes() == 0:
        if json_mode:
            _json_out([])
            store.close()
            return
        console.print("[yellow]Knowledge base is empty.[/]")
        store.close()
        return

    # Build vector index
    try:
        store.build_vector_index()
    except Exception:
        if not json_mode:
            console.print("[dim]Vector index not available, keyword search only.[/]")

    # Read text model from DB metadata (set during build)
    text_model = store.get_meta("text_model", None)
    results = hybrid_search(
        query, store, G, top_k=top_k, fast=fast, text_model=text_model,
    )

    if json_mode:
        _json_out([
            {
                "node_id": r.node_id,
                "label": r.label,
                "kind": r.kind,
                "file_path": r.file_path,
                "start_line": r.start_line,
                "end_line": getattr(r, "end_line", None),
                "score": r.score,
                "snippet": getattr(r, "snippet", None),
                "signal_contributions": r.signal_contributions,
                "neighbors": r.neighbors,
            }
            for r in results
        ])
        store.close()
        return

    _print_search_results(query, results)
    store.close()


def _file_loc(r) -> str:
    """Format file:line for search result display."""
    name = str(Path(r.file_path).name)
    if r.start_line:
        return f"{name}:{r.start_line}"
    return name


def _print_search_results(query: str, results: list) -> None:
    """Print search results as a Rich table."""
    if not results:
        console.print("[yellow]No results found.[/]")
        return

    table = Table(title=f"Search: '{query}'")
    table.add_column("#", style="dim", width=3)
    table.add_column("Label", style="bold")
    table.add_column("Kind")
    table.add_column("File")
    table.add_column("Score", justify="right")
    table.add_column("Signals", style="dim")
    table.add_column("Neighbors", style="dim")

    for i, r in enumerate(results, 1):
        # Format signal contributions as compact abbreviations
        sig_parts = []
        abbrev = {"code_vector": "cv", "text_vector": "tv", "graph": "g",
                  "keyword": "kw", "community": "cm"}
        for sname, sval in sorted(r.signal_contributions.items(), key=lambda x: -x[1]):
            if sval > 0:
                sig_parts.append(f"{abbrev.get(sname, sname[:2])}:{sval:.3f}")
        table.add_row(
            str(i),
            r.label,
            r.kind,
            _file_loc(r) if r.file_path else "",
            f"{r.score:.4f}",
            " ".join(sig_parts[:3]),
            ", ".join(r.neighbors[:3]),
        )

    console.print(table)


@cli.command()
@click.option("--db", type=click.Path(), default=None, help="Path to knowledge.db")
@click.option("--source-dir", type=click.Path(), default=".", help="Source dir")
@click.pass_context
def stats(ctx, db: str | None, source_dir: str):
    """Show knowledge graph statistics."""
    from hedwig_kg.storage.store import KnowledgeStore

    json_mode = ctx.obj.get("json", False) if ctx.obj else False

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        if json_mode:
            _json_error("No knowledge base found. Run 'hedwig-kg build' first.")
        console.print("[red]No knowledge base found. Run 'hedwig-kg build' first.[/]")
        raise SystemExit(1)

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

    if json_mode:
        _json_out({
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
        return

    table = Table(title="Knowledge Base Statistics")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Nodes", str(G.number_of_nodes()))
    table.add_row("Edges", str(G.number_of_edges()))

    for k, v in sorted(kinds.items(), key=lambda x: -x[1]):
        table.add_row(f"  {k}", str(v))

    for c, v in sorted(conf.items()):
        table.add_row(f"  {c} edges", str(v))

    if density is not None:
        table.add_row("Density", f"{density:.4f}")
    if components is not None:
        table.add_row("Connected components", str(components))
    if avg_clustering is not None:
        table.add_row("Avg clustering coeff", f"{avg_clustering:.4f}")

    table.add_row("Communities", str(comm_count))
    table.add_row("Embeddings", str(emb_count))
    table.add_row("Database", str(db_path))
    table.add_row("Source", store.get_meta("source_dir", "unknown"))

    console.print(table)
    store.close()


@cli.command()
@click.option("--db", type=click.Path(), default=None)
@click.option("--source-dir", type=click.Path(), default=".", help="Source dir")
@click.option("--level", type=int, default=None, help="Filter by hierarchy level")
@click.option("--search", "query", type=str, default=None, help="Search community summaries")
@click.pass_context
def communities(ctx, db: str | None, source_dir: str, level: int | None, query: str | None):
    """List and search communities in the knowledge graph."""
    from hedwig_kg.storage.store import KnowledgeStore

    json_mode = ctx.obj.get("json", False) if ctx.obj else False

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        if json_mode:
            _json_error("No knowledge base found. Run 'hedwig-kg build' first.")
        console.print("[red]No knowledge base found. Run 'hedwig-kg build' first.[/]")
        raise SystemExit(1)

    store = KnowledgeStore(db_path)

    if query:
        terms = [t.lower() for t in query.split() if len(t) > 2]
        results = store.community_search(terms, top_k=10)
        if json_mode:
            _json_out([
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
        if not results:
            console.print("[yellow]No matching communities found.[/]")
            store.close()
            return
        table = Table(title=f"Communities matching '{query}'")
        table.add_column("ID", justify="right")
        table.add_column("Level", justify="right")
        table.add_column("Nodes", justify="right")
        table.add_column("Score", justify="right")
        table.add_column("Summary", max_width=60)
        for r in results:
            table.add_row(
                str(r["community_id"]),
                str(r["level"]),
                str(len(r["node_ids"])),
                f"{r['score']:.1f}",
                (r["summary"] or "")[:60],
            )
        console.print(table)
    else:
        sql = "SELECT id, level, resolution, summary FROM communities"
        params: list = []
        if level is not None:
            sql += " WHERE level = ?"
            params.append(level)
        sql += " ORDER BY level, id"
        rows = store.conn.execute(sql, params).fetchall()

        if json_mode:
            _json_out([
                {
                    "id": row["id"],
                    "level": row["level"],
                    "resolution": row["resolution"],
                    "summary": row["summary"],
                }
                for row in rows
            ])
            store.close()
            return

        if not rows:
            console.print("[yellow]No communities found.[/]")
            store.close()
            return

        table = Table(title="Communities")
        table.add_column("ID", justify="right")
        table.add_column("Level", justify="right")
        table.add_column("Resolution", justify="right")
        table.add_column("Summary", max_width=70)
        for row in rows:
            table.add_row(
                str(row["id"]),
                str(row["level"]),
                f"{row['resolution']:.2f}",
                (row["summary"] or "")[:70],
            )
        console.print(table)

    store.close()


@cli.command()
@click.option("--db", type=click.Path(), default=None)
@click.option("--source-dir", type=click.Path(), default=".")
@click.option("--format", "fmt", type=click.Choice(["json", "graphml", "d3"]), default="json")
@click.option("--output", "-o", type=click.Path(), default=None)
def export(db: str | None, source_dir: str, fmt: str, output: str | None):
    """Export the knowledge graph."""
    import json

    import networkx as nx

    from hedwig_kg.storage.store import KnowledgeStore

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        console.print("[red]No knowledge base found.[/]")
        raise SystemExit(1)

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    if fmt == "d3":
        data = _graph_to_d3(G)
        out = output or "knowledge_graph_d3.json"
        Path(out).write_text(json.dumps(data, indent=2, default=str))
    elif fmt == "json":
        data = nx.node_link_data(G)
        out = output or "knowledge_graph.json"
        Path(out).write_text(json.dumps(data, indent=2, default=str))
    elif fmt == "graphml":
        # GraphML doesn't support list attributes, convert them
        G2 = G.copy()
        for n in G2.nodes():
            for k, v in list(G2.nodes[n].items()):
                if isinstance(v, (list, dict)):
                    G2.nodes[n][k] = str(v)
        out = output or "knowledge_graph.graphml"
        nx.write_graphml(G2, out)

    console.print(f"[green]Exported to {out}[/]")
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
    """Generate an interactive HTML visualization of the knowledge graph."""
    from hedwig_kg.storage.store import KnowledgeStore

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        console.print("[red]No knowledge base found. Run 'hedwig-kg build' first.[/]")
        raise SystemExit(1)

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    # Trim to top N nodes by PageRank for browser performance
    if G.number_of_nodes() > max_nodes:
        ranked = sorted(G.nodes(data=True), key=lambda x: x[1].get("pagerank", 0), reverse=True)
        keep = {n for n, _ in ranked[:max_nodes]}
        G = G.subgraph(keep).copy()

    d3_data = _graph_to_d3(G)
    html = _build_viz_html(d3_data, offline=offline)

    out = output or "knowledge_graph.html"
    Path(out).write_text(html)

    console.print(f"[green]Visualization saved to {out}[/]")
    console.print(f"  Nodes: {d3_data['metadata']['node_count']}, "
                  f"Links: {d3_data['metadata']['link_count']}")
    if offline:
        console.print("  [dim]Offline mode: D3.js inlined (~280KB)[/]")
    console.print(f"  Open in browser: file://{Path(out).resolve()}")
    store.close()


@cli.command()
@click.option("--source-dir", type=click.Path(), default=".",
              help="Source directory whose .hedwig-kg/ to remove")
@click.option("--db", type=click.Path(), default=None,
              help="Specific database file to remove")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def clean(source_dir: str, db: str | None, yes: bool):
    """Remove the knowledge base database and associated data."""
    import shutil

    if db:
        target = Path(db)
        if not target.exists():
            console.print("[yellow]Database not found.[/]")
            return
        if not yes:
            click.confirm(f"Delete {target}?", abort=True)
        target.unlink()
        console.print(f"[green]Removed {target}[/]")
    else:
        kb_dir = Path(source_dir).resolve() / ".hedwig-kg"
        if not kb_dir.exists():
            console.print("[yellow]No .hedwig-kg/ directory found.[/]")
            return
        if not yes:
            click.confirm(f"Delete {kb_dir}/?", abort=True)
        shutil.rmtree(kb_dir)
        console.print(f"[green]Removed {kb_dir}/[/]")


@cli.command()
@click.option("--db", type=click.Path(), default=None, help="Path to knowledge.db")
@click.option("--source-dir", type=click.Path(), default=".", help="Source dir")
@click.option("--top-k", default=15, type=int, help="Number of results per query")
def query(db: str | None, source_dir: str, top_k: int):
    """Interactive search REPL for exploring the knowledge graph.

    Launches an interactive session where you can run multiple searches
    without reloading the graph. Type 'quit' or 'exit' to leave.

    Special commands:
      :node <id>   - Show node details
      :stats       - Show graph statistics
      :quit        - Exit the REPL
    """
    from hedwig_kg.query.hybrid import hybrid_search
    from hedwig_kg.storage.store import KnowledgeStore

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        console.print("[red]No knowledge base found. Run 'hedwig-kg build' first.[/]")
        raise SystemExit(1)

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    if G.number_of_nodes() == 0:
        console.print("[yellow]Knowledge base is empty.[/]")
        store.close()
        return

    try:
        store.build_vector_index()
    except Exception:
        console.print("[dim]Vector index not available, keyword search only.[/]")

    # Preload embedding models in background thread so first search is fast
    import threading
    def _preload_models():
        try:
            from hedwig_kg.query.embeddings import CODE_MODEL, TEXT_MODEL, _get_model
            _get_model(CODE_MODEL)
            _get_model(TEXT_MODEL)
        except Exception:
            pass
    threading.Thread(target=_preload_models, daemon=True).start()

    console.print(f"[bold green]hedwig-kg query REPL[/] — "
                  f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    console.print("[dim]Type a query to search. :quit to exit. :node <id> for details.[/]")
    console.print("[dim]Models loading in background...[/]\n")

    while True:
        try:
            user_input = click.prompt("hedwig-kg", prompt_suffix="> ")
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
            console.print(f"  Nodes: {G.number_of_nodes()}, "
                          f"Edges: {G.number_of_edges()}")
        else:
            results = hybrid_search(user_input, store, G, top_k=top_k)
            _print_search_results(user_input, results)

    store.close()
    console.print("[dim]Session ended.[/]")


def _repl_show_node(G, node_id: str) -> None:
    """Show node details in REPL mode."""
    if node_id not in G:
        matches = [n for n in G.nodes() if node_id.lower() in n.lower()]
        if not matches:
            console.print(f"[red]Node '{node_id}' not found.[/]")
            return
        node_id = matches[0]

    data = G.nodes[node_id]
    console.print(f"  [bold]{data.get('label', node_id)}[/] ({data.get('kind', '')})")
    console.print(f"  File: {data.get('file_path', '')}")
    console.print(f"  PageRank: {data.get('pagerank', 0):.6f}")
    out_count = len(list(G.out_edges(node_id)))
    in_count = len(list(G.in_edges(node_id)))
    console.print(f"  Edges: {out_count} outgoing, {in_count} incoming")


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


def _resolve_db(db: str | None, source_dir: str) -> Path | None:
    """Find the knowledge database."""
    if db:
        p = Path(db)
        return p if p.exists() else None

    # Default location
    default = Path(source_dir).resolve() / ".hedwig-kg" / "knowledge.db"
    if default.exists():
        return default

    return None


@cli.command(name="node")
@click.argument("node_id")
@click.option("--db", type=click.Path(), default=None)
@click.option("--source-dir", type=click.Path(), default=".")
@click.pass_context
def show_node(ctx, node_id: str, db: str | None, source_dir: str):
    """Show details of a specific node."""
    from hedwig_kg.storage.store import KnowledgeStore

    json_mode = ctx.obj.get("json", False) if ctx.obj else False

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        if json_mode:
            _json_error("No knowledge base found.")
        console.print("[red]No knowledge base found.[/]")
        raise SystemExit(1)

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    if node_id not in G:
        # Try fuzzy match
        matches = [n for n in G.nodes() if node_id.lower() in n.lower()]
        if not matches:
            if json_mode:
                _json_error(f"Node '{node_id}' not found.")
            console.print(f"[red]Node '{node_id}' not found.[/]")
            store.close()
            return
        node_id = matches[0]
        if len(matches) > 1 and not json_mode:
            console.print(f"[yellow]Multiple matches, showing: {node_id}[/]")

    data = G.nodes[node_id]

    if json_mode:
        _json_out({
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
        return

    console.print(f"\n[bold]{data.get('label', node_id)}[/] ({data.get('kind', '')})")
    console.print(f"  File: {data.get('file_path', '')}")
    console.print(f"  Line: {data.get('start_line', '')}")
    console.print(f"  PageRank: {data.get('pagerank', 0):.6f}")

    if data.get("signature"):
        console.print(f"  Signature: {data['signature']}")

    # Show edges
    console.print("\n[bold]Outgoing:[/]")
    for _, target, edata in G.out_edges(node_id, data=True):
        t_label = G.nodes[target].get("label", target) if target in G else target
        rel = edata.get('relation', '')
        conf = edata.get('confidence', '')
        console.print(f"  → {t_label} [{rel}] ({conf})")

    console.print("\n[bold]Incoming:[/]")
    for source, _, edata in G.in_edges(node_id, data=True):
        s_label = G.nodes[source].get("label", source) if source in G else source
        rel = edata.get('relation', '')
        conf = edata.get('confidence', '')
        console.print(f"  ← {s_label} [{rel}] ({conf})")

    store.close()


def _auto_rebuild_command() -> str:
    """Return the shell command for auto-rebuild on session stop."""
    script = Path(__file__).parent.parent / "scripts" / "auto_rebuild.sh"
    return f"sh {script}"


@cli.group(name="claude")
def claude_group():
    """Manage Claude Code integration (skill + CLAUDE.md + hooks)."""
    pass


@claude_group.command(name="install")
@click.option(
    "--scope",
    type=click.Choice(["user", "project"], case_sensitive=False),
    default=None,
    help="Install scope: 'user' (global ~/.claude/skills/) or 'project' (.claude/skills/). "
         "If omitted, you will be prompted to choose.",
)
def claude_install(scope: str | None):
    """Install Claude Code integration.

    Priority: 1) Skill  2) CLAUDE.md + hooks  3) MCP
    """
    import json
    import shutil

    project_root = Path.cwd()

    # --- Prompt for scope if not provided ---
    if scope is None:
        console.print("[bold]Select installation scope:[/]")
        console.print(
            "  [cyan]1)[/] user    — Global (~/.claude/skills/)."
            " Available in ALL projects."
        )
        console.print(
            "  [cyan]2)[/] project — Local (.claude/skills/)."
            " Available only in THIS project."
        )
        choice = click.prompt(
            "Choose scope",
            type=click.Choice(["1", "2", "user", "project"]),
            default="1",
        )
        scope = "user" if choice in ("1", "user") else "project"

    # --- Priority 1: Install Skill ---
    skill_source = Path(__file__).parent.parent / "skill.md"
    if scope == "user":
        skill_dir = Path.home() / ".claude" / "skills" / "hedwig-kg"
    else:
        skill_dir = project_root / ".claude" / "skills" / "hedwig-kg"

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dest = skill_dir / "SKILL.md"

    if skill_source.exists():
        shutil.copy2(skill_source, skill_dest)
        scope_label = (
            "~/.claude/skills/hedwig-kg/"
            if scope == "user"
            else ".claude/skills/hedwig-kg/"
        )
        console.print(
            f"[green]✓ Skill installed[/] → "
            f"{scope_label}SKILL.md ({scope} scope)"
        )
    else:
        console.print("[yellow]⚠ Skill source not found, skipping skill registration.[/]")

    # --- Priority 2: CLAUDE.md + hooks ---
    # 1. Write section to project CLAUDE.md
    claude_md = project_root / "CLAUDE.md"
    marker = "## hedwig-kg"
    section = (
        "\n## hedwig-kg\n\n"
        "This project has a hedwig-kg knowledge graph at `.hedwig-kg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-kg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files with Glob/Grep, run `hedwig-kg search` first. "
        "Only fall back to Grep if the knowledge graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-kg build . --incremental` to keep the graph current\n"
        "- Use `hedwig-kg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-kg stats` for structural overview "
        "(god nodes, communities, density)\n"
    )

    if claude_md.exists():
        content = claude_md.read_text()
        if marker in content:
            console.print("[dim]CLAUDE.md already has hedwig-kg section.[/]")
        else:
            claude_md.write_text(content + section)
            console.print("[green]Added hedwig-kg section to CLAUDE.md[/]")
    else:
        claude_md.write_text(section.lstrip("\n"))
        console.print("[green]Created CLAUDE.md with hedwig-kg section[/]")

    # 2. Write PreToolUse hook to .claude/settings.json
    settings_dir = project_root / ".claude"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_file = settings_dir / "settings.json"

    hook_entry = {
        "matcher": "Glob|Grep",
        "hooks": [{
            "type": "command",
            "command": (
                '[ -f .hedwig-kg/knowledge.db ] && echo '
                '\'{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
                '"additionalContext":"hedwig-kg: Knowledge graph available. '
                "Use `hedwig-kg search \\\"<query>\\\"` (5-signal HybridRAG) "
                "instead of grepping raw files. This single command covers "
                "vector, graph, keyword, and community search with RRF fusion."
                '"}}\' || true'
            ),
        }],
    }

    if settings_file.exists():
        settings = json.loads(settings_file.read_text())
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})
    pre_hooks = hooks.setdefault("PreToolUse", [])

    # Check if already installed
    already = any(
        "hedwig-kg" in json.dumps(h)
        for h in pre_hooks
    )
    if already:
        console.print("[dim].claude/settings.json already has hedwig-kg PreToolUse hook.[/]")
    else:
        pre_hooks.append(hook_entry)
        console.print("[green]Added PreToolUse hook to .claude/settings.json[/]")

    # 3. Write Stop hook for auto-rebuild
    stop_hook_entry = {
        "matcher": "*",
        "hooks": [{
            "type": "command",
            "command": _auto_rebuild_command(),
            "timeout": 10,
        }],
    }
    stop_hooks = hooks.setdefault("Stop", [])
    stop_already = any("hedwig-kg" in json.dumps(h) or "auto_rebuild" in json.dumps(h)
                       for h in stop_hooks)
    if stop_already:
        console.print("[dim].claude/settings.json already has hedwig-kg Stop hook.[/]")
    else:
        stop_hooks.append(stop_hook_entry)
        console.print("[green]Added Stop hook for auto-rebuild to .claude/settings.json[/]")

    settings_file.write_text(json.dumps(settings, indent=2) + "\n")

    console.print()
    console.print("[bold]Done![/] Claude Code will now use the knowledge graph "
                  "when searching this project.")
    console.print("[dim]Graph auto-rebuilds when your session ends.[/]")
    console.print("[dim]Run 'hedwig-kg claude uninstall' to remove.[/]")


@claude_group.command(name="uninstall")
@click.option(
    "--scope",
    type=click.Choice(["user", "project", "all"], case_sensitive=False),
    default="all",
    help="Uninstall scope: 'user', 'project', or 'all' (default).",
)
def claude_uninstall(scope: str):
    """Remove Claude Code integration (skill + CLAUDE.md + hooks)."""
    import json
    import shutil

    project_root = Path.cwd()

    # 0. Remove skill
    removed_skill = False
    if scope in ("user", "all"):
        user_skill = Path.home() / ".claude" / "skills" / "hedwig-kg"
        if user_skill.exists():
            shutil.rmtree(user_skill)
            console.print("[green]Removed user-scope skill (~/.claude/skills/hedwig-kg/)[/]")
            removed_skill = True
    if scope in ("project", "all"):
        proj_skill = project_root / ".claude" / "skills" / "hedwig-kg"
        if proj_skill.exists():
            shutil.rmtree(proj_skill)
            console.print("[green]Removed project-scope skill (.claude/skills/hedwig-kg/)[/]")
            removed_skill = True
    if not removed_skill:
        console.print("[dim]No skill found to remove.[/]")

    # 1. Remove section from CLAUDE.md
    claude_md = project_root / "CLAUDE.md"
    if claude_md.exists():
        lines = claude_md.read_text().splitlines(keepends=True)
        filtered = []
        skip = False
        for line in lines:
            if line.strip() == "## hedwig-kg":
                skip = True
                continue
            if skip and line.startswith("##") and "hedwig-kg" not in line.lower():
                skip = False
            if skip:
                continue
            filtered.append(line)
        new_content = "".join(filtered).rstrip("\n") + "\n"
        claude_md.write_text(new_content)
        console.print("[green]Removed hedwig-kg section from CLAUDE.md[/]")

    # 2. Remove hooks from .claude/settings.json
    settings_file = project_root / ".claude" / "settings.json"
    if settings_file.exists():
        settings = json.loads(settings_file.read_text())
        hooks = settings.get("hooks", {})
        for event in ("PreToolUse", "Stop"):
            event_hooks = hooks.get(event, [])
            hooks[event] = [
                h for h in event_hooks
                if "hedwig-kg" not in json.dumps(h)
                and "auto_rebuild" not in json.dumps(h)
            ]
            if not hooks[event]:
                hooks.pop(event, None)
        if not hooks:
            settings.pop("hooks", None)
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")
        console.print("[green]Removed hedwig-kg hooks from .claude/settings.json[/]")

    console.print("[dim]hedwig-kg Claude Code integration removed.[/]")


cli.add_command(claude_group)


# --- Codex CLI integration ---

@cli.group(name="codex")
def codex_group():
    """Manage per-project OpenAI Codex CLI integration."""
    pass


@codex_group.command(name="install")
def codex_install():
    """Install per-project Codex CLI integration (AGENTS.md + hooks.json)."""
    import json

    project_root = Path.cwd()

    # 1. Write section to project AGENTS.md
    agents_md = project_root / "AGENTS.md"
    marker = "## hedwig-kg"
    section = (
        "\n## hedwig-kg\n\n"
        "This project has a hedwig-kg knowledge graph at `.hedwig-kg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-kg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files, run `hedwig-kg search` first. "
        "Only fall back to grep if the knowledge graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-kg build . --incremental` to keep the graph current\n"
        "- Use `hedwig-kg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-kg stats` for structural overview "
        "(god nodes, communities, density)\n"
    )

    if agents_md.exists():
        content = agents_md.read_text()
        if marker in content:
            console.print("[dim]AGENTS.md already has hedwig-kg section.[/]")
        else:
            agents_md.write_text(content + section)
            console.print("[green]Added hedwig-kg section to AGENTS.md[/]")
    else:
        agents_md.write_text(section.lstrip("\n"))
        console.print("[green]Created AGENTS.md with hedwig-kg section[/]")

    # 2. Write PreToolUse hook to .codex/hooks.json
    hooks_dir = project_root / ".codex"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hooks_file = hooks_dir / "hooks.json"

    hook_entry = {
        "matcher": "Bash",
        "hooks": [{
            "type": "command",
            "command": (
                '[ -f .hedwig-kg/knowledge.db ] && echo '
                '\'{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
                '"additionalContext":"hedwig-kg: Knowledge graph available. '
                "Use `hedwig-kg search \\\"<query>\\\"` (5-signal HybridRAG) "
                "instead of grepping raw files. This single command covers "
                "vector, graph, keyword, and community search with RRF fusion."
                '"}}\' || true'
            ),
        }],
    }

    if hooks_file.exists():
        hooks_data = json.loads(hooks_file.read_text())
    else:
        hooks_data = {}

    hooks = hooks_data.setdefault("hooks", {})
    pre_hooks = hooks.setdefault("PreToolUse", [])

    already = any("hedwig-kg" in json.dumps(h) for h in pre_hooks)
    if already:
        console.print("[dim].codex/hooks.json already has hedwig-kg PreToolUse hook.[/]")
    else:
        pre_hooks.append(hook_entry)
        console.print("[green]Added PreToolUse hook to .codex/hooks.json[/]")

    # 3. Write Stop hook for auto-rebuild
    stop_hook_entry = {
        "matcher": "*",
        "hooks": [{
            "type": "command",
            "command": _auto_rebuild_command(),
            "timeout": 10,
        }],
    }
    stop_hooks = hooks.setdefault("Stop", [])
    stop_already = any("auto_rebuild" in json.dumps(h) for h in stop_hooks)
    if stop_already:
        console.print("[dim].codex/hooks.json already has hedwig-kg Stop hook.[/]")
    else:
        stop_hooks.append(stop_hook_entry)
        console.print("[green]Added Stop hook for auto-rebuild to .codex/hooks.json[/]")

    hooks_file.write_text(json.dumps(hooks_data, indent=2) + "\n")

    console.print()
    console.print("[bold]Done![/] Codex CLI will now use the knowledge graph "
                  "when working in this project.")
    console.print("[dim]Graph auto-rebuilds when your session ends.[/]")
    console.print("[dim]Run 'hedwig-kg codex uninstall' to remove.[/]")


@codex_group.command(name="uninstall")
def codex_uninstall():
    """Remove per-project Codex CLI integration."""
    import json

    project_root = Path.cwd()

    # 1. Remove section from AGENTS.md
    agents_md = project_root / "AGENTS.md"
    if agents_md.exists():
        lines = agents_md.read_text().splitlines(keepends=True)
        filtered = []
        skip = False
        for line in lines:
            if line.strip() == "## hedwig-kg":
                skip = True
                continue
            if skip and line.startswith("##") and "hedwig-kg" not in line.lower():
                skip = False
            if skip:
                continue
            filtered.append(line)
        new_content = "".join(filtered).rstrip("\n") + "\n"
        agents_md.write_text(new_content)
        console.print("[green]Removed hedwig-kg section from AGENTS.md[/]")

    # 2. Remove hooks from .codex/hooks.json
    hooks_file = project_root / ".codex" / "hooks.json"
    if hooks_file.exists():
        hooks_data = json.loads(hooks_file.read_text())
        hooks = hooks_data.get("hooks", {})
        for event in ("PreToolUse", "Stop"):
            event_hooks = hooks.get(event, [])
            hooks[event] = [
                h for h in event_hooks
                if "hedwig-kg" not in json.dumps(h)
                and "auto_rebuild" not in json.dumps(h)
            ]
            if not hooks[event]:
                hooks.pop(event, None)
        if not hooks:
            hooks_data.pop("hooks", None)
        hooks_file.write_text(json.dumps(hooks_data, indent=2) + "\n")
        console.print("[green]Removed hedwig-kg hooks from .codex/hooks.json[/]")

    console.print("[dim]hedwig-kg Codex CLI integration removed.[/]")


cli.add_command(codex_group)


# --- Gemini CLI integration ---

@cli.group(name="gemini")
def gemini_group():
    """Manage per-project Google Gemini CLI integration."""
    pass


@gemini_group.command(name="install")
def gemini_install():
    """Install per-project Gemini CLI integration (GEMINI.md + BeforeTool hook)."""
    import json

    project_root = Path.cwd()

    # 1. Write section to project GEMINI.md
    gemini_md = project_root / "GEMINI.md"
    marker = "## hedwig-kg"
    section = (
        "\n## hedwig-kg\n\n"
        "This project has a hedwig-kg knowledge graph at `.hedwig-kg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-kg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before reading raw files, run `hedwig-kg search` first. "
        "Only fall back to file reads if the knowledge graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-kg build . --incremental` to keep the graph current\n"
        "- Use `hedwig-kg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-kg stats` for structural overview "
        "(god nodes, communities, density)\n"
    )

    if gemini_md.exists():
        content = gemini_md.read_text()
        if marker in content:
            console.print("[dim]GEMINI.md already has hedwig-kg section.[/]")
        else:
            gemini_md.write_text(content + section)
            console.print("[green]Added hedwig-kg section to GEMINI.md[/]")
    else:
        gemini_md.write_text(section.lstrip("\n"))
        console.print("[green]Created GEMINI.md with hedwig-kg section[/]")

    # 2. Write BeforeTool hook to .gemini/settings.json
    settings_dir = project_root / ".gemini"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_file = settings_dir / "settings.json"

    hook_entry = {
        "matcher": "read_file",
        "hooks": [{
            "type": "command",
            "command": (
                '[ -f .hedwig-kg/knowledge.db ] && echo '
                '\'{"hookSpecificOutput":{"additionalContext":'
                '"hedwig-kg: Knowledge graph available. '
                "Use `hedwig-kg search \\\"<query>\\\"` (5-signal HybridRAG) "
                "instead of reading raw files. This single command covers "
                "vector, graph, keyword, and community search with RRF fusion."
                '"}}\' || true'
            ),
        }],
    }

    if settings_file.exists():
        settings = json.loads(settings_file.read_text())
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})
    before_hooks = hooks.setdefault("BeforeTool", [])

    already = any("hedwig-kg" in json.dumps(h) for h in before_hooks)
    if already:
        console.print("[dim].gemini/settings.json already has hedwig-kg BeforeTool hook.[/]")
    else:
        before_hooks.append(hook_entry)
        console.print("[green]Added BeforeTool hook to .gemini/settings.json[/]")

    # 3. Write SessionEnd hook for auto-rebuild
    session_end_entry = {
        "matcher": "*",
        "hooks": [{
            "type": "command",
            "command": _auto_rebuild_command(),
            "timeout": 10,
        }],
    }
    session_hooks = hooks.setdefault("SessionEnd", [])
    session_already = any("auto_rebuild" in json.dumps(h) for h in session_hooks)
    if session_already:
        console.print("[dim].gemini/settings.json already has hedwig-kg SessionEnd hook.[/]")
    else:
        session_hooks.append(session_end_entry)
        console.print("[green]Added SessionEnd hook for auto-rebuild to .gemini/settings.json[/]")

    settings_file.write_text(json.dumps(settings, indent=2) + "\n")

    console.print()
    console.print("[bold]Done![/] Gemini CLI will now use the knowledge graph "
                  "when working in this project.")
    console.print("[dim]Graph auto-rebuilds when your session ends.[/]")
    console.print("[dim]Run 'hedwig-kg gemini uninstall' to remove.[/]")


@gemini_group.command(name="uninstall")
def gemini_uninstall():
    """Remove per-project Gemini CLI integration."""
    import json

    project_root = Path.cwd()

    # 1. Remove section from GEMINI.md
    gemini_md = project_root / "GEMINI.md"
    if gemini_md.exists():
        lines = gemini_md.read_text().splitlines(keepends=True)
        filtered = []
        skip = False
        for line in lines:
            if line.strip() == "## hedwig-kg":
                skip = True
                continue
            if skip and line.startswith("##") and "hedwig-kg" not in line.lower():
                skip = False
            if skip:
                continue
            filtered.append(line)
        new_content = "".join(filtered).rstrip("\n") + "\n"
        gemini_md.write_text(new_content)
        console.print("[green]Removed hedwig-kg section from GEMINI.md[/]")

    # 2. Remove hooks from .gemini/settings.json
    settings_file = project_root / ".gemini" / "settings.json"
    if settings_file.exists():
        settings = json.loads(settings_file.read_text())
        hooks = settings.get("hooks", {})
        for event in ("BeforeTool", "SessionEnd"):
            event_hooks = hooks.get(event, [])
            hooks[event] = [
                h for h in event_hooks
                if "hedwig-kg" not in json.dumps(h)
                and "auto_rebuild" not in json.dumps(h)
            ]
            if not hooks[event]:
                hooks.pop(event, None)
        if not hooks:
            settings.pop("hooks", None)
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")
        console.print("[green]Removed hedwig-kg hooks from .gemini/settings.json[/]")

    console.print("[dim]hedwig-kg Gemini CLI integration removed.[/]")


cli.add_command(gemini_group)


# --- Cursor integration ---

@cli.group(name="cursor")
def cursor_group():
    """Manage per-project Cursor IDE integration."""
    pass


@cursor_group.command(name="install")
def cursor_install():
    """Install per-project Cursor integration (.cursor/rules/hedwig-kg.mdc)."""
    project_root = Path.cwd()

    rules_dir = project_root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_file = rules_dir / "hedwig-kg.mdc"

    rule_content = (
        "---\n"
        "description: hedwig-kg knowledge graph search rules\n"
        "globs: **/*\n"
        "alwaysApply: true\n"
        "---\n\n"
        "# hedwig-kg\n\n"
        "This project has a hedwig-kg knowledge graph at `.hedwig-kg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-kg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files, run `hedwig-kg search` first. "
        "Only fall back to grep/find if the knowledge graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-kg build . --incremental` to keep the graph current.\n"
        "- Use `hedwig-kg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-kg stats` for structural overview "
        "(god nodes, communities, density).\n"
    )

    if rules_file.exists():
        content = rules_file.read_text()
        if "hedwig-kg" in content:
            console.print("[dim].cursor/rules/hedwig-kg.mdc already exists.[/]")
        else:
            rules_file.write_text(rule_content)
            console.print("[green]Updated .cursor/rules/hedwig-kg.mdc[/]")
    else:
        rules_file.write_text(rule_content)
        console.print("[green]Created .cursor/rules/hedwig-kg.mdc[/]")

    console.print()
    console.print("[bold]Done![/] Cursor will now see hedwig-kg rules "
                  "when working in this project.")
    console.print("[dim]Run 'hedwig-kg cursor uninstall' to remove.[/]")


@cursor_group.command(name="uninstall")
def cursor_uninstall():
    """Remove per-project Cursor integration."""
    project_root = Path.cwd()

    rules_file = project_root / ".cursor" / "rules" / "hedwig-kg.mdc"
    if rules_file.exists():
        rules_file.unlink()
        console.print("[green]Removed .cursor/rules/hedwig-kg.mdc[/]")
    else:
        console.print("[dim]No hedwig-kg Cursor rule file found.[/]")

    console.print("[dim]hedwig-kg Cursor integration removed.[/]")


cli.add_command(cursor_group)


# --- Windsurf integration ---

@cli.group(name="windsurf")
def windsurf_group():
    """Manage per-project Windsurf IDE integration."""
    pass


@windsurf_group.command(name="install")
def windsurf_install():
    """Install per-project Windsurf integration (.windsurf/rules/hedwig-kg.md)."""
    project_root = Path.cwd()

    rules_dir = project_root / ".windsurf" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_file = rules_dir / "hedwig-kg.md"

    rule_content = (
        "# hedwig-kg\n\n"
        "This project has a hedwig-kg knowledge graph at `.hedwig-kg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-kg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files, run `hedwig-kg search` first. "
        "Only fall back to grep/find if the knowledge graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-kg build . --incremental` to keep the graph current.\n"
        "- Use `hedwig-kg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-kg stats` for structural overview "
        "(god nodes, communities, density).\n"
    )

    if rules_file.exists():
        content = rules_file.read_text()
        if "hedwig-kg" in content:
            console.print("[dim].windsurf/rules/hedwig-kg.md already exists.[/]")
        else:
            rules_file.write_text(rule_content)
            console.print("[green]Updated .windsurf/rules/hedwig-kg.md[/]")
    else:
        rules_file.write_text(rule_content)
        console.print("[green]Created .windsurf/rules/hedwig-kg.md[/]")

    console.print()
    console.print("[bold]Done![/] Windsurf Cascade will now see hedwig-kg rules "
                  "when working in this project.")
    console.print("[dim]Run 'hedwig-kg windsurf uninstall' to remove.[/]")


@windsurf_group.command(name="uninstall")
def windsurf_uninstall():
    """Remove per-project Windsurf integration."""
    project_root = Path.cwd()

    rules_file = project_root / ".windsurf" / "rules" / "hedwig-kg.md"
    if rules_file.exists():
        rules_file.unlink()
        console.print("[green]Removed .windsurf/rules/hedwig-kg.md[/]")
    else:
        console.print("[dim]No hedwig-kg Windsurf rule file found.[/]")

    console.print("[dim]hedwig-kg Windsurf integration removed.[/]")


cli.add_command(windsurf_group)


# --- Cline integration ---

@cli.group(name="cline")
def cline_group():
    """Manage per-project Cline (VS Code extension) integration."""
    pass


@cline_group.command(name="install")
def cline_install():
    """Install per-project Cline integration (.clinerules)."""
    project_root = Path.cwd()

    rules_file = project_root / ".clinerules"

    rule_content = (
        "# hedwig-kg\n\n"
        "This project has a hedwig-kg knowledge graph at `.hedwig-kg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-kg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files, run `hedwig-kg search` first. "
        "Only fall back to grep/find if the knowledge graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-kg build . --incremental` to keep the graph current.\n"
        "- Use `hedwig-kg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-kg stats` for structural overview "
        "(god nodes, communities, density).\n"
    )

    if rules_file.exists():
        content = rules_file.read_text()
        if "hedwig-kg" in content:
            console.print("[dim].clinerules already contains hedwig-kg rules.[/]")
        else:
            # Append to existing rules
            with open(rules_file, "a") as f:
                f.write("\n\n" + rule_content)
            console.print("[green]Appended hedwig-kg rules to .clinerules[/]")
    else:
        rules_file.write_text(rule_content)
        console.print("[green]Created .clinerules[/]")

    console.print()
    console.print("[bold]Done![/] Cline will now see hedwig-kg rules "
                  "when working in this project.")
    console.print("[dim]Run 'hedwig-kg cline uninstall' to remove.[/]")


@cline_group.command(name="uninstall")
def cline_uninstall():
    """Remove per-project Cline integration."""
    project_root = Path.cwd()

    rules_file = project_root / ".clinerules"
    if rules_file.exists():
        content = rules_file.read_text()
        if "hedwig-kg" in content:
            # Remove hedwig-kg section
            lines = content.split("\n")
            filtered = []
            skip = False
            for line in lines:
                if line.strip() == "# hedwig-kg":
                    skip = True
                    continue
                if skip and line.startswith("# ") and "hedwig-kg" not in line:
                    skip = False
                if not skip:
                    filtered.append(line)
            new_content = "\n".join(filtered).strip()
            if new_content:
                rules_file.write_text(new_content + "\n")
                console.print("[green]Removed hedwig-kg section from .clinerules[/]")
            else:
                rules_file.unlink()
                console.print("[green]Removed .clinerules (was hedwig-kg only)[/]")
        else:
            console.print("[dim]No hedwig-kg section found in .clinerules.[/]")
    else:
        console.print("[dim]No .clinerules file found.[/]")

    console.print("[dim]hedwig-kg Cline integration removed.[/]")


cli.add_command(cline_group)


# --- Aider integration ---

@cli.group(name="aider")
def aider_group():
    """Manage per-project Aider CLI integration."""
    pass


@aider_group.command(name="install")
def aider_install():
    """Install per-project Aider integration (CONVENTIONS.md + .aider.conf.yml)."""
    import yaml

    project_root = Path.cwd()

    # 1. Write CONVENTIONS.md with hedwig-kg rules
    conventions_md = project_root / "CONVENTIONS.md"
    marker = "## hedwig-kg"
    section = (
        "\n## hedwig-kg\n\n"
        "This project has a hedwig-kg knowledge graph at `.hedwig-kg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-kg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files, run `hedwig-kg search` first. "
        "Only fall back to grep/find if the knowledge graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-kg build . --incremental` to keep the graph current.\n"
        "- Use `hedwig-kg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-kg stats` for structural overview "
        "(god nodes, communities, density).\n"
    )

    if conventions_md.exists():
        content = conventions_md.read_text()
        if marker in content:
            console.print("[dim]CONVENTIONS.md already has hedwig-kg section.[/]")
        else:
            conventions_md.write_text(content + section)
            console.print("[green]Added hedwig-kg section to CONVENTIONS.md[/]")
    else:
        conventions_md.write_text(section.lstrip("\n"))
        console.print("[green]Created CONVENTIONS.md with hedwig-kg section[/]")

    # 2. Ensure .aider.conf.yml loads CONVENTIONS.md via read:
    conf_file = project_root / ".aider.conf.yml"
    if conf_file.exists():
        conf = yaml.safe_load(conf_file.read_text()) or {}
    else:
        conf = {}

    read_list = conf.get("read", [])
    if isinstance(read_list, str):
        read_list = [read_list]
    if "CONVENTIONS.md" not in read_list:
        read_list.append("CONVENTIONS.md")
        conf["read"] = read_list
        conf_file.write_text(yaml.dump(conf, default_flow_style=False))
        console.print("[green]Added CONVENTIONS.md to .aider.conf.yml read list[/]")
    else:
        console.print("[dim].aider.conf.yml already reads CONVENTIONS.md[/]")

    console.print()
    console.print("[bold]Done![/] Aider will now load hedwig-kg conventions "
                  "when working in this project.")
    console.print("[dim]Run 'hedwig-kg aider uninstall' to remove.[/]")


@aider_group.command(name="uninstall")
def aider_uninstall():
    """Remove per-project Aider integration."""
    import yaml

    project_root = Path.cwd()

    # 1. Remove section from CONVENTIONS.md
    conventions_md = project_root / "CONVENTIONS.md"
    if conventions_md.exists():
        lines = conventions_md.read_text().splitlines(keepends=True)
        filtered = []
        skip = False
        for line in lines:
            if line.strip() == "## hedwig-kg":
                skip = True
                continue
            if skip and line.startswith("##") and "hedwig-kg" not in line.lower():
                skip = False
            if skip:
                continue
            filtered.append(line)
        new_content = "".join(filtered).rstrip("\n") + "\n"
        conventions_md.write_text(new_content)
        console.print("[green]Removed hedwig-kg section from CONVENTIONS.md[/]")

    # 2. Remove CONVENTIONS.md from .aider.conf.yml read list
    conf_file = project_root / ".aider.conf.yml"
    if conf_file.exists():
        conf = yaml.safe_load(conf_file.read_text()) or {}
        read_list = conf.get("read", [])
        if isinstance(read_list, str):
            read_list = [read_list]
        if "CONVENTIONS.md" in read_list:
            read_list.remove("CONVENTIONS.md")
            if read_list:
                conf["read"] = read_list
            else:
                conf.pop("read", None)
            if conf:
                conf_file.write_text(yaml.dump(conf, default_flow_style=False))
            else:
                conf_file.unlink()
            console.print("[green]Removed CONVENTIONS.md from .aider.conf.yml[/]")

    console.print("[dim]hedwig-kg Aider integration removed.[/]")


cli.add_command(aider_group)


@cli.command()
def doctor():
    """Check hedwig-kg installation health and knowledge graph integrity.

    Verifies dependencies, model availability, database integrity,
    and graph quality metrics. Useful for troubleshooting issues.
    """
    import importlib
    import sqlite3
    import sys

    from rich.panel import Panel

    checks_passed = 0
    checks_failed = 0
    checks_warned = 0

    def ok(msg: str):
        nonlocal checks_passed
        checks_passed += 1
        console.print(f"  [green]✓[/] {msg}")

    def fail(msg: str):
        nonlocal checks_failed
        checks_failed += 1
        console.print(f"  [red]✗[/] {msg}")

    def warn(msg: str):
        nonlocal checks_warned
        checks_warned += 1
        console.print(f"  [yellow]![/] {msg}")

    console.print(Panel("[bold]hedwig-kg doctor[/]", subtitle="Installation Health Check"))
    console.print()

    # 1. Python version
    console.print("[bold]Python Environment[/]")
    v = sys.version_info
    if v >= (3, 10):
        ok(f"Python {v.major}.{v.minor}.{v.micro}")
    else:
        fail(f"Python {v.major}.{v.minor}.{v.micro} (requires >= 3.10)")

    # 2. Core dependencies
    console.print("\n[bold]Core Dependencies[/]")
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
            ok(f"{pip_name} ({ver})")
        except ImportError:
            fail(f"{pip_name} — not installed (pip install {pip_name})")

    # 3. Tree-sitter parsers
    console.print("\n[bold]Tree-sitter Parsers[/]")
    ts_langs = [
        ("tree_sitter", "tree-sitter"),
        ("tree_sitter_python", "tree-sitter-python"),
        ("tree_sitter_javascript", "tree-sitter-javascript"),
    ]
    for mod_name, pip_name in ts_langs:
        try:
            importlib.import_module(mod_name)
            ok(pip_name)
        except ImportError:
            warn(f"{pip_name} — not installed (optional, enables AST extraction)")

    # 4. MCP server dependency
    console.print("\n[bold]MCP Server[/]")
    try:
        importlib.import_module("mcp")
        ok("mcp (Model Context Protocol server available)")
    except ImportError:
        warn("mcp — not installed (optional, install with: pip install mcp)")

    # 5. Embedding models
    console.print("\n[bold]Embedding Models[/]")
    model_cache = Path.home() / ".hedwig-kg" / "models"
    if model_cache.exists():
        cached_models = [d.name for d in model_cache.iterdir() if d.is_dir()]
        if cached_models:
            for m in cached_models:
                ok(f"Cached: {m}")
        else:
            warn("Model cache exists but empty — models will download on first build")
    else:
        warn("No model cache at ~/.hedwig-kg/models/ — models will download on first build")

    # 6. Knowledge graph database
    console.print("\n[bold]Knowledge Graph Database[/]")
    cwd = Path.cwd()
    db_path = cwd / ".hedwig-kg" / "knowledge.db"
    if db_path.exists():
        ok(f"Database found: {db_path}")
        # Check integrity
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity == "ok":
                ok("Database integrity: OK")
            else:
                fail(f"Database integrity: {integrity}")

            # Node count
            try:
                n_nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
                n_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
                ok(f"Nodes: {n_nodes}, Edges: {n_edges}")
                if n_nodes == 0:
                    warn("Graph is empty — run 'hedwig-kg build .' to populate")
            except sqlite3.OperationalError:
                fail("Missing nodes/edges tables — database may be corrupted")

            # FTS5 index
            try:
                conn.execute("SELECT COUNT(*) FROM nodes_fts").fetchone()
                ok("FTS5 full-text search index: present")
            except sqlite3.OperationalError:
                warn("FTS5 index missing — keyword search may not work")

            # Communities
            try:
                n_comm = conn.execute("SELECT COUNT(*) FROM communities").fetchone()[0]
                ok(f"Communities: {n_comm}")
            except sqlite3.OperationalError:
                warn("Communities table missing — run build to generate")

            # FAISS index
            faiss_path = cwd / ".hedwig-kg" / "faiss_code.index"
            faiss_text_path = cwd / ".hedwig-kg" / "faiss_text.index"
            if faiss_path.exists() and faiss_text_path.exists():
                code_size = faiss_path.stat().st_size / 1024
                text_size = faiss_text_path.stat().st_size / 1024
                ok(f"FAISS code index: {code_size:.1f} KB")
                ok(f"FAISS text index: {text_size:.1f} KB")
            elif faiss_path.exists() or faiss_text_path.exists():
                warn("Only one FAISS index found — dual-model search may be degraded")
            else:
                warn("No FAISS indexes — run 'hedwig-kg build .' (without --no-embed)")

            conn.close()
        except sqlite3.DatabaseError as e:
            fail(f"Cannot open database: {e}")
    else:
        warn(f"No database at {db_path} — run 'hedwig-kg build .' to create")

    # Summary
    console.print()
    total = checks_passed + checks_failed + checks_warned
    if checks_failed == 0:
        emoji = "✅" if checks_warned == 0 else "⚠️"
        console.print(Panel(
            f"{emoji} {checks_passed}/{total} checks passed"
            + (f", {checks_warned} warnings" if checks_warned else ""),
            title="[bold green]Health Check Complete[/]",
        ))
    else:
        console.print(Panel(
            f"❌ {checks_failed} failed, {checks_warned} warnings, "
            f"{checks_passed} passed out of {total}",
            title="[bold red]Issues Found[/]",
        ))


@cli.command()
def mcp():
    """Start the hedwig-kg MCP server (stdio transport).

    Exposes knowledge graph tools to AI agents via the Model Context Protocol.
    Tools: search, node, stats, communities, build.

    Configure in Claude Code:

        claude mcp add hedwig-kg -- hedwig-kg mcp

    Or in .cursor/mcp.json / .vscode/mcp.json:

        { "mcpServers": { "hedwig-kg": { "command": "hedwig-kg", "args": ["mcp"] } } }
    """
    console.print("[bold green]Starting hedwig-kg MCP server...[/]")
    console.print("[dim]Transport: stdio | Tools: search, node, stats, communities, build[/]")
    from hedwig_kg.mcp_server import main as mcp_main
    mcp_main()


if __name__ == "__main__":
    cli()
