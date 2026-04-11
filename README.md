<p align="center">
  <h1 align="center">hedwig-kg</h1>
  <p align="center">
    Local-first knowledge graph builder for AI coding agents
    <br />
    <a href="#integration-with-ai-coding-agents">Integration</a> · <a href="#quick-start">Quick Start</a> · <a href="#architecture">Architecture</a> · <a href="docs/README_ko.md">한국어</a> · <a href="docs/README_ja.md">日本語</a>
  </p>
</p>

<p align="center">
  <a href="https://github.com/hedwig-ai/hedwig-knowledge-graph/actions"><img src="https://img.shields.io/github/actions/workflow/status/hedwig-ai/hedwig-knowledge-graph/ci.yml?branch=main" alt="CI"></a>
  <a href="https://pypi.org/project/hedwig-kg/"><img src="https://img.shields.io/pypi/v/hedwig-kg" alt="PyPI"></a>
  <a href="https://github.com/hedwig-ai/hedwig-knowledge-graph/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hedwig-ai/hedwig-knowledge-graph" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

<img width="1919" height="991" alt="Knowledge Graph" src="https://github.com/user-attachments/assets/a169c526-bb7c-4900-91dd-4db637793e32" />


**hedwig-kg** builds knowledge graphs from source code and documents, then provides **4-signal HybridRAG search** that fuses vector similarity, graph traversal, keyword matching, and community summaries. Everything runs **100% locally** — no cloud APIs, no data leaves your machine.

## Integration with AI Coding Agents

hedwig-kg integrates with major AI coding agents in one command. Each integration writes platform-specific context files and hooks so the agent automatically uses the knowledge graph before searching raw files.

```bash
pip install hedwig-kg
```

### Claude Code

```bash
hedwig-kg claude install
```

Writes `CLAUDE.md` section + `.claude/settings.json` PreToolUse hook. Claude Code will consult the knowledge graph before every Glob/Grep operation.

### OpenAI Codex CLI

```bash
hedwig-kg codex install
```

Writes `AGENTS.md` section + `.codex/hooks.json` PreToolUse hook. Codex CLI will see knowledge graph context before Bash tool calls.

### Google Gemini CLI

```bash
hedwig-kg gemini install
```

Writes `GEMINI.md` section + `.gemini/settings.json` BeforeTool hook. Gemini CLI will see knowledge graph context before file reads.

### How It Works

Each `install` command does two things:

1. **Context file** — Adds a `## hedwig-kg` section to the platform's context file (`CLAUDE.md`, `AGENTS.md`, or `GEMINI.md`) with rules for using the knowledge graph
2. **Hook** — Registers a lightweight shell hook that fires before tool calls, reminding the agent to use `hedwig-kg search` instead of grepping raw files

To remove: `hedwig-kg <platform> uninstall`

### Requirements

- Python 3.10+
- ~500MB disk space for the default embedding model (downloaded on first use)

### Optional Dependencies

```bash
# PDF text extraction
pip install hedwig-kg[docs]
```

## Quick Start

### 1. Install & Build

```bash
pip install hedwig-kg
cd ./my-project
hedwig-kg build .
```

First build scans all files, extracts AST structures, generates embeddings (~80MB model download on first run), detects communities, and stores everything in `.hedwig-kg/knowledge.db`.

### 2. Search

```bash
# 4-signal HybridRAG search (vector + graph + keyword + community)
hedwig-kg search "authentication handler"
```

### 3. Integrate with Your Agent

```bash
# Pick your platform
hedwig-kg claude install   # Claude Code
hedwig-kg codex install    # Codex CLI
hedwig-kg gemini install   # Gemini CLI
```

### 4. Keep It Updated

```bash
# Incremental rebuild — only re-processes changed files (fast)
hedwig-kg build . --incremental
```

### 5. Explore

```bash
hedwig-kg stats                           # Graph overview
hedwig-kg communities --search "auth"     # Community exploration
hedwig-kg node "AuthHandler"              # Node details
hedwig-kg query                           # Interactive REPL
hedwig-kg visualize                       # HTML visualization
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

### HybridRAG Search

1. **Vector Search** — Embed the query, find semantically similar nodes via FAISS
2. **Graph Expansion** — From top vector hits, traverse N-hop neighbors
3. **Keyword Search** — FTS5 full-text search with BM25 ranking
4. **Community Search** — Match query against community summaries, boost member nodes
5. **RRF Fusion** — Reciprocal Rank Fusion combines all signals into a unified ranking

## CLI Reference

| Command | Description |
|---------|-------------|
| `build <dir>` | Build knowledge graph (`--incremental`, `--no-embed`, `--model`) |
| `search <query>` | 4-signal HybridRAG search (`--top-k`, `--source-dir`) |
| `query` | Interactive search REPL |
| `communities` | List and search communities (`--search`, `--level`) |
| `stats` | Graph statistics (density, clustering, components) |
| `node <id>` | Node details with fuzzy matching |
| `export` | Export as JSON, GraphML, or D3.js |
| `visualize` | Interactive HTML visualization (`--max-nodes`, `--offline`) |
| `clean` | Remove .hedwig-kg/ database |
| `claude install` | Claude Code integration |
| `codex install` | Codex CLI integration |
| `gemini install` | Gemini CLI integration |

## Key Features

- **4-Signal HybridRAG Search** — Vector + Graph + Keyword + Community → RRF fusion
- **Tree-sitter AST Extraction** — Python, JavaScript, TypeScript with call graph analysis
- **Hierarchical Communities** — Multi-resolution Leiden clustering with auto-generated summaries
- **Incremental Builds** — SHA-256 content hashing skips unchanged files
- **100% Local** — SQLite + FTS5 + FAISS, no cloud APIs
- **20+ Languages** — File detection for Python, JS/TS, Java, Go, Rust, C/C++, Ruby, and more

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check hedwig_kg/
```

## License

MIT License. See [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
