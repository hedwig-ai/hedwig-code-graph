<p align="center">
  <h1 align="center">hedwig-kg</h1>
  <p align="center">
    Local-first knowledge graph builder for AI coding agents
    <br />
    <a href="#integration-with-ai-coding-agents">Integration</a> · <a href="#quick-start">Quick Start</a> · <a href="#architecture">Architecture</a> · <a href="docs/README_ko.md">한국어</a> · <a href="docs/README_ja.md">日本語</a> · <a href="docs/README_zh.md">中文</a> · <a href="docs/README_de.md">Deutsch</a>
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


**hedwig-kg** builds knowledge graphs from source code and documents, then provides **5-signal HybridRAG search** with dual embedding models (code-specialized + text-specialized) fused via RRF. Everything runs **100% locally** — no cloud APIs, no data leaves your machine.

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

### Cursor IDE

```bash
hedwig-kg cursor install
```

Creates `.cursor/rules/hedwig-kg.mdc` rule file. Cursor will automatically apply hedwig-kg search rules across your project.

### Windsurf IDE

```bash
hedwig-kg windsurf install
```

Creates `.windsurf/rules/hedwig-kg.md` rule file. Windsurf Cascade will automatically apply hedwig-kg search rules when working in your project.

### Cline (VS Code Extension)

```bash
hedwig-kg cline install
```

Creates `.clinerules` file with hedwig-kg search rules. Cline will automatically apply knowledge graph search when working in your project.

### Aider CLI

```bash
hedwig-kg aider install
```

Creates `CONVENTIONS.md` with hedwig-kg rules + adds it to `.aider.conf.yml` read list. Aider will automatically load knowledge graph conventions.

### MCP Server (Universal)

For any MCP-compatible agent, hedwig-kg also ships as an MCP server:

```bash
# Claude Code
claude mcp add hedwig-kg -- hedwig-kg mcp

# Cursor / VS Code (.cursor/mcp.json or .vscode/mcp.json)
{ "mcpServers": { "hedwig-kg": { "command": "hedwig-kg", "args": ["mcp"] } } }
```

This exposes 5 tools over the Model Context Protocol: `search`, `node`, `stats`, `communities`, `build`. Any MCP client can call them programmatically.

### How It Works

Each `install` command does two things:

1. **Context file** — Adds a `## hedwig-kg` section to the platform's context file (`CLAUDE.md`, `AGENTS.md`, `GEMINI.md`, `CONVENTIONS.md`) or rule file (`.cursor/rules/`, `.windsurf/rules/`) with rules for using the knowledge graph
2. **Hook** — For platforms that support it (Claude Code, Codex, Gemini), registers a lightweight shell hook that fires before tool calls, reminding the agent to use `hedwig-kg search` instead of grepping raw files

To remove: `hedwig-kg <platform> uninstall`

### Requirements

- Python 3.10+
- ~250MB disk space for dual embedding models (cached in `~/.hedwig-kg/models/` on first use)

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

First build scans all files, extracts AST structures, generates embeddings with dual models (~250MB download on first run, cached in `~/.hedwig-kg/models/`), detects communities, and stores everything in `.hedwig-kg/knowledge.db`.

### 2. Search

```bash
# 5-signal HybridRAG search (code vector + text vector + graph + keyword + community)
hedwig-kg search "authentication handler"

# Fast mode — text model only, 10× lower cold-start latency
hedwig-kg search "authentication handler" --fast
```

### 3. Integrate with Your Agent

```bash
# Pick your platform
hedwig-kg claude install     # Claude Code
hedwig-kg codex install      # Codex CLI
hedwig-kg gemini install     # Gemini CLI
hedwig-kg cursor install     # Cursor IDE
hedwig-kg windsurf install   # Windsurf IDE
hedwig-kg cline install      # Cline (VS Code)
hedwig-kg aider install      # Aider CLI
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

### HybridRAG Search (5 Signals)

```
  Query: "authentication handler"
    │
    ├─→ ① Code Vector (bge-small)  ─→ FAISS cosine  ─→  cv:0.019
    ├─→ ② Text Vector (MiniLM)     ─→ FAISS cosine  ─→  tv:0.018
    ├─→ ③ Graph Expansion           ─→ weighted BFS  ─→  g:0.012
    ├─→ ④ Keyword (FTS5)            ─→ BM25 ranking  ─→  kw:0.016
    ├─→ ⑤ Community                 ─→ summary match ─→  cm:0.008
    │
    └─→ Weighted RRF Fusion ──→ Final: 0.073 (with signal breakdown)
```

1. **Code Vector Search** — Query embedded with `BAAI/bge-small-en-v1.5`, searches code nodes via FAISS
2. **Text Vector Search** — Query embedded with `all-MiniLM-L6-v2`, searches document nodes via FAISS
3. **Graph Expansion** — Weight-aware BFS from top vector hits using edge quality (semantic similarity × confidence × relation type: `calls`=1.0, `imports`=0.7, `contains`=0.3)
4. **Keyword Search** — FTS5 full-text search with BM25 ranking and 80+ stopword filtering
5. **Community Search** — Match query against auto-generated community summaries, boost member nodes
6. **Weighted RRF Fusion** — Reciprocal Rank Fusion with per-signal weights (code=1.2×, text=1.2×, graph=0.8×, keyword=1.0×, community=0.6×) and **per-result signal breakdown** for full explainability

## CLI Reference

| Command | Description |
|---------|-------------|
| `build <dir>` | Build knowledge graph (`--incremental`, `--no-embed`, `--model`) |
| `search <query>` | 5-signal HybridRAG search (`--top-k`, `--fast`) |
| `query` | Interactive search REPL |
| `communities` | List and search communities (`--search`, `--level`) |
| `stats` | Graph statistics (density, clustering, components) |
| `node <id>` | Node details with fuzzy matching |
| `export` | Export as JSON, GraphML, or D3.js |
| `visualize` | Interactive HTML visualization (`--max-nodes`, `--offline`) |
| `clean` | Remove .hedwig-kg/ database |
| `mcp` | Start MCP server (stdio) — 5 tools for AI agents |
| `claude install` | Claude Code integration |
| `codex install` | Codex CLI integration |
| `gemini install` | Gemini CLI integration |
| `cursor install` | Cursor IDE integration |
| `windsurf install` | Windsurf IDE integration |
| `cline install` | Cline (VS Code) integration |
| `aider install` | Aider CLI integration |

## Key Features

- **5-Signal HybridRAG Search** — Dual vector (code + text) + Graph + Keyword + Community → Weighted RRF fusion with per-result signal breakdown
- **Dual Embedding Models** — Code nodes use `bge-small-en-v1.5`, text nodes use `all-MiniLM-L6-v2` (~220MB total, cached locally)
- **Tree-sitter AST Extraction** — Python, JavaScript, TypeScript with call graph tracking, class hierarchy, and decorator extraction
- **Weight-Aware Graph Expansion** — Edges scored by semantic similarity, confidence, proximity, and relation type (`calls`/`inherits` > `imports` > `contains`)
- **Search Explainability** — Each result shows which signals contributed (e.g. `cv:0.019 kw:0.016 g:0.012`)
- **Fast Search Mode** — `--fast` flag uses text model only for 10× lower cold-start latency
- **Line Number Navigation** — Results include `file.py:42-67` ranges for direct AI agent code navigation
- **Incremental Builds + Embedding** — SHA-256 hashing skips unchanged files; DB lookup skips unchanged embeddings (95% faster)
- **Hierarchical Communities** — Multi-resolution Leiden clustering with auto-generated keyword-rich summaries
- **MCP Server** — Universal AI agent integration via Model Context Protocol (5 tools over stdio)
- **8 AI Agent Integrations** — Claude Code, Codex CLI, Gemini CLI, Cursor IDE, Windsurf IDE, Cline, Aider CLI + MCP server
- **100% Local** — SQLite + FTS5 + FAISS, no cloud APIs, no data leaves your machine
- **20+ Languages** — File detection for Python, JS/TS, Java, Go, Rust, C/C++, Ruby, and more

## Performance

Benchmarks measured on hedwig-kg itself (~3,000 lines, 85 files, 976 nodes):

| Operation | Time | Notes |
|-----------|------|-------|
| Full build | ~9.5s | Detect + extract + embed + cluster + store |
| Incremental build (changes) | ~4s | Re-embeds only changed-file nodes |
| Incremental build (no changes) | ~0.4s | All embeddings reused from DB |
| Cold search (dual model) | ~2.8s | Both models loaded + 5-signal fusion |
| Cold search (`--fast`) | ~0.2s | Text model only, code index cross-searched |
| Warm search (new query) | ~0.08s | Models cached, encode + FAISS + fusion |
| Cached search (same query) | <1ms | LRU cache hit |
| FAISS search only | ~0.03s | Pure vector similarity (post-model-load) |
| Embedding models | ~220MB | Downloaded once, cached in `~/.hedwig-kg/models/` |
| Database size | ~1.5MB | SQLite + FTS5 + FAISS indices |

### Optimizations

- **Incremental embedding** — SHA-256 hash + DB embedding lookup skips unchanged nodes (95% faster rebuilds)
- **Fast search mode** — `--fast` skips code model loading, cross-searches with text vectors only
- **REPL model preloading** — Background thread loads models while you type your first query
- **FAISS mmap loading** — Vector indices loaded via `IO_FLAG_MMAP` for lower RSS and faster cold starts
- **Per-stage timing** — Build shows wall-clock breakdown per stage to identify bottlenecks
- **Query embedding LRU cache** — 256-entry cache eliminates re-encoding for repeated queries
- **Search result LRU cache** — 128-entry cache for instant repeated search results
- **Memory-bounded embedding** — 2GB RSS budget with streaming batches and automatic GC
- **Decorator-enriched embeddings** — Python decorators (`@dataclass`, `@route`) included in embedding text
- **Metadata-enriched embeddings** — File paths, parent class context, signatures, and line numbers in embedding text
- **Weight-aware graph traversal** — Edge weights (semantic similarity × confidence × relation type) guide expansion

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
