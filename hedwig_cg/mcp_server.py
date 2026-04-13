"""hedwig-cg MCP Server — exposes code graph tools to AI agents.

Provides 5 tools over the Model Context Protocol (MCP):
- search: 5-signal HybridRAG search
- node: Get detailed node information
- stats: Graph statistics overview
- communities: List or search communities
- build: Trigger incremental graph rebuild

Usage:
    # stdio transport (default for Claude Code / Cursor / Windsurf)
    hedwig-cg mcp

    # Or directly:
    python -m hedwig_cg.mcp_server
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from hedwig_cg.cli._helpers import suppress_library_logs

suppress_library_logs()

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "hedwig-cg",
    instructions=(
        "Local-first code graph for code and document search. "
        "START with 'search' — it is the primary tool and handles most queries. "
        "Only use 'node' when you need full details about a specific entity "
        "found in search results. Use 'stats' for a structural overview. "
        "Use 'build' after code changes to update the graph. "
        "Avoid calling 'communities' directly — search already includes "
        "community signals in its ranking."
    ),
)

# ---------------------------------------------------------------------------
# Lazy-loaded shared state
# ---------------------------------------------------------------------------
_store = None
_graph = None
_db_path: str | None = None


def _get_db_path() -> str:
    """Resolve the code graph database path."""
    global _db_path
    if _db_path:
        return _db_path
    # Check environment variable first, then fall back to cwd
    env_path = os.environ.get("HEDWIG_CG_DB")
    if env_path and Path(env_path).exists():
        _db_path = env_path
        return _db_path
    # Walk up from cwd looking for .hedwig-cg/knowledge.db
    cwd = Path.cwd()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".hedwig-cg" / "knowledge.db"
        if candidate.exists():
            _db_path = str(candidate)
            return _db_path
    # Default to cwd
    _db_path = str(cwd / ".hedwig-cg" / "knowledge.db")
    return _db_path


def _load():
    """Lazy-load store and graph."""
    global _store, _graph
    if _store is not None and _graph is not None:
        return _store, _graph
    from hedwig_cg.storage.store import KnowledgeStore

    db = _get_db_path()
    if not Path(db).exists():
        raise FileNotFoundError(
            f"Code graph not found at {db}. "
            "Run 'hedwig-cg build <dir>' first."
        )
    _store = KnowledgeStore(db)
    _graph = _store.load_graph()
    n, e = _graph.number_of_nodes(), _graph.number_of_edges()
    logger.info("Loaded graph: %d nodes, %d edges", n, e)
    return _store, _graph


def _reload():
    """Force reload after a build."""
    global _store, _graph
    _store = None
    _graph = None
    return _load()


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def search(query: str, top_k: int = 10, fast: bool = False) -> str:
    """Search the code graph. This is the PRIMARY tool — use it first.

    Finds functions, classes, modules, and documents by combining semantic
    vector search, keyword matching, graph structure, and community context.

    Args:
        query: What to search for (e.g. "authentication handler",
               "database connection pool", "how does build work")
        top_k: Number of results (default 10)
        fast: Use text model only for faster response (default False)
    """
    store, G = _load()
    from hedwig_cg.query.hybrid import extract_result_edges, hybrid_search

    results = hybrid_search(query, store, G, top_k=top_k, fast=fast)
    if not results:
        return f"No results found for '{query}'."

    lines = [f"## Search: '{query}' ({len(results)} results)\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"### {i}. {r.label} ({r.kind})")
        loc = r.file_path
        if r.start_line:
            loc += f":{r.start_line}"
            if r.end_line and r.end_line != r.start_line:
                loc += f"-{r.end_line}"
        lines.append(f"- **File**: {loc}")
        lines.append(f"- **Score**: {r.score:.4f}")
        if r.signal_contributions:
            sigs = ", ".join(
                f"{k}={v:.3f}" for k, v in
                sorted(r.signal_contributions.items(), key=lambda x: -x[1]) if v > 0
            )
            lines.append(f"- **Signals**: {sigs}")
        if r.neighbors:
            lines.append(f"- **Neighbors**: {', '.join(r.neighbors[:5])}")
        if getattr(r, "signature", ""):
            lines.append(f"- **Signature**: `{r.signature}`")
        if getattr(r, "docstring", ""):
            lines.append(f"- **Docstring**: {r.docstring}")
        lines.append("")

    # Add relationship edges between result nodes
    edges = extract_result_edges(G, results)
    if edges:
        lines.append("## Relationships\n")
        for e in edges:
            lines.append(f"- {e['from']} --{e['rel']}--> {e['to']}")
        lines.append("")

    return "\n".join(lines)


@mcp.tool()
def node(node_id: str) -> str:
    """Get detailed information about a specific node in the code graph.

    Args:
        node_id: Full or partial node ID. Partial matches are supported
                 (e.g. "KnowledgeStore" will match the full node ID).
    """
    store, G = _load()

    # Try exact match first
    if node_id in G.nodes:
        matches = [node_id]
    else:
        # Partial match
        matches = [n for n in G.nodes if node_id.lower() in n.lower()]

    if not matches:
        return f"No node found matching '{node_id}'."

    lines = []
    for nid in matches[:5]:  # Limit to 5 matches
        data = G.nodes[nid]
        lines.append(f"## {data.get('label', nid)}")
        lines.append(f"- **ID**: {nid}")
        lines.append(f"- **Kind**: {data.get('kind', 'unknown')}")
        lines.append(f"- **File**: {data.get('file_path', 'N/A')}")
        if data.get("signature"):
            lines.append(f"- **Signature**: `{data['signature']}`")
        if data.get("docstring"):
            lines.append(f"- **Docstring**: {data['docstring'][:300]}")
        if data.get("start_line"):
            lines.append(f"- **Lines**: {data.get('start_line')}-{data.get('end_line', '?')}")

        # Edges
        out_edges = list(G.out_edges(nid, data=True))[:10]
        in_edges = list(G.in_edges(nid, data=True))[:10]
        if out_edges:
            lines.append("- **Outgoing edges**:")
            for _, target, edata in out_edges:
                tlabel = G.nodes.get(target, {}).get("label", target.split("::")[-1])
                rel = edata.get('relation', '?')
                w = edata.get('weight', 0)
                lines.append(f"  - → {tlabel} ({rel}, w={w:.2f})")
        if in_edges:
            lines.append("- **Incoming edges**:")
            for source, _, edata in in_edges:
                slabel = G.nodes.get(source, {}).get("label", source.split("::")[-1])
                rel = edata.get('relation', '?')
                w = edata.get('weight', 0)
                lines.append(f"  - ← {slabel} ({rel}, w={w:.2f})")
        lines.append("")
    return "\n".join(lines)


@mcp.tool()
def stats() -> str:
    """Get code graph statistics.

    Returns node/edge counts, communities, and quality metrics.
    """
    store, G = _load()
    from hedwig_cg.core.analyze import analyze as analyze_graph

    n_nodes = G.number_of_nodes()
    n_edges = G.number_of_edges()

    # Node kind distribution
    kinds: dict[str, int] = {}
    for _, data in G.nodes(data=True):
        k = data.get("kind", "unknown")
        kinds[k] = kinds.get(k, 0) + 1

    # Community count
    community_ids: set[int] = set()
    for _, data in G.nodes(data=True):
        for cid in data.get("community_ids", []):
            community_ids.add(cid)

    # God nodes (high degree + pagerank)
    analysis = analyze_graph(G, top_k=10)
    god_nodes = analysis.god_nodes

    lines = [
        "## Code Graph Statistics\n",
        f"- **Nodes**: {n_nodes}",
        f"- **Edges**: {n_edges}",
        f"- **Communities**: {len(community_ids)}",
        f"- **Density**: {n_edges / max(n_nodes * (n_nodes - 1), 1):.6f}",
        "",
        "### Node Kinds",
    ]
    for kind, count in sorted(kinds.items(), key=lambda x: -x[1]):
        lines.append(f"- {kind}: {count}")

    if god_nodes:
        lines.append("\n### God Nodes (high fan-out)")
        for gn in god_nodes[:10]:
            lines.append(f"- {gn['label']} ({gn['kind']}): {gn['degree']} connections")

    lines.append(f"\n- **Database**: {_get_db_path()}")
    return "\n".join(lines)


@mcp.tool()
def communities(search_query: str = "", level: int = -1) -> str:
    """Browse community clusters (rarely needed — use 'search' instead).

    Communities group related code entities by topic. The 'search' tool
    already factors community signals into ranking, so only use this
    when you need to explore the community structure itself.

    Args:
        search_query: Filter communities by keyword (leave empty to list all).
        level: Hierarchy level (-1 for all levels).
    """
    store, G = _load()

    if search_query:
        terms = search_query.lower().split()
        results = store.community_search(terms, top_k=10)
        if not results:
            return f"No communities found matching '{search_query}'."

        lines = [f"## Communities matching '{search_query}'\n"]
        for comm in results:
            cid = comm.get("community_id", comm.get("id", "?"))
            lines.append(f"### Community {cid} (level {comm.get('level', '?')})")
            lines.append(f"- **Score**: {comm['score']:.2f}")
            lines.append(f"- **Nodes**: {len(comm.get('node_ids', []))}")
            if comm.get("summary"):
                lines.append(f"- **Summary**: {comm['summary'][:200]}")
            if comm.get("node_ids"):
                sample = comm["node_ids"][:5]
                labels = [G.nodes.get(n, {}).get("label", n) for n in sample]
                lines.append(f"- **Sample members**: {', '.join(labels)}")
            lines.append("")
        return "\n".join(lines)
    else:
        # List all communities directly from SQLite
        query = "SELECT id, level, summary FROM communities"
        params: list = []
        if level >= 0:
            query += " WHERE level = ?"
            params.append(level)
        query += " ORDER BY level, id"
        rows = store.conn.execute(query, params).fetchall()
        if not rows:
            return "No communities found."

        lines = [f"## All Communities ({len(rows)} total)\n"]
        for row in rows[:20]:
            # Count members
            cnt = store.conn.execute(
                "SELECT COUNT(*) as c FROM community_members WHERE community_id = ?",
                (row["id"],),
            ).fetchone()["c"]
            summary = (row["summary"] or "No summary")[:100]
            lines.append(f"- **Community {row['id']}** (level {row['level']}): "
                         f"{cnt} nodes — {summary}")
        if len(rows) > 20:
            lines.append(f"\n... and {len(rows) - 20} more. Use search_query to filter.")
        return "\n".join(lines)


@mcp.tool()
def build(directory: str = ".", incremental: bool = True) -> str:
    """Build or rebuild the code graph from source code.

    Args:
        directory: Directory to analyze (default: current directory).
        incremental: If true, only re-process changed files (default: true).
    """
    from hedwig_cg.core.pipeline import run_pipeline

    target = Path(directory).resolve()
    if not target.is_dir():
        return f"Error: '{directory}' is not a valid directory."

    result = run_pipeline(str(target), incremental=incremental)

    nodes = getattr(result, "node_count", 0) or (
        result.graph.number_of_nodes() if getattr(result, "graph", None) else 0
    )
    edges = getattr(result, "edge_count", 0) or (
        result.graph.number_of_edges() if getattr(result, "graph", None) else 0
    )
    files = len(result.detect_result.files) if getattr(result, "detect_result", None) else 0

    # Free large in-memory objects after DB persistence
    if hasattr(result, "release_memory"):
        result.release_memory()

    # Force reload after build
    _reload()

    return (
        f"## Build Complete\n\n"
        f"- **Directory**: {target}\n"
        f"- **Mode**: {'incremental' if incremental else 'full'}\n"
        f"- **Nodes**: {nodes}\n"
        f"- **Edges**: {edges}\n"
        f"- **Files detected**: {files}\n"
        f"- **Database**: {_get_db_path()}\n"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Run the MCP server with stdio transport."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
