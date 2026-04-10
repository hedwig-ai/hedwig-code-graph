# hedwig-kg — Local-First Knowledge Graph Builder

## Project Overview
hedwig-kg analyzes source code and documents to build knowledge graphs, providing HybridRAG search that combines vector similarity, graph traversal, and keyword matching via RRF fusion. Everything runs locally — no cloud services required.

## Quick Start
```bash
# Install
pip install -e .

# Build knowledge graph from a directory
hedwig-kg build ./my-project

# Incremental rebuild (skips unchanged files)
hedwig-kg build ./my-project --incremental

# Search the knowledge graph (4-signal HybridRAG)
hedwig-kg search "authentication handler"

# Explore communities
hedwig-kg communities
hedwig-kg communities --search "auth"

# View statistics
hedwig-kg stats

# Show node details
hedwig-kg node "node_id_or_partial_match"

# Export graph
hedwig-kg export --format json
hedwig-kg export --format d3    # D3.js compatible JSON

# Interactive visualization
hedwig-kg visualize
hedwig-kg visualize --max-nodes 300 -o my_graph.html
```

## Architecture
```
detect → extract → build → embed → cluster → summarize → analyze → store
```

- **detect**: Scans directories, classifies files (20+ languages), respects .hedwig-kg-ignore
- **extract**: Tree-sitter AST extraction (Python, JS/TS) with regex fallback; markdown heading/section extraction
- **build**: Assembles NetworkX DiGraph with 3-phase deduplication
- **embed**: sentence-transformers local embeddings (all-MiniLM-L6-v2)
- **cluster**: Hierarchical Leiden community detection (multi-resolution)
- **summarize**: Auto-generates keyword-rich community summaries from node attributes
- **analyze**: God nodes, hub detection, surprising connections, quality metrics
- **store**: SQLite + FTS5 full-text search + FAISS vector index, all local

## CLI Commands
| Command | Description |
|---------|-------------|
| `hedwig-kg build <dir>` | Build knowledge graph (`--incremental`, `--no-embed`) |
| `hedwig-kg search <query>` | 4-signal HybridRAG (vector + graph + keyword + community) |
| `hedwig-kg communities` | List/search communities (`--search`, `--level`) |
| `hedwig-kg stats` | Show graph statistics |
| `hedwig-kg node <id>` | Show node details and connections |
| `hedwig-kg export` | Export as JSON, GraphML, or D3.js format |
| `hedwig-kg visualize` | Interactive HTML graph visualization (`--max-nodes`) |
| `hedwig-kg query` | Interactive search REPL (`--top-k`, `:node`, `:stats`, `:quit`) |
| `hedwig-kg clean` | Remove .hedwig-kg/ database directory (`--yes` to skip confirm) |

## Key Design Decisions
- **100% local**: No cloud services. SQLite + FAISS for storage, sentence-transformers for embeddings
- **4-signal HybridRAG**: Vector → Graph N-hop → FTS5 keyword → Community summary → RRF fusion
- **Tree-sitter AST**: Accurate structural extraction with method→class attribution, inheritance, call tracking
- **Markdown extraction**: Headings → section nodes with hierarchy, internal links → reference edges
- **Hierarchical communities**: Multi-resolution Leiden (0.25, 0.5, 1.0, 2.0) with auto-generated summaries
- **Incremental builds**: SHA-256 content hashing to skip unchanged files
- **Privacy-first**: No data leaves the machine

## Database
Default location: `<source_dir>/.hedwig-kg/knowledge.db` (SQLite with FTS5)

## Dependencies
- networkx, sentence-transformers, faiss-cpu, leidenalg, igraph
- click, rich (CLI)
- tree-sitter, tree-sitter-python, tree-sitter-javascript (AST extraction)
