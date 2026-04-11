<p align="center">
  <h1 align="center">hedwig-kg</h1>
  <p align="center">
    Local-first knowledge graph builder with hybrid vector + graph search
    <br />
    <a href="#installation">Installation</a> · <a href="#quick-start">Quick Start</a> · <a href="#architecture">Architecture</a> · <a href="docs/README_ko.md">한국어</a> · <a href="docs/README_ja.md">日本語</a>
  </p>
</p>

<p align="center">
  <a href="https://github.com/hedwig-ai/hedwig-knowledge-graph/actions"><img src="https://img.shields.io/github/actions/workflow/status/hedwig-ai/hedwig-knowledge-graph/ci.yml?branch=main" alt="CI"></a>
  <a href="https://pypi.org/project/hedwig-kg/"><img src="https://img.shields.io/pypi/v/hedwig-kg" alt="PyPI"></a>
  <a href="https://github.com/hedwig-ai/hedwig-knowledge-graph/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hedwig-ai/hedwig-knowledge-graph" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

## What is hedwig-kg?

**hedwig-kg** builds knowledge graphs from source code and documents, then provides **HybridRAG search** that fuses vector similarity, graph traversal, and full-text keyword matching. Everything runs **100% locally** — no cloud APIs, no data leaves your machine.

### Key Features

- **4-Signal HybridRAG Search** — Vector similarity → Graph N-hop expansion → FTS5 keyword matching → Community summary matching → RRF fusion
- **Tree-sitter AST Extraction** — Accurate structural parsing for Python, JavaScript, TypeScript with method→class attribution, inheritance tracking, and call graph analysis
- **Markdown Document Extraction** — Headings become section nodes with hierarchy, internal links become reference edges
- **Hierarchical Communities** — Multi-resolution Leiden clustering (0.25, 0.5, 1.0, 2.0) with auto-generated keyword-rich summaries
- **Incremental Builds** — SHA-256 content hashing skips unchanged files for fast rebuilds
- **Local Embeddings** — sentence-transformers for privacy-preserving semantic search
- **SQLite + FTS5 + FAISS** — Single-file database with full-text search and FAISS vector index
- **20+ Languages** — File detection and classification for Python, JS/TS, Java, Go, Rust, C/C++, Ruby, and more
- **CLI-First** — Simple commands for building, searching, and exploring knowledge graphs

## Installation

```bash
pip install hedwig-kg
```

Or install from source:

```bash
git clone https://github.com/hedwig-ai/hedwig-knowledge-graph.git
cd hedwig-knowledge-graph
pip install -e .
```

### Requirements

- Python 3.10+
- ~500MB disk space for the default embedding model (downloaded on first use)

## Quick Start

### Build a Knowledge Graph

```bash
# Analyze a project directory
hedwig-kg build ./my-project

# Incremental rebuild (skips unchanged files)
hedwig-kg build ./my-project --incremental

# Build without embeddings (faster, keyword-only search)
hedwig-kg build ./my-project --no-embed

# Use a custom embedding model
hedwig-kg build ./my-project --model all-MiniLM-L6-v2
```

### Search

```bash
# 4-signal HybridRAG search (vector + graph + keyword + community)
hedwig-kg search "authentication handler"

# Get more results
hedwig-kg search "database connection" --top-k 20
```

### Explore Communities

```bash
# List all detected communities with summaries
hedwig-kg communities

# Filter by hierarchy level (0=coarsest, higher=finer)
hedwig-kg communities --level 0

# Search communities by keyword
hedwig-kg communities --search "authentication"
```

### Interactive Exploration (REPL)

```bash
# Launch interactive query session (graph stays loaded for fast searches)
hedwig-kg query

# Inside the REPL:
#   Type any query to search
#   :node <id>   — show node details
#   :stats       — show graph statistics
#   :quit        — exit
```

### Explore Nodes

```bash
# View graph statistics (includes density, clustering, connected components)
hedwig-kg stats

# Inspect a specific node (supports fuzzy matching)
hedwig-kg node "AuthHandler"

# Export the full graph
hedwig-kg export --format json
hedwig-kg export --format graphml
hedwig-kg export --format d3       # D3.js compatible JSON

# Interactive visualization (opens in browser)
hedwig-kg visualize
hedwig-kg visualize --max-nodes 300 -o my_graph.html
hedwig-kg visualize --offline        # airgapped use (inlines D3.js)

# Clean up the database
hedwig-kg clean
hedwig-kg clean --yes              # skip confirmation
```

## Architecture

```
Source Code/Docs
       │
       ▼
   ┌───────┐     ┌─────────┐     ┌───────┐     ┌───────┐
   │Detect │────▶│ Extract │────▶│ Build │────▶│ Embed │
   └───────┘     └─────────┘     └───────┘     └───────┘
                  tree-sitter      NetworkX      sentence-
                  + markdown       DiGraph       transformers
       │
       ▼
   ┌─────────┐   ┌───────────┐   ┌─────────┐   ┌───────┐
   │ Cluster │──▶│ Summarize │──▶│ Analyze │──▶│ Store │
   └─────────┘   └───────────┘   └─────────┘   └───────┘
    Leiden         community       PageRank,     SQLite +
    hierarchy      summaries       god nodes     FTS5 + FAISS
```

### Pipeline Stages

| Stage | Description |
|-------|-------------|
| **Detect** | Scans directories, classifies 20+ languages, respects `.hedwig-kg-ignore` |
| **Extract** | Tree-sitter AST extraction for Python/JS/TS; markdown heading/section extraction; regex fallback for others |
| **Build** | Assembles directed graph with 3-phase node deduplication |
| **Embed** | Generates local embeddings via sentence-transformers |
| **Cluster** | Hierarchical Leiden community detection at multiple resolutions |
| **Summarize** | Auto-generates keyword-rich community summaries from node attributes |
| **Analyze** | Computes PageRank, detects god nodes, hub analysis |
| **Store** | Persists to SQLite with FTS5 full-text index and FAISS vector index |

### HybridRAG Search

hedwig-kg implements a four-signal fusion search:

1. **Vector Search** — Embed the query, find semantically similar nodes via FAISS
2. **Graph Expansion** — From top vector hits, traverse N-hop neighbors in the knowledge graph
3. **Keyword Search** — FTS5 full-text search with BM25 ranking
4. **Community Search** — Match query against community summaries, boost member nodes
5. **RRF Fusion** — Reciprocal Rank Fusion combines all four signals into a unified ranking

## CLI Reference

| Command | Description |
|---------|-------------|
| `build <dir>` | Build knowledge graph (`--incremental`, `--no-embed`, `--model`) |
| `search <query>` | 4-signal HybridRAG search (`--top-k`, `--source-dir`) |
| `query` | Interactive search REPL (`--top-k`, `:node`, `:stats`, `:quit`) |
| `communities` | List and search communities (`--search`, `--level`) |
| `stats` | Graph statistics with quality metrics (density, clustering) |
| `node <id>` | Node details with fuzzy matching |
| `export` | Export as JSON, GraphML, or D3.js format |
| `visualize` | Interactive HTML visualization (`--max-nodes`, `-o`, `--offline`) |
| `clean` | Remove .hedwig-kg/ database (`--yes` to skip confirm) |

### `hedwig-kg build`

```
Arguments:
  SOURCE_DIR              Path to the source directory

Options:
  -o, --output PATH       Output directory for the database
  --no-embed              Skip embedding generation
  --incremental           Skip unchanged files (faster rebuilds)
  --model TEXT            Sentence-transformers model name [default: all-MiniLM-L6-v2]
  --max-file-size INT     Max file size in bytes [default: 1000000]
```

### `hedwig-kg search`

```
Arguments:
  QUERY                   Natural language search query

Options:
  --db PATH               Path to knowledge.db
  --top-k INT             Number of results [default: 10]
  --source-dir PATH       Source directory to find default DB [default: .]
```

## Database

All data is stored in a single SQLite database at `<source_dir>/.hedwig-kg/knowledge.db`:

- **nodes** — Graph nodes with metadata (kind, file, line numbers, docstrings, snippets)
- **edges** — Relationships (defines, inherits, calls, imports) with confidence levels
- **communities** — Hierarchical community assignments
- **embeddings** — Node embedding vectors (binary blobs)
- **nodes_fts** — FTS5 virtual table for full-text search with BM25
- **metadata** — Build configuration and status

## Integration with AI Coding Tools

hedwig-kg integrates with Claude Code, OpenAI Codex CLI, and Google Gemini CLI.

```bash
# Claude Code — global /hedwig-kg slash command
hedwig-kg install

# Per-project integration (writes CLAUDE.md + PreToolUse hook)
hedwig-kg claude install

# OpenAI Codex CLI (writes AGENTS.md + .codex/hooks.json)
hedwig-kg codex install

# Google Gemini CLI (writes GEMINI.md + .gemini/settings.json)
hedwig-kg gemini install
```

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check hedwig_kg/
```

## License

MIT License. See [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
