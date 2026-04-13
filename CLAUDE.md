# hedwig-cg — Local-First Code Graph Builder

## Project Overview
hedwig-cg analyzes source code and documents to build code graphs, providing 5-signal HybridRAG search with dual embedding models (code + text) fused via RRF. Everything runs locally — no cloud services required.

## Quick Start
```bash
# Install
pip install -e .

# Build code graph from a directory
hedwig-cg build ./my-project

# Incremental rebuild (skips unchanged files)
hedwig-cg build ./my-project --incremental

# Search the code graph (5-signal HybridRAG)
hedwig-cg search "authentication handler"
hedwig-cg search "authentication handler" --fast  # text model only, lower latency

# Explore communities
hedwig-cg communities
hedwig-cg communities --search "auth"

# View statistics
hedwig-cg stats

# Show node details
hedwig-cg node "node_id_or_partial_match"

# Export graph
hedwig-cg export --format json
hedwig-cg export --format d3    # D3.js compatible JSON

# Interactive visualization
hedwig-cg visualize
hedwig-cg visualize --max-nodes 300 -o my_graph.html
```

## Architecture
```
detect → extract → build → embed → cluster → summarize → analyze → store
```

- **detect**: Scans directories, classifies files (20+ languages), respects .hedwig-cg-ignore
- **extract**: Tree-sitter AST extraction (Python, JS/TS) with regex fallback; markdown heading/section extraction
- **build**: Assembles NetworkX DiGraph with 3-phase deduplication
- **embed**: dual-model embeddings (code: BAAI/bge-small-en-v1.5, text: all-MiniLM-L6-v2, cached in ~/.hedwig-cg/models/)
- **cluster**: Hierarchical Leiden community detection (multi-resolution)
- **summarize**: Auto-generates keyword-rich community summaries from node attributes
- **analyze**: God nodes, hub detection, surprising connections, quality metrics
- **store**: SQLite + FTS5 full-text search + FAISS vector index, all local

## CLI Commands
| Command | Description |
|---------|-------------|
| `hedwig-cg build <dir>` | Build code graph (`--incremental`) |
| `hedwig-cg search <query>` | Two-Stage 5-signal HybridRAG (code vector + text vector + graph + keyword + community → RRF → reranking) (`--fast` for text-only) |
| `hedwig-cg communities` | List/search communities (`--search`, `--level`) |
| `hedwig-cg stats` | Show graph statistics |
| `hedwig-cg node <id>` | Show node details and connections |
| `hedwig-cg export` | Export as JSON, GraphML, or D3.js format |
| `hedwig-cg visualize` | Interactive HTML graph visualization (`--max-nodes`) |
| `hedwig-cg query` | Interactive search REPL (`--top-k`, `:node`, `:stats`, `:quit`) |
| `hedwig-cg clean` | Remove .hedwig-cg/ database directory (`--yes` to skip confirm) |
| `hedwig-cg doctor` | Check installation health, dependencies, DB integrity, and model availability |
| `hedwig-cg mcp` | Start MCP server (stdio) — exposes search, node, stats, communities, build tools |

## Key Design Decisions
- **100% local**: No cloud services. SQLite + FAISS for storage, sentence-transformers for embeddings
- **5-signal HybridRAG**: Code vector + Text vector → Graph N-hop → FTS5 keyword → Community summary → RRF fusion
- **Dual embedding models**: Code nodes (bge-small-en-v1.5) + Text nodes (all-MiniLM-L6-v2 or multilingual-e5-small), both 384-dim, cached in ~/.hedwig-cg/models/
- **Multilingual support**: `--lang auto|en|multilingual` — auto-detects non-English text nodes via Unicode script analysis, switches text model to `intfloat/multilingual-e5-small` (100+ languages). Code model stays English-optimized.
- **Tree-sitter AST**: Accurate structural extraction with method→class attribution, inheritance, call tracking
- **Markdown extraction**: Headings → section nodes with hierarchy, internal links → reference edges
- **Hierarchical communities**: Multi-resolution Leiden (0.25, 0.5, 1.0, 2.0) with auto-generated summaries
- **Incremental builds**: SHA-256 content hashing to skip unchanged files
- **Privacy-first**: No data leaves the machine
- **No manual curation features**: Do NOT add features that require users to manually create/maintain configuration files (e.g. synonym dictionaries, term mappings, custom ontologies). All search quality improvements must be algorithmic and automatic. Manual curation doesn't scale and creates maintenance burden.

## Database
Default location: `<source_dir>/.hedwig-cg/knowledge.db` (SQLite with FTS5)

## Dependencies
- networkx, sentence-transformers, faiss-cpu, leidenalg, igraph
- click, rich (CLI)
- tree-sitter, tree-sitter-python, tree-sitter-javascript (AST extraction)

## AI Agent Interface Design Principle
- **Minimal interface**: Keep the number of tools/commands exposed to AI agents small. Too many options cause hallucination or wrong tool selection.
- **MCP tools priority**: `search` → `node` → `build` → `stats`. The `communities` tool is rarely needed since search already includes community signals.
- **CLI for humans, MCP for agents**: The CLI has 18+ commands for human users; the MCP server exposes only 5 focused tools for AI agents.
- **Clear docstrings**: Each MCP tool docstring explicitly states when to use (and when NOT to use) that tool.

## hedwig-cg

This project has a hedwig-cg code graph at `.hedwig-cg/`.

hedwig-cg is a **map builder**, not an answer engine. It tells you **what the codebase looks like** and **what to read next**. Use it as the starting point of every investigation, then drill deeper with Read and Grep.

Workflow: `hedwig-cg search` (discover files) → `Read` (understand architecture) → `Grep` (find specific symbols)

Rules:
- **Always start with `hedwig-cg search "<query>"` to get the big picture.** It runs Two-Stage 5-signal HybridRAG in a single call.
- **Always query in English.** Non-English queries have significantly lower precision.
- **hedwig-cg finds what to read; Read/Grep finds the details.** Don't expect it to surface specific type definitions, constants, or function signatures — use Grep for those.
- **Don't stop at first results.** Drill into discovered terms for deeper understanding across services.
- After modifying code files, run `hedwig-cg build . --incremental` to keep the graph current.
- Use `hedwig-cg communities` (without `--search`) only when you need to list or browse the community structure, not as a search substitute.
- Use `hedwig-cg stats` for structural overview (god nodes, communities, density).
