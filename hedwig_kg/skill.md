---
name: hedwig-kg
description: Local-first knowledge graph builder with 5-signal HybridRAG search (dual vector + graph + keyword + community → RRF fusion). Use when analyzing codebases, searching for code architecture, exploring dependencies, or building knowledge graphs from source code and documents.
---

# hedwig-kg

Build knowledge graphs from source code and documents. Search with 5-signal HybridRAG fusion (code vector + text vector + graph traversal + FTS5 keyword + community matching → RRF). Dual embedding models: `BAAI/bge-small-en-v1.5` for code, `all-MiniLM-L6-v2` for text. 100% local — no cloud APIs.

**IMPORTANT: Always use `--json` flag.** All commands return structured JSON that you can parse directly. No Rich formatting, no model download logs — clean JSON only.

## Quick Start

```bash
# Ensure hedwig-kg is available
python3 -c "import hedwig_kg" 2>/dev/null || pip install hedwig-kg

# Build knowledge graph from current directory
hedwig-kg --json build .

# Search the knowledge graph (PRIMARY command)
hedwig-kg --json search "authentication handler"
```

## Core Commands

### Search (PRIMARY — use this first)

```bash
# 5-signal HybridRAG search (default: 15 results)
hedwig-kg --json search "database connection pool"

# Custom result count
hedwig-kg --json search "error handling" --top-k 30

# Fast mode (text model only, lower latency)
hedwig-kg --json search "auth" --fast
```

Response format:
```json
[{"node_id": "...", "label": "AuthHandler", "kind": "class", "file_path": "src/auth.py", "start_line": 10, "end_line": 45, "score": 0.031, "snippet": "...", "signal_contributions": {...}, "neighbors": [...]}]
```

### Build

```bash
# Full build (first time)
hedwig-kg --json build .

# Incremental rebuild (skips unchanged files)
hedwig-kg --json build . --incremental
```

### Inspect

```bash
# Graph statistics
hedwig-kg --json stats

# Node details with edges (supports partial matching)
hedwig-kg --json node "AuthHandler"
```

## Rules

- **Always use `--json` flag** so output is machine-parseable. Without it, output is human-readable Rich tables.
- **Always use `hedwig-kg --json search "<query>"` as the primary search method.** It runs 5-signal HybridRAG in a single call — no need for separate searches.
- Before grepping raw files with Glob/Grep, run `hedwig-kg --json search` first. Only fall back to Grep if the knowledge graph has no results.
- Search results include `file_path` and `start_line`/`end_line` — use these to read the relevant code directly.
- Run `hedwig-kg --json build . --incremental` after modifying code files to keep the graph current.
- Errors return `{"error": "message"}` — check for this key in the response.

## Output

Knowledge base: `<project>/.hedwig-kg/knowledge.db` (SQLite + FTS5 + dual FAISS vector indices).
