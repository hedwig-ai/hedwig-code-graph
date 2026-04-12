"""CLI interface for hedwig-cg.

Usage:
    hedwig-cg build <source_dir> [--output <dir>] [--no-embed] [--model <name>]
    hedwig-cg search <query> [--db <path>] [--top-k <n>]
    hedwig-cg stats [--db <path>]
    hedwig-cg export [--db <path>] [--format json|graphml]
"""

from __future__ import annotations

from pathlib import Path

import click


def _suppress_library_logs():
    """Suppress noisy library logs."""
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
    click.echo(json.dumps(data, separators=(",", ":"), default=str))


def _json_error(message: str) -> None:
    """Print error as JSON and exit with code 1."""
    import json
    click.echo(json.dumps({"error": message}))
    raise SystemExit(1)


@click.group()
@click.version_option(version=None, prog_name="hedwig-cg", package_name="hedwig-cg")
@click.pass_context
def cli(ctx):
    """hedwig-cg: Local-first code graph with hybrid search."""
    ctx.ensure_object(dict)
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
    """Build code graph from a source directory."""
    from hedwig_cg.core.pipeline import run_pipeline

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

    _json_out({
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
@click.option("--top-k", default=80, type=int, help="Number of results")
@click.option("--source-dir", type=click.Path(), default=".",
              help="Source dir (to find default DB)")
@click.option("--fast", is_flag=True, default=False,
              help="Fast mode: text model only (lower latency, slightly reduced accuracy)")
@click.option("--expand", is_flag=True, default=False,
              help="Two-stage query expansion: re-search with neighbor terms for broader recall")
@click.pass_context
def search(ctx, query: str, db: str | None, top_k: int, source_dir: str, fast: bool, expand: bool):
    """Search the code graph with hybrid vector + graph + keyword search."""
    from hedwig_cg.query.hybrid import expanded_search, hybrid_search
    from hedwig_cg.storage.store import KnowledgeStore

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        _json_error("No knowledge base found. Run 'hedwig-cg build' first.")

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    if G.number_of_nodes() == 0:
        _json_out([])
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

    _json_out([_compact_result(r) for r in results])
    store.close()


@cli.command()
@click.option("--db", type=click.Path(), default=None)
@click.option("--source-dir", type=click.Path(), default=".", help="Source dir")
@click.pass_context
def stats(ctx, db: str | None, source_dir: str):
    """Show code graph statistics."""
    from hedwig_cg.storage.store import KnowledgeStore

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        _json_error("No knowledge base found. Run 'hedwig-cg build' first.")

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


@cli.command()
@click.option("--db", type=click.Path(), default=None)
@click.option("--source-dir", type=click.Path(), default=".", help="Source dir")
@click.option("--level", type=int, default=None, help="Filter by hierarchy level")
@click.option("--search", "query", type=str, default=None, help="Search community summaries")
@click.pass_context
def communities(ctx, db: str | None, source_dir: str, level: int | None, query: str | None):
    """List and search communities in the code graph."""
    from hedwig_cg.storage.store import KnowledgeStore

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        _json_error("No knowledge base found. Run 'hedwig-cg build' first.")

    store = KnowledgeStore(db_path)

    if query:
        terms = [t.lower() for t in query.split() if len(t) > 2]
        results = store.community_search(terms, top_k=10)
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

    sql = "SELECT id, level, resolution, summary FROM communities"
    params: list = []
    if level is not None:
        sql += " WHERE level = ?"
        params.append(level)
    sql += " ORDER BY level, id"
    rows = store.conn.execute(sql, params).fetchall()

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

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        _json_error("No knowledge base found.")

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

    _json_out({"exported": str(out), "format": fmt})
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

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        _json_error("No knowledge base found. Run 'hedwig-cg build' first.")

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

    _json_out({
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
            _json_out({"message": "Database not found."})
            return
        if not yes:
            click.confirm(f"Delete {target}?", abort=True)
        target.unlink()
        _json_out({"removed": str(target)})
    else:
        kb_dir = Path(source_dir).resolve() / ".hedwig-cg"
        if not kb_dir.exists():
            _json_out({"message": "No .hedwig-cg/ directory found."})
            return
        if not yes:
            click.confirm(f"Delete {kb_dir}/?", abort=True)
        shutil.rmtree(kb_dir)
        _json_out({"removed": str(kb_dir)})


@cli.command()
@click.option("--db", type=click.Path(), default=None, help="Path to knowledge.db")
@click.option("--source-dir", type=click.Path(), default=".", help="Source dir")
@click.option("--top-k", default=80, type=int, help="Number of results per query")
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

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        _json_error("No knowledge base found. Run 'hedwig-cg build' first.")

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    if G.number_of_nodes() == 0:
        _json_out({"message": "Knowledge base is empty."})
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

    _json_out({"status": "ready", "nodes": G.number_of_nodes(),
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
            _json_out({"nodes": G.number_of_nodes(),
                        "edges": G.number_of_edges()})
        else:
            results = hybrid_search(user_input, store, G, top_k=top_k)
            _json_out([{"label": r.label, "kind": r.kind, "score": round(r.score, 3)}
                       for r in results])

    store.close()
    _json_out({"status": "session_ended"})


def _repl_show_node(G, node_id: str) -> None:
    """Show node details in REPL mode."""
    if node_id not in G:
        matches = [n for n in G.nodes() if node_id.lower() in n.lower()]
        if not matches:
            _json_out({"error": f"Node '{node_id}' not found."})
            return
        node_id = matches[0]

    data = G.nodes[node_id]
    _json_out({
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


def _resolve_db(db: str | None, source_dir: str) -> Path | None:
    """Find the knowledge database."""
    if db:
        p = Path(db)
        return p if p.exists() else None

    # Default location
    default = Path(source_dir).resolve() / ".hedwig-cg" / "knowledge.db"
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
    from hedwig_cg.storage.store import KnowledgeStore

    db_path = _resolve_db(db, source_dir)
    if not db_path:
        _json_error("No knowledge base found.")

    store = KnowledgeStore(db_path)
    G = store.load_graph()

    if node_id not in G:
        # Try fuzzy match
        matches = [n for n in G.nodes() if node_id.lower() in n.lower()]
        if not matches:
            _json_error(f"Node '{node_id}' not found.")
        node_id = matches[0]

    data = G.nodes[node_id]

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

    # --- Default to user scope (no interactive prompt for agent use) ---
    if scope is None:
        scope = "user"

    # --- Priority 1: Install Skill ---
    skill_source = Path(__file__).parent.parent / "skill.md"
    if scope == "user":
        skill_dir = Path.home() / ".claude" / "skills" / "hedwig-cg"
    else:
        skill_dir = project_root / ".claude" / "skills" / "hedwig-cg"

    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_dest = skill_dir / "SKILL.md"

    actions = []

    if skill_source.exists():
        shutil.copy2(skill_source, skill_dest)
        actions.append(f"skill_installed:{scope}")
    else:
        actions.append("skill_source_not_found")

    # --- Priority 2: CLAUDE.md + hooks ---
    # 1. Write section to project CLAUDE.md
    claude_md = project_root / "CLAUDE.md"
    marker = "## hedwig-cg"
    section = (
        "\n## hedwig-cg\n\n"
        "This project has a hedwig-cg code graph at `.hedwig-cg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-cg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files with Glob/Grep, run `hedwig-cg search` first. "
        "Only fall back to Grep if the code graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-cg build . --incremental` to keep the graph current\n"
        "- Use `hedwig-cg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-cg stats` for structural overview "
        "(god nodes, communities, density)\n"
    )

    if claude_md.exists():
        content = claude_md.read_text()
        if marker in content:
            actions.append("claude_md:already_exists")
        else:
            claude_md.write_text(content + section)
            actions.append("claude_md:added")
    else:
        claude_md.write_text(section.lstrip("\n"))
        actions.append("claude_md:created")

    # 2. Write PreToolUse hook to .claude/settings.json
    settings_dir = project_root / ".claude"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_file = settings_dir / "settings.json"

    hook_entry = {
        "matcher": "Glob|Grep",
        "hooks": [{
            "type": "command",
            "command": (
                '[ -f .hedwig-cg/knowledge.db ] && echo '
                '\'{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
                '"additionalContext":"hedwig-cg: code graph available. '
                "Use `hedwig-cg search \\\"<query>\\\"` (5-signal HybridRAG) "
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

    already = any(
        "hedwig-cg" in json.dumps(h)
        for h in pre_hooks
    )
    if already:
        actions.append("pretooluse_hook:already_exists")
    else:
        pre_hooks.append(hook_entry)
        actions.append("pretooluse_hook:added")

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
    stop_already = any("hedwig-cg" in json.dumps(h) or "auto_rebuild" in json.dumps(h)
                       for h in stop_hooks)
    if stop_already:
        actions.append("stop_hook:already_exists")
    else:
        stop_hooks.append(stop_hook_entry)
        actions.append("stop_hook:added")

    settings_file.write_text(json.dumps(settings, indent=2) + "\n")

    _json_out({"installed": True, "scope": scope, "actions": actions})


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
    actions = []

    # 0. Remove skill
    if scope in ("user", "all"):
        user_skill = Path.home() / ".claude" / "skills" / "hedwig-cg"
        if user_skill.exists():
            shutil.rmtree(user_skill)
            actions.append("skill_removed:user")
    if scope in ("project", "all"):
        proj_skill = project_root / ".claude" / "skills" / "hedwig-cg"
        if proj_skill.exists():
            shutil.rmtree(proj_skill)
            actions.append("skill_removed:project")

    # 1. Remove section from CLAUDE.md
    claude_md = project_root / "CLAUDE.md"
    if claude_md.exists():
        lines = claude_md.read_text().splitlines(keepends=True)
        filtered = []
        skip = False
        for line in lines:
            if line.strip() == "## hedwig-cg":
                skip = True
                continue
            if skip and line.startswith("##") and "hedwig-cg" not in line.lower():
                skip = False
            if skip:
                continue
            filtered.append(line)
        new_content = "".join(filtered).rstrip("\n") + "\n"
        claude_md.write_text(new_content)
        actions.append("claude_md:removed")

    # 2. Remove hooks from .claude/settings.json
    settings_file = project_root / ".claude" / "settings.json"
    if settings_file.exists():
        settings = json.loads(settings_file.read_text())
        hooks = settings.get("hooks", {})
        for event in ("PreToolUse", "Stop"):
            event_hooks = hooks.get(event, [])
            hooks[event] = [
                h for h in event_hooks
                if "hedwig-cg" not in json.dumps(h)
                and "auto_rebuild" not in json.dumps(h)
            ]
            if not hooks[event]:
                hooks.pop(event, None)
        if not hooks:
            settings.pop("hooks", None)
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")
        actions.append("hooks:removed")

    _json_out({"uninstalled": True, "scope": scope, "actions": actions})


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
    marker = "## hedwig-cg"
    section = (
        "\n## hedwig-cg\n\n"
        "This project has a hedwig-cg code graph at `.hedwig-cg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-cg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files, run `hedwig-cg search` first. "
        "Only fall back to grep if the code graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-cg build . --incremental` to keep the graph current\n"
        "- Use `hedwig-cg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-cg stats` for structural overview "
        "(god nodes, communities, density)\n"
    )

    actions = []

    if agents_md.exists():
        content = agents_md.read_text()
        if marker in content:
            actions.append("agents_md:already_exists")
        else:
            agents_md.write_text(content + section)
            actions.append("agents_md:added")
    else:
        agents_md.write_text(section.lstrip("\n"))
        actions.append("agents_md:created")

    # 2. Write PreToolUse hook to .codex/hooks.json
    hooks_dir = project_root / ".codex"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hooks_file = hooks_dir / "hooks.json"

    hook_entry = {
        "matcher": "Bash",
        "hooks": [{
            "type": "command",
            "command": (
                '[ -f .hedwig-cg/knowledge.db ] && echo '
                '\'{"hookSpecificOutput":{"hookEventName":"PreToolUse",'
                '"additionalContext":"hedwig-cg: code graph available. '
                "Use `hedwig-cg search \\\"<query>\\\"` (5-signal HybridRAG) "
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

    already = any("hedwig-cg" in json.dumps(h) for h in pre_hooks)
    if already:
        actions.append("pretooluse_hook:already_exists")
    else:
        pre_hooks.append(hook_entry)
        actions.append("pretooluse_hook:added")

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
        actions.append("stop_hook:already_exists")
    else:
        stop_hooks.append(stop_hook_entry)
        actions.append("stop_hook:added")

    hooks_file.write_text(json.dumps(hooks_data, indent=2) + "\n")

    _json_out({"installed": True, "actions": actions})


@codex_group.command(name="uninstall")
def codex_uninstall():
    """Remove per-project Codex CLI integration."""
    import json

    project_root = Path.cwd()
    actions = []

    # 1. Remove section from AGENTS.md
    agents_md = project_root / "AGENTS.md"
    if agents_md.exists():
        lines = agents_md.read_text().splitlines(keepends=True)
        filtered = []
        skip = False
        for line in lines:
            if line.strip() == "## hedwig-cg":
                skip = True
                continue
            if skip and line.startswith("##") and "hedwig-cg" not in line.lower():
                skip = False
            if skip:
                continue
            filtered.append(line)
        new_content = "".join(filtered).rstrip("\n") + "\n"
        agents_md.write_text(new_content)
        actions.append("agents_md:removed")

    # 2. Remove hooks from .codex/hooks.json
    hooks_file = project_root / ".codex" / "hooks.json"
    if hooks_file.exists():
        hooks_data = json.loads(hooks_file.read_text())
        hooks = hooks_data.get("hooks", {})
        for event in ("PreToolUse", "Stop"):
            event_hooks = hooks.get(event, [])
            hooks[event] = [
                h for h in event_hooks
                if "hedwig-cg" not in json.dumps(h)
                and "auto_rebuild" not in json.dumps(h)
            ]
            if not hooks[event]:
                hooks.pop(event, None)
        if not hooks:
            hooks_data.pop("hooks", None)
        hooks_file.write_text(json.dumps(hooks_data, indent=2) + "\n")
        actions.append("hooks:removed")

    _json_out({"uninstalled": True, "actions": actions})


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
    marker = "## hedwig-cg"
    section = (
        "\n## hedwig-cg\n\n"
        "This project has a hedwig-cg code graph at `.hedwig-cg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-cg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before reading raw files, run `hedwig-cg search` first. "
        "Only fall back to file reads if the code graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-cg build . --incremental` to keep the graph current\n"
        "- Use `hedwig-cg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-cg stats` for structural overview "
        "(god nodes, communities, density)\n"
    )

    actions = []

    if gemini_md.exists():
        content = gemini_md.read_text()
        if marker in content:
            actions.append("gemini_md:already_exists")
        else:
            gemini_md.write_text(content + section)
            actions.append("gemini_md:added")
    else:
        gemini_md.write_text(section.lstrip("\n"))
        actions.append("gemini_md:created")

    # 2. Write BeforeTool hook to .gemini/settings.json
    settings_dir = project_root / ".gemini"
    settings_dir.mkdir(parents=True, exist_ok=True)
    settings_file = settings_dir / "settings.json"

    hook_entry = {
        "matcher": "read_file",
        "hooks": [{
            "type": "command",
            "command": (
                '[ -f .hedwig-cg/knowledge.db ] && echo '
                '\'{"hookSpecificOutput":{"additionalContext":'
                '"hedwig-cg: code graph available. '
                "Use `hedwig-cg search \\\"<query>\\\"` (5-signal HybridRAG) "
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

    already = any("hedwig-cg" in json.dumps(h) for h in before_hooks)
    if already:
        actions.append("beforetool_hook:already_exists")
    else:
        before_hooks.append(hook_entry)
        actions.append("beforetool_hook:added")

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
        actions.append("sessionend_hook:already_exists")
    else:
        session_hooks.append(session_end_entry)
        actions.append("sessionend_hook:added")

    settings_file.write_text(json.dumps(settings, indent=2) + "\n")

    _json_out({"installed": True, "actions": actions})


@gemini_group.command(name="uninstall")
def gemini_uninstall():
    """Remove per-project Gemini CLI integration."""
    import json

    project_root = Path.cwd()
    actions = []

    # 1. Remove section from GEMINI.md
    gemini_md = project_root / "GEMINI.md"
    if gemini_md.exists():
        lines = gemini_md.read_text().splitlines(keepends=True)
        filtered = []
        skip = False
        for line in lines:
            if line.strip() == "## hedwig-cg":
                skip = True
                continue
            if skip and line.startswith("##") and "hedwig-cg" not in line.lower():
                skip = False
            if skip:
                continue
            filtered.append(line)
        new_content = "".join(filtered).rstrip("\n") + "\n"
        gemini_md.write_text(new_content)
        actions.append("gemini_md:removed")

    # 2. Remove hooks from .gemini/settings.json
    settings_file = project_root / ".gemini" / "settings.json"
    if settings_file.exists():
        settings = json.loads(settings_file.read_text())
        hooks = settings.get("hooks", {})
        for event in ("BeforeTool", "SessionEnd"):
            event_hooks = hooks.get(event, [])
            hooks[event] = [
                h for h in event_hooks
                if "hedwig-cg" not in json.dumps(h)
                and "auto_rebuild" not in json.dumps(h)
            ]
            if not hooks[event]:
                hooks.pop(event, None)
        if not hooks:
            settings.pop("hooks", None)
        settings_file.write_text(json.dumps(settings, indent=2) + "\n")
        actions.append("hooks:removed")

    _json_out({"uninstalled": True, "actions": actions})


cli.add_command(gemini_group)


# --- Cursor integration ---

@cli.group(name="cursor")
def cursor_group():
    """Manage per-project Cursor IDE integration."""
    pass


@cursor_group.command(name="install")
def cursor_install():
    """Install per-project Cursor integration (.cursor/rules/hedwig-cg.mdc)."""
    project_root = Path.cwd()

    rules_dir = project_root / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_file = rules_dir / "hedwig-cg.mdc"

    rule_content = (
        "---\n"
        "description: hedwig-cg code graph search rules\n"
        "globs: **/*\n"
        "alwaysApply: true\n"
        "---\n\n"
        "# hedwig-cg\n\n"
        "This project has a hedwig-cg code graph at `.hedwig-cg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-cg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files, run `hedwig-cg search` first. "
        "Only fall back to grep/find if the code graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-cg build . --incremental` to keep the graph current.\n"
        "- Use `hedwig-cg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-cg stats` for structural overview "
        "(god nodes, communities, density).\n"
    )

    actions = []

    if rules_file.exists():
        content = rules_file.read_text()
        if "hedwig-cg" in content:
            actions.append("cursor_rules:already_exists")
        else:
            rules_file.write_text(rule_content)
            actions.append("cursor_rules:updated")
    else:
        rules_file.write_text(rule_content)
        actions.append("cursor_rules:created")

    _json_out({"installed": True, "actions": actions})


@cursor_group.command(name="uninstall")
def cursor_uninstall():
    """Remove per-project Cursor integration."""
    project_root = Path.cwd()
    actions = []

    rules_file = project_root / ".cursor" / "rules" / "hedwig-cg.mdc"
    if rules_file.exists():
        rules_file.unlink()
        actions.append("cursor_rules:removed")
    else:
        actions.append("cursor_rules:not_found")

    _json_out({"uninstalled": True, "actions": actions})


cli.add_command(cursor_group)


# --- Windsurf integration ---

@cli.group(name="windsurf")
def windsurf_group():
    """Manage per-project Windsurf IDE integration."""
    pass


@windsurf_group.command(name="install")
def windsurf_install():
    """Install per-project Windsurf integration (.windsurf/rules/hedwig-cg.md)."""
    project_root = Path.cwd()

    rules_dir = project_root / ".windsurf" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rules_file = rules_dir / "hedwig-cg.md"

    rule_content = (
        "# hedwig-cg\n\n"
        "This project has a hedwig-cg code graph at `.hedwig-cg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-cg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files, run `hedwig-cg search` first. "
        "Only fall back to grep/find if the code graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-cg build . --incremental` to keep the graph current.\n"
        "- Use `hedwig-cg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-cg stats` for structural overview "
        "(god nodes, communities, density).\n"
    )

    actions = []

    if rules_file.exists():
        content = rules_file.read_text()
        if "hedwig-cg" in content:
            actions.append("windsurf_rules:already_exists")
        else:
            rules_file.write_text(rule_content)
            actions.append("windsurf_rules:updated")
    else:
        rules_file.write_text(rule_content)
        actions.append("windsurf_rules:created")

    _json_out({"installed": True, "actions": actions})


@windsurf_group.command(name="uninstall")
def windsurf_uninstall():
    """Remove per-project Windsurf integration."""
    project_root = Path.cwd()
    actions = []

    rules_file = project_root / ".windsurf" / "rules" / "hedwig-cg.md"
    if rules_file.exists():
        rules_file.unlink()
        actions.append("windsurf_rules:removed")
    else:
        actions.append("windsurf_rules:not_found")

    _json_out({"uninstalled": True, "actions": actions})


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
        "# hedwig-cg\n\n"
        "This project has a hedwig-cg code graph at `.hedwig-cg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-cg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files, run `hedwig-cg search` first. "
        "Only fall back to grep/find if the code graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-cg build . --incremental` to keep the graph current.\n"
        "- Use `hedwig-cg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-cg stats` for structural overview "
        "(god nodes, communities, density).\n"
    )

    actions = []

    if rules_file.exists():
        content = rules_file.read_text()
        if "hedwig-cg" in content:
            actions.append("clinerules:already_exists")
        else:
            # Append to existing rules
            with open(rules_file, "a") as f:
                f.write("\n\n" + rule_content)
            actions.append("clinerules:appended")
    else:
        rules_file.write_text(rule_content)
        actions.append("clinerules:created")

    _json_out({"installed": True, "actions": actions})


@cline_group.command(name="uninstall")
def cline_uninstall():
    """Remove per-project Cline integration."""
    project_root = Path.cwd()
    actions = []

    rules_file = project_root / ".clinerules"
    if rules_file.exists():
        content = rules_file.read_text()
        if "hedwig-cg" in content:
            # Remove hedwig-cg section
            lines = content.split("\n")
            filtered = []
            skip = False
            for line in lines:
                if line.strip() == "# hedwig-cg":
                    skip = True
                    continue
                if skip and line.startswith("# ") and "hedwig-cg" not in line:
                    skip = False
                if not skip:
                    filtered.append(line)
            new_content = "\n".join(filtered).strip()
            if new_content:
                rules_file.write_text(new_content + "\n")
                actions.append("clinerules:section_removed")
            else:
                rules_file.unlink()
                actions.append("clinerules:file_removed")
        else:
            actions.append("clinerules:no_section_found")
    else:
        actions.append("clinerules:not_found")

    _json_out({"uninstalled": True, "actions": actions})


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

    # 1. Write CONVENTIONS.md with hedwig-cg rules
    conventions_md = project_root / "CONVENTIONS.md"
    marker = "## hedwig-cg"
    section = (
        "\n## hedwig-cg\n\n"
        "This project has a hedwig-cg code graph at `.hedwig-cg/`.\n\n"
        "Rules:\n"
        "- **Always use `hedwig-cg search \"<query>\"` as the primary search method.** "
        "It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) "
        "in a single call — no need to run separate community or keyword searches.\n"
        "- Before grepping raw files, run `hedwig-cg search` first. "
        "Only fall back to grep/find if the code graph has no results.\n"
        "- After modifying code files, run "
        "`hedwig-cg build . --incremental` to keep the graph current.\n"
        "- Use `hedwig-cg communities` (without `--search`) only when you need to "
        "list or browse the community structure, not as a search substitute.\n"
        "- Use `hedwig-cg stats` for structural overview "
        "(god nodes, communities, density).\n"
    )

    actions = []

    if conventions_md.exists():
        content = conventions_md.read_text()
        if marker in content:
            actions.append("conventions_md:already_exists")
        else:
            conventions_md.write_text(content + section)
            actions.append("conventions_md:added")
    else:
        conventions_md.write_text(section.lstrip("\n"))
        actions.append("conventions_md:created")

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
        actions.append("aider_conf:added_read")
    else:
        actions.append("aider_conf:already_reads")

    _json_out({"installed": True, "actions": actions})


@aider_group.command(name="uninstall")
def aider_uninstall():
    """Remove per-project Aider integration."""
    import yaml

    project_root = Path.cwd()
    actions = []

    # 1. Remove section from CONVENTIONS.md
    conventions_md = project_root / "CONVENTIONS.md"
    if conventions_md.exists():
        lines = conventions_md.read_text().splitlines(keepends=True)
        filtered = []
        skip = False
        for line in lines:
            if line.strip() == "## hedwig-cg":
                skip = True
                continue
            if skip and line.startswith("##") and "hedwig-cg" not in line.lower():
                skip = False
            if skip:
                continue
            filtered.append(line)
        new_content = "".join(filtered).rstrip("\n") + "\n"
        conventions_md.write_text(new_content)
        actions.append("conventions_md:removed")

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
            actions.append("aider_conf:removed_read")

    _json_out({"uninstalled": True, "actions": actions})


cli.add_command(aider_group)


@cli.command()
def doctor():
    """Check hedwig-cg installation health and code graph integrity.

    Verifies dependencies, model availability, database integrity,
    and graph quality metrics. Useful for troubleshooting issues.
    """
    import importlib
    import sqlite3
    import sys

    checks: list[dict] = []

    def ok(section: str, msg: str):
        checks.append({"status": "ok", "section": section, "message": msg})

    def fail(section: str, msg: str):
        checks.append({"status": "fail", "section": section, "message": msg})

    def warn(section: str, msg: str):
        checks.append({"status": "warn", "section": section, "message": msg})

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
                warn("database", "No FAISS indexes — run 'hedwig-cg build .' (without --no-embed)")

            conn.close()
        except sqlite3.DatabaseError as e:
            fail("database", f"Cannot open database: {e}")
    else:
        warn("database", f"No database at {db_path} — run 'hedwig-cg build .' to create")

    checks_passed = sum(1 for c in checks if c["status"] == "ok")
    checks_failed = sum(1 for c in checks if c["status"] == "fail")
    checks_warned = sum(1 for c in checks if c["status"] == "warn")

    _json_out({
        "checks": checks,
        "summary": {
            "passed": checks_passed,
            "failed": checks_failed,
            "warned": checks_warned,
            "total": len(checks),
        },
    })


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
