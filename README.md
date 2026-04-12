<p align="center">
  <h1 align="center">hedwig-cg</h1>
  <p align="center">
    "Hedwig will be back with the word"
    <br />
    <a href="#quick-start">Quick Start</a> · <a href="#supported-languages">Languages</a> · <a href="#ai-agent-integrations">Integrations</a> · <a href="#architecture">Architecture</a> · <a href="docs/README_ko.md">한국어</a> · <a href="docs/README_ja.md">日本語</a> · <a href="docs/README_zh.md">中文</a> · <a href="docs/README_de.md">Deutsch</a>
  </p>
</p>

<p align="center">
  <a href="https://github.com/hedwig-ai/hedwig-code-graph/actions"><img src="https://img.shields.io/github/actions/workflow/status/hedwig-ai/hedwig-code-graph/ci.yml?branch=main" alt="CI"></a>
  <a href="https://pypi.org/project/hedwig-cg/"><img src="https://img.shields.io/pypi/v/hedwig-cg" alt="PyPI"></a>
  <a href="https://github.com/hedwig-ai/hedwig-code-graph/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hedwig-ai/hedwig-code-graph" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

## Why hedwig-cg?

hedwig-cg builds a unified code graph from your code, docs, and dependencies — built to handle enterprise codebases with 10,000+ files. 5-signal hybrid search (vector + graph + keyword + community → RRF fusion) lets coding agents truly understand your entire project, not just search keywords. Install it, and Claude Code sees the full picture — no extra tokens, no extra commands, everything runs 100% locally.

<img width="1919" height="991" alt="Code Graph" src="https://github.com/user-attachments/assets/a169c526-bb7c-4900-91dd-4db637793e32" />

## Quick Start

```bash
pip install hedwig-cg
hedwig-cg claude install
```

Then tell Claude Code:

> "Build a code graph for this project"

That's it. Claude Code will build the graph, and from then on, consult it before every search. When the code changes, just say:

> "Rebuild the code graph"

## Supported Languages

### Deep AST Extraction (17 languages)

hedwig-cg uses [tree-sitter tags.scm](https://tree-sitter.github.io/tree-sitter/4-code-navigation.html) for universal structural extraction — functions, classes, methods, calls, imports, inheritance — without per-language custom code.

| | | | |
|:---:|:---:|:---:|:---:|
| Python | JavaScript | TypeScript | Go |
| Rust | Java | C | C++ |
| C# | Ruby | Swift | Scala |
| Lua | PHP | Elixir | Kotlin |
| Objective-C | | | |

Additionally detects and indexes: Markdown, PDF, HTML, CSV, YAML, JSON, TOML, Shell, R, and more.

### Multilingual Natural Language

Text nodes (docs, comments, markdown) are embedded with `intfloat/multilingual-e5-small` supporting **100+ natural languages** — Korean, Japanese, Chinese, German, French, and more. Search in your language, find results in any language.

## AI Agent Integrations

hedwig-cg integrates with major AI coding agents in one command:

| Agent | Install | What it does |
|-------|---------|-------------|
| **Claude Code** | `hedwig-cg claude install` | Skill + CLAUDE.md + PreToolUse hook |
| **Codex CLI** | `hedwig-cg codex install` | AGENTS.md + PreToolUse hook |
| **Gemini CLI** | `hedwig-cg gemini install` | GEMINI.md + BeforeTool hook |
| **Cursor IDE** | `hedwig-cg cursor install` | `.cursor/rules/` rule file |
| **Windsurf IDE** | `hedwig-cg windsurf install` | `.windsurf/rules/` rule file |
| **Cline** | `hedwig-cg cline install` | `.clinerules` file |
| **Aider CLI** | `hedwig-cg aider install` | CONVENTIONS.md + `.aider.conf.yml` |
| **MCP Server** | `claude mcp add hedwig-cg -- hedwig-cg mcp` | 5 tools over Model Context Protocol |

Each `install` does two things: writes a context file with rules, and (where supported) registers a hook that fires before tool calls. To remove: `hedwig-cg <platform> uninstall`.

---

## Features

### Auto-Rebuild

When integrated with AI coding agents (Claude Code, Codex, etc.), hedwig-cg **automatically rebuilds** the graph when code changes. The Stop/SessionEnd hook detects modified files via `git diff` and triggers an incremental rebuild in the background — zero manual intervention.

### Smart Ignore

hedwig-cg respects ignore patterns from three sources, all using **full gitignore spec** (negation `!`, `**` globs, directory-only patterns):

| Source | Description |
|--------|-------------|
| Built-in | `.git`, `node_modules`, `__pycache__`, `dist`, `build`, etc. |
| `.gitignore` | Auto-read from project root — your existing git ignores just work |
| `.hedwig-cg-ignore` | Project-specific overrides for the code graph |

### Incremental Builds

SHA-256 content hashing per file. Only changed files are re-extracted and re-embedded. Unchanged files are merged from the existing graph — typically **95%+ faster** than a full rebuild.

### Memory Management

4GB memory budget with stage-wise release. The pipeline generates → stores → frees at each stage: extraction results are freed after graph build, embeddings are streamed in batches and freed after DB write, and the full graph is released after persistence. GC triggers proactively at 75% threshold.

### 100% Local

No cloud services, no API keys, no telemetry. SQLite + FAISS for storage, sentence-transformers for embeddings. All data stays on your machine.

---

## Architecture

```
Source Code/Docs
       |
       v
   Detect ──> Extract ──> Build ──> Embed ──> Cluster ──> Analyze ──> Store
              tags.scm    NetworkX   dual       Leiden      PageRank    SQLite
              (17 langs)  DiGraph    FAISS      hierarchy   god nodes   FTS5+FAISS
```

### 5-Signal Hybrid Search

Every search query runs through five independent retrieval signals, then fuses them into a single ranked result:

```
  Query: "authentication handler"
    |
    |-> 1. Code Vector (bge-small)  -> FAISS cosine similarity
    |-> 2. Text Vector (e5-small)   -> FAISS cosine similarity
    |-> 3. Graph Expansion          -> weighted BFS (2-hop neighbors)
    |-> 4. Full-Text Search (FTS5)  -> BM25 ranking
    |-> 5. Community Context        -> Leiden cluster summary match
    |
    +-> Weighted RRF Fusion -> Final ranked results
```

| Signal | Engine | What it finds |
|--------|--------|---------------|
| **Code Vector** | FAISS + `bge-small-en-v1.5` | Semantically similar code (functions, classes, methods) |
| **Text Vector** | FAISS + `multilingual-e5-small` | Docs, comments, markdown in 100+ languages |
| **Graph Expansion** | NetworkX weighted BFS | Structurally connected nodes (callers, callees, imports) |
| **Full-Text Search** | SQLite FTS5 + BM25 | Exact keyword matches across source code, no snippet limits |
| **Community Context** | Leiden clustering | Related nodes from the same functional cluster |
| **RRF Fusion** | Weighted Reciprocal Rank | Combines all signals — nodes found by multiple signals rank higher |

## CLI Reference

All commands output compact JSON by default (designed for AI agent consumption).

| Command | Description |
|---------|-------------|
| `build <dir>` | Build code graph (`--incremental`, `--no-embed`) |
| `search <query>` | 5-signal hybrid search (`--top-k`, `--fast`, `--expand`) |
| `query` | Interactive search REPL |
| `communities` | List and search communities (`--search`, `--level`) |
| `stats` | Graph statistics |
| `node <id>` | Node details with fuzzy matching |
| `export` | Export as JSON, GraphML, or D3.js |
| `visualize` | Interactive HTML visualization |
| `clean` | Remove .hedwig-cg/ database |
| `doctor` | Check installation health |
| `mcp` | Start MCP server (stdio) |

## Performance

Benchmarks on hedwig-cg's own codebase (~3,500 lines, 90 files, 1,300 nodes):

| Operation | Time |
|-----------|------|
| Full build | ~14s |
| Incremental (changes) | ~4s |
| Incremental (no changes) | ~0.4s |
| Cold search (dual model) | ~2.8s |
| Cold search (`--fast`) | ~0.2s |
| Warm search | ~0.08s |
| Cached search | <1ms |

- **Embedding models**: ~470MB, downloaded once to `~/.hedwig-cg/models/`
- **Database**: ~2MB (SQLite + FTS5 + FAISS indices)
- **Incremental builds**: SHA-256 hashing, 95%+ faster than full rebuild

## Requirements

- Python 3.10+
- ~470MB disk for embedding models (cached on first use)

```bash
# Optional: PDF extraction
pip install hedwig-cg[docs]
```

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check hedwig_cg/
```

## License

MIT License. See [LICENSE](LICENSE) for details.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.
