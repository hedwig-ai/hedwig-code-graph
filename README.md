<p align="center">
  <h1 align="center">hedwig-kg</h1>
  <p align="center">
    "Hedwig will be back with the word"
    <br />
    <a href="#quick-start">Quick Start</a> · <a href="#supported-languages">Languages</a> · <a href="#ai-agent-integrations">Integrations</a> · <a href="#architecture">Architecture</a> · <a href="docs/README_ko.md">한국어</a> · <a href="docs/README_ja.md">日本語</a> · <a href="docs/README_zh.md">中文</a> · <a href="docs/README_de.md">Deutsch</a>
  </p>
</p>

<p align="center">
  <a href="https://github.com/hedwig-ai/hedwig-knowledge-graph/actions"><img src="https://img.shields.io/github/actions/workflow/status/hedwig-ai/hedwig-knowledge-graph/ci.yml?branch=main" alt="CI"></a>
  <a href="https://pypi.org/project/hedwig-kg/"><img src="https://img.shields.io/pypi/v/hedwig-kg" alt="PyPI"></a>
  <a href="https://github.com/hedwig-ai/hedwig-knowledge-graph/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hedwig-ai/hedwig-knowledge-graph" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

## Why hedwig-kg?

hedwig-kg builds a unified knowledge graph from your code, docs, and dependencies — so coding agents can truly understand your entire project, not just search keywords. Install it, and Claude Code sees the full picture — no extra tokens, no extra commands, everything runs 100% locally.

<img width="1919" height="991" alt="Knowledge Graph" src="https://github.com/user-attachments/assets/a169c526-bb7c-4900-91dd-4db637793e32" />

## Quick Start

```bash
pip install hedwig-kg
hedwig-kg claude install
```

Then tell Claude Code:

> "Build a knowledge graph for this project"

That's it. Claude Code will build the graph, and from then on, consult it before every search. When the code changes, just say:

> "Rebuild the knowledge graph"

## Supported Languages

### Deep AST Extraction (17 languages)

hedwig-kg uses [tree-sitter tags.scm](https://tree-sitter.github.io/tree-sitter/4-code-navigation.html) for universal structural extraction — functions, classes, methods, calls, imports, inheritance — without per-language custom code.

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

hedwig-kg integrates with major AI coding agents in one command:

| Agent | Install | What it does |
|-------|---------|-------------|
| **Claude Code** | `hedwig-kg claude install` | Skill + CLAUDE.md + PreToolUse hook |
| **Codex CLI** | `hedwig-kg codex install` | AGENTS.md + PreToolUse hook |
| **Gemini CLI** | `hedwig-kg gemini install` | GEMINI.md + BeforeTool hook |
| **Cursor IDE** | `hedwig-kg cursor install` | `.cursor/rules/` rule file |
| **Windsurf IDE** | `hedwig-kg windsurf install` | `.windsurf/rules/` rule file |
| **Cline** | `hedwig-kg cline install` | `.clinerules` file |
| **Aider CLI** | `hedwig-kg aider install` | CONVENTIONS.md + `.aider.conf.yml` |
| **MCP Server** | `claude mcp add hedwig-kg -- hedwig-kg mcp` | 5 tools over Model Context Protocol |

Each `install` does two things: writes a context file with rules, and (where supported) registers a hook that fires before tool calls. To remove: `hedwig-kg <platform> uninstall`.

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

### Hybrid Search (5 Signals)

```
  Query: "authentication handler"
    |
    |-> 1. Code Vector (bge-small)  -> FAISS cosine
    |-> 2. Text Vector (e5-small)   -> FAISS cosine
    |-> 3. Graph Expansion          -> weighted BFS (2-hop)
    |-> 4. Keyword (FTS5)           -> BM25 ranking
    |-> 5. Community                -> summary match
    |
    +-> Weighted RRF Fusion -> Final ranked results
```

1. **Code Vector** — `BAAI/bge-small-en-v1.5` embeds code nodes, FAISS cosine search
2. **Text Vector** — `intfloat/multilingual-e5-small` embeds text nodes (100+ languages)
3. **Graph Expansion** — BFS from vector hits, weighted by edge quality (calls > imports > contains)
4. **Keyword** — FTS5 full-text over complete source code (no snippet limits)
5. **Community** — Leiden clustering summaries boost related nodes
6. **RRF Fusion** — Weighted Reciprocal Rank Fusion combines all signals

## CLI Reference

**Global flag:** `--json` outputs compact JSON for AI agent consumption.

| Command | Description |
|---------|-------------|
| `build <dir>` | Build knowledge graph (`--incremental`, `--no-embed`) |
| `search <query>` | 5-signal hybrid search (`--top-k`, `--fast`, `--expand`) |
| `query` | Interactive search REPL |
| `communities` | List and search communities (`--search`, `--level`) |
| `stats` | Graph statistics |
| `node <id>` | Node details with fuzzy matching |
| `export` | Export as JSON, GraphML, or D3.js |
| `visualize` | Interactive HTML visualization |
| `clean` | Remove .hedwig-kg/ database |
| `doctor` | Check installation health |
| `mcp` | Start MCP server (stdio) |

## Performance

Benchmarks on hedwig-kg's own codebase (~3,500 lines, 90 files, 1,300 nodes):

| Operation | Time |
|-----------|------|
| Full build | ~14s |
| Incremental (changes) | ~4s |
| Incremental (no changes) | ~0.4s |
| Cold search (dual model) | ~2.8s |
| Cold search (`--fast`) | ~0.2s |
| Warm search | ~0.08s |
| Cached search | <1ms |

- **Embedding models**: ~470MB, downloaded once to `~/.hedwig-kg/models/`
- **Database**: ~2MB (SQLite + FTS5 + FAISS indices)
- **Incremental builds**: SHA-256 hashing, 95%+ faster than full rebuild

## Requirements

- Python 3.10+
- ~470MB disk for embedding models (cached on first use)

```bash
# Optional: PDF extraction
pip install hedwig-kg[docs]
```

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
