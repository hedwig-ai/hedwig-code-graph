<p align="center">
<img width="2048" height="1138" alt="hegwid-cg" src="https://github.com/user-attachments/assets/2875669b-e7e3-45df-9e50-90110e2abbf1" />
<h1 align="center">hedwig-cg</h1>
  <p align="center">
    "With hedwig-cg, your coding agent knows what to read."
    <br />
    <a href="#quick-start">Quick Start</a> · <a href="docs/README_ko.md">한국어</a> · <a href="docs/README_ja.md">日本語</a> · <a href="docs/README_zh.md">中文</a> · <a href="docs/README_de.md">Deutsch</a>
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

> raw data from a given number of sources is collected, then compiled by an LLM into a .md wiki, then operated on by various CLIs by the LLM to do Q&A and to incrementally enhance the wiki - Andrej Karpathy

hedwig-cg builds a queryable code graph and knowledge base from codebases with 10,000+ files and knowledge documents, powered by lightweight local LLM models. Hybrid vector + keyword search with subgraph response (vector + keyword → RRF fusion with MST subgraph) lets coding agents truly understand your entire project, not just search keywords. Install it, and Claude Code sees the full picture — no extra tokens, no extra commands, everything runs 100% locally.

## Quick Start

```bash
pip install hedwig-cg

cd your-project/
hedwig-cg opencode install    # for OpenCode
# or: hedwig-cg claude install  # for Claude Code
```

Then tell Claude Code or OpenCode:

> "Build a code graph for this project"

That's it. Your agent will build the graph, and from then on, consult it before every search. The graph auto-rebuilds when your session ends.

## AI Agent Integrations

hedwig-cg integrates with major AI coding agents in one command:

| Agent | Install | What it does |
|-------|---------|-------------|
| **Claude Code** | `hedwig-cg claude install` | Skill + CLAUDE.md + PreToolUse hook |
| **OpenCode** | `hedwig-cg opencode install` | Skill in `.opencode/skills/` |
| **Codex CLI** | `hedwig-cg codex install` | AGENTS.md + PreToolUse hook |
| **Gemini CLI** | `hedwig-cg gemini install` | GEMINI.md + BeforeTool hook |
| **Cursor IDE** | `hedwig-cg cursor install` | `.cursor/rules/` rule file |
| **Windsurf IDE** | `hedwig-cg windsurf install` | `.windsurf/rules/` rule file |
| **Cline** | `hedwig-cg cline install` | `.clinerules` file |
| **Aider CLI** | `hedwig-cg aider install` | CONVENTIONS.md + `.aider.conf.yml` |
| **MCP Server** | `claude mcp add hedwig-cg -- hedwig-cg mcp` | 5 tools over Model Context Protocol |

Each `install` does two things: writes a context file with rules, and (where supported) registers a hook that fires before tool calls. To remove: `hedwig-cg <platform> uninstall`.

## Supported Languages

### Structural Extraction (20+ languages)

hedwig-cg extracts functions, classes, methods, calls, imports, and inheritance from source code using tree-sitter and native parsers.

| | | | |
|:---:|:---:|:---:|:---:|
| Python | JavaScript | TypeScript | Go |
| Rust | Java | C | C++ |
| C# | Ruby | Swift | Scala |
| Lua | PHP | Elixir | Kotlin |
| Objective-C | Terraform/HCL | | |

Also extracts structure from config and document formats: YAML, JSON, TOML, Markdown, PDF, HTML, CSV, Shell, R, and more.

### Multilingual Natural Language

Text nodes (docs, comments, markdown) are embedded with `intfloat/multilingual-e5-small` supporting **100+ natural languages** — Korean, Japanese, Chinese, German, French, and more. Search in your language, find results in any language.

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

## Hybrid Search with Subgraph Response

Every query returns seed nodes and a subgraph showing how they connect:

**Search Pipeline**

| Signal | What it finds |
|--------|---------------|
| **Vector Search** | Semantically similar code and documents (dual-model: code + text) |
| **Keyword Search** | Exact name matches via FTS5 (BM25) |

Results are fused via Weighted Reciprocal Rank Fusion (RRF), then connected through MST-based shortest paths to reveal how seed nodes relate.

**Response Format**
```
seeds:
hedwig_cg/core/pipeline.py:71
hedwig_cg/query/embeddings.py:70

edges:
hedwig_cg/core/pipeline.py:71 -calls-> hedwig_cg/core/extract.py:747
hedwig_cg/core/pipeline.py:0 -co_change-> hedwig_cg/query/embeddings.py:0
```

- `seeds`: Node IDs (file:line) found by search
- `edges`: Subgraph connecting seeds through shortest paths (intermediate nodes appear in edges)

## CLI Reference

All commands output compact text by default (designed for AI agent consumption).

| Command | Description |
|---------|-------------|
| `build <dir>` | Build code graph (`--incremental`) |
| `search <query>` | Hybrid vector + keyword search with subgraph (`--top-k`, `--fast`) |
| `search-vector <query>` | Vector similarity only (code + text dual model) |
| `search-keyword <query>` | FTS5 keyword matching only (BM25 ranking) |
| `query` | Interactive search REPL |
| `communities` | List and search communities (`--search`, `--level`) |
| `stats` | Graph statistics |
| `node <id>` | Node details with fuzzy matching |
| `export` | Export as JSON, GraphML, or D3.js |
| `visualize` | Interactive HTML visualization |
| `clean` | Remove .hedwig-cg/ database |
| `doctor` | Check installation health |
| `mcp` | Start MCP server (stdio) |
| `claude install\|uninstall` | Manage Claude Code integration |
| `codex install\|uninstall` | Manage Codex CLI integration |
| `gemini install\|uninstall` | Manage Gemini CLI integration |
| `cursor install\|uninstall` | Manage Cursor IDE integration |
| `windsurf install\|uninstall` | Manage Windsurf IDE integration |
| `cline install\|uninstall` | Manage Cline integration |
| `aider install\|uninstall` | Manage Aider CLI integration |
| `opencode install\|uninstall` | Manage OpenCode integration |

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

- **Embedding models**: ~180MB, downloaded once to `~/.hedwig-cg/models/`
- **Database**: ~2MB (SQLite + FTS5 + FAISS indices)
- **Incremental builds**: SHA-256 hashing, 95%+ faster than full rebuild

## Requirements

- Python 3.10+
- ~180MB disk for embedding models (cached on first use)

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
