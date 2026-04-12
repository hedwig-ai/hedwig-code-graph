# hedwig-cg — Code Graph Builder with LLM Semantic Enrichment

## Project Overview
hedwig-cg analyzes source code and documents to build code graphs, providing 5-signal HybridRAG search with dual embedding models (code + text) fused via RRF. AST structural extraction captures explicit relationships; LLM semantic enrichment discovers hidden cross-module connections automatically when built inside an AI coding agent.

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
detect → extract → build → [semantic] → embed → cluster → summarize → analyze → store
                            LLM enrichment (agent analyzes nodes, injects INFERRED edges)
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
| `hedwig-cg build <dir>` | Build code graph (`--incremental`, `--no-embed`, `--lang auto\|en\|multilingual`) |
| `hedwig-cg search <query>` | 5-signal HybridRAG (code vector + text vector + graph + keyword + community) (`--fast` for text-only) |
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
- **LLM semantic enrichment**: AI coding agent analyzes node batches in parallel, injecting INFERRED edges (design patterns, behavioral deps, cross-module relationships) that AST cannot detect. No separate API key — uses the agent's own LLM context
- **5-signal HybridRAG**: Code vector + Text vector → Graph N-hop → FTS5 keyword → Community summary → RRF fusion
- **Dual embedding models**: Code nodes (bge-small-en-v1.5) + Text nodes (all-MiniLM-L6-v2 or multilingual-e5-small), both 384-dim, cached in ~/.hedwig-cg/models/
- **Multilingual support**: `--lang auto|en|multilingual` — auto-detects non-English text nodes via Unicode script analysis, switches text model to `intfloat/multilingual-e5-small` (100+ languages). Code model stays English-optimized.
- **Tree-sitter AST**: Accurate structural extraction with method→class attribution, inheritance, call tracking
- **Markdown extraction**: Headings → section nodes with hierarchy, internal links → reference edges
- **Hierarchical communities**: Multi-resolution Leiden (0.25, 0.5, 1.0, 2.0) with auto-generated summaries
- **Incremental builds**: SHA-256 content hashing to skip unchanged files
- **Privacy-aware**: Graph data stored locally in SQLite + FAISS. Semantic enrichment sends only node summaries (names, signatures, snippets) to the agent's LLM
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

Rules:
- **Always use `hedwig-cg --json search "<query>"` as the primary search method.** It runs 5-signal HybridRAG (vector + graph + keyword + community → RRF fusion) in a single call — no need to run separate community or keyword searches.
- Before grepping raw files with Glob/Grep, run `hedwig-cg --json search` first. Only fall back to Grep if the code graph has no results.
- After modifying code files, run `hedwig-cg build . --incremental` to keep the graph current
- Use `hedwig-cg communities` (without `--search`) only when you need to list or browse the community structure, not as a search substitute.
- Use `hedwig-cg stats` for structural overview (god nodes, communities, density)
