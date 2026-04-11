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


@click.group()
@click.version_option(version=None, prog_name="hedwig-kg", package_name="hedwig-kg")
def cli():
    """hedwig-kg: Local-first knowledge graph with hybrid search."""
    pass


@cli.command()
@click.argument("source_dir", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output directory for the database")
@click.option("--no-embed", is_flag=True, help="Skip embedding generation")
@click.option("--model", default="all-MiniLM-L6-v2", help="Sentence-transformers model name")
@click.option("--max-file-size", default=1_000_000, type=int, help="Max file size in bytes")
@click.option("--incremental", is_flag=True, help="Skip unchanged files (faster rebuilds)")
def build(
    source_dir: str, output: str | None, no_embed: bool,
    model: str, max_file_size: int, incremental: bool,
):
    """Build knowledge graph from a source directory."""
    from hedwig_kg.core.pipeline import run_pipeline

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
        )

    # Summary
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


@cli.command()
@click.argument("query")
@click.option("--db", type=click.Path(), default=None, help="Path to knowledge.db")
@click.option("--top-k", default=10, type=int, help="Number of results")
@click.option("--source-dir", type=click.Path(), default=".",
              help="Source dir (to find default DB)")
def search(query: str, db: str | None, top_k: int, source_dir: str):
    """Search the knowledge graph with hybrid vector + graph + keyword search."""
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

    # Build vector index
    try:
        store.build_vector_index()
    except Exception:
        console.print("[dim]Vector index not available, keyword search only.[/]")

    results = hybrid_search(query, store, G, top_k=top_k)
    _print_search_results(query, results)
    store.close()


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
    table.add_column("Neighbors", style="dim")

    for i, r in enumerate(results, 1):
        table.add_row(
            str(i),
            r.label,
            r.kind,
            str(Path(r.file_path).name) if r.file_path else "",
            f"{r.score:.4f}",
            ", ".join(r.neighbors[:3]),
        )

    console.print(table)


@cli.command()
@click.option("--db", type=click.Path(), default=None, help="Path to knowledge.db")
@click.option("--source-dir", type=click.Path(), default=".", help="Source dir")
def stats(db: str | None, source_dir: str):
    """Show knowledge graph statistics."""
    from hedwig_kg.storage.store import KnowledgeStore

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        console.print("[red]No knowledge base found. Run 'hedwig-kg build' first.[/]")
        raise SystemExit(1)

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    table = Table(title="Knowledge Base Statistics")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Nodes", str(G.number_of_nodes()))
    table.add_row("Edges", str(G.number_of_edges()))

    # Node kinds
    kinds: dict[str, int] = {}
    for _, data in G.nodes(data=True):
        k = data.get("kind", "unknown")
        kinds[k] = kinds.get(k, 0) + 1
    for k, v in sorted(kinds.items(), key=lambda x: -x[1]):
        table.add_row(f"  {k}", str(v))

    # Edge confidence
    conf: dict[str, int] = {}
    for _, _, data in G.edges(data=True):
        c = data.get("confidence", "EXTRACTED")
        conf[c] = conf.get(c, 0) + 1
    for c, v in sorted(conf.items()):
        table.add_row(f"  {c} edges", str(v))

    # Graph quality metrics
    import networkx as nx

    if G.number_of_nodes() > 0:
        density = nx.density(G)
        table.add_row("Density", f"{density:.4f}")

        undirected = G.to_undirected()
        components = nx.number_connected_components(undirected)
        table.add_row("Connected components", str(components))

        try:
            avg_clustering = nx.average_clustering(undirected)
            table.add_row("Avg clustering coeff", f"{avg_clustering:.4f}")
        except Exception:
            pass

    # Communities
    comm_count = store.conn.execute("SELECT COUNT(*) FROM communities").fetchone()[0]
    table.add_row("Communities", str(comm_count))

    # Embeddings
    emb_count = store.conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
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
def communities(db: str | None, source_dir: str, level: int | None, query: str | None):
    """List and search communities in the knowledge graph."""
    from hedwig_kg.storage.store import KnowledgeStore

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        console.print("[red]No knowledge base found. Run 'hedwig-kg build' first.[/]")
        raise SystemExit(1)

    store = KnowledgeStore(db_path)

    if query:
        terms = [t.lower() for t in query.split() if len(t) > 2]
        results = store.community_search(terms, top_k=10)
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
@click.option("--top-k", default=10, type=int, help="Number of results per query")
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

    console.print(f"[bold green]hedwig-kg query REPL[/] — "
                  f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    console.print("[dim]Type a query to search. :quit to exit. :node <id> for details.[/]\n")

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
def show_node(node_id: str, db: str | None, source_dir: str):
    """Show details of a specific node."""
    from hedwig_kg.storage.store import KnowledgeStore

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        console.print("[red]No knowledge base found.[/]")
        raise SystemExit(1)

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    if node_id not in G:
        # Try fuzzy match
        matches = [n for n in G.nodes() if node_id.lower() in n.lower()]
        if not matches:
            console.print(f"[red]Node '{node_id}' not found.[/]")
            store.close()
            return
        node_id = matches[0]
        if len(matches) > 1:
            console.print(f"[yellow]Multiple matches, showing: {node_id}[/]")

    data = G.nodes[node_id]
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


@cli.group(name="claude")
def claude_group():
    """Manage per-project Claude Code integration."""
    pass


@claude_group.command(name="install")
def claude_install():
    """Install per-project Claude Code integration (CLAUDE.md + PreToolUse hook)."""
    import json

    project_root = Path.cwd()

    # 1. Write section to project CLAUDE.md
    claude_md = project_root / "CLAUDE.md"
    marker = "## hedwig-kg"
    section = (
        "\n## hedwig-kg\n\n"
        "This project has a hedwig-kg knowledge graph at `.hedwig-kg/`.\n\n"
        "Rules:\n"
        "- Before answering architecture or codebase questions, "
        "run `hedwig-kg search \"<query>\"` for graph-aware results\n"
        "- Use `hedwig-kg stats` for structural overview "
        "(god nodes, communities, density)\n"
        "- After modifying code files, run "
        "`hedwig-kg build . --incremental` to keep the graph current\n"
        "- Use `hedwig-kg communities --search \"<topic>\"` "
        "for high-level architecture understanding\n"
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
                "Consider running `hedwig-kg search` for graph-aware results "
                'before grepping raw files."}}\' || true'
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
        console.print("[dim].claude/settings.json already has hedwig-kg hook.[/]")
    else:
        pre_hooks.append(hook_entry)
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")
        console.print("[green]Added PreToolUse hook to .claude/settings.json[/]")

    console.print()
    console.print("[bold]Done![/] Claude Code will now use the knowledge graph "
                  "when searching this project.")
    console.print("[dim]Run 'hedwig-kg claude uninstall' to remove.[/]")


@claude_group.command(name="uninstall")
def claude_uninstall():
    """Remove per-project Claude Code integration."""
    import json

    project_root = Path.cwd()

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

    # 2. Remove hook from .claude/settings.json
    settings_file = project_root / ".claude" / "settings.json"
    if settings_file.exists():
        settings = json.loads(settings_file.read_text())
        hooks = settings.get("hooks", {})
        pre_hooks = hooks.get("PreToolUse", [])
        hooks["PreToolUse"] = [
            h for h in pre_hooks
            if "hedwig-kg" not in json.dumps(h)
        ]
        if not hooks["PreToolUse"]:
            del hooks["PreToolUse"]
        if not hooks:
            del settings["hooks"]
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")
        console.print("[green]Removed PreToolUse hook from .claude/settings.json[/]")

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
        "- Before answering architecture or codebase questions, "
        "run `hedwig-kg search \"<query>\"` for graph-aware results\n"
        "- Use `hedwig-kg stats` for structural overview "
        "(god nodes, communities, density)\n"
        "- After modifying code files, run "
        "`hedwig-kg build . --incremental` to keep the graph current\n"
        "- Use `hedwig-kg communities --search \"<topic>\"` "
        "for high-level architecture understanding\n"
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
                "Consider running `hedwig-kg search` for graph-aware results "
                'before grepping raw files."}}\' || true'
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
        console.print("[dim].codex/hooks.json already has hedwig-kg hook.[/]")
    else:
        pre_hooks.append(hook_entry)
        hooks_file.write_text(json.dumps(hooks_data, indent=2) + "\n")
        console.print("[green]Added PreToolUse hook to .codex/hooks.json[/]")

    console.print()
    console.print("[bold]Done![/] Codex CLI will now use the knowledge graph "
                  "when working in this project.")
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

    # 2. Remove hook from .codex/hooks.json
    hooks_file = project_root / ".codex" / "hooks.json"
    if hooks_file.exists():
        hooks_data = json.loads(hooks_file.read_text())
        hooks = hooks_data.get("hooks", {})
        pre_hooks = hooks.get("PreToolUse", [])
        hooks["PreToolUse"] = [
            h for h in pre_hooks
            if "hedwig-kg" not in json.dumps(h)
        ]
        if not hooks["PreToolUse"]:
            del hooks["PreToolUse"]
        if not hooks:
            del hooks_data["hooks"]
        hooks_file.write_text(json.dumps(hooks_data, indent=2) + "\n")
        console.print("[green]Removed PreToolUse hook from .codex/hooks.json[/]")

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
        "- Before answering architecture or codebase questions, "
        "run `hedwig-kg search \"<query>\"` for graph-aware results\n"
        "- Use `hedwig-kg stats` for structural overview "
        "(god nodes, communities, density)\n"
        "- After modifying code files, run "
        "`hedwig-kg build . --incremental` to keep the graph current\n"
        "- Use `hedwig-kg communities --search \"<topic>\"` "
        "for high-level architecture understanding\n"
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
                "Consider running `hedwig-kg search` for graph-aware results "
                'before reading raw files."}}\' || true'
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
        console.print("[dim].gemini/settings.json already has hedwig-kg hook.[/]")
    else:
        before_hooks.append(hook_entry)
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")
        console.print("[green]Added BeforeTool hook to .gemini/settings.json[/]")

    console.print()
    console.print("[bold]Done![/] Gemini CLI will now use the knowledge graph "
                  "when working in this project.")
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

    # 2. Remove hook from .gemini/settings.json
    settings_file = project_root / ".gemini" / "settings.json"
    if settings_file.exists():
        settings = json.loads(settings_file.read_text())
        hooks = settings.get("hooks", {})
        before_hooks = hooks.get("BeforeTool", [])
        hooks["BeforeTool"] = [
            h for h in before_hooks
            if "hedwig-kg" not in json.dumps(h)
        ]
        if not hooks["BeforeTool"]:
            del hooks["BeforeTool"]
        if not hooks:
            del settings["hooks"]
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")
        console.print("[green]Removed BeforeTool hook from .gemini/settings.json[/]")

    console.print("[dim]hedwig-kg Gemini CLI integration removed.[/]")


cli.add_command(gemini_group)


if __name__ == "__main__":
    cli()
