---
name: hedwig-kg
description: Local-first knowledge graph builder with 5-signal HybridRAG search (dual vector + graph + keyword + community → RRF fusion). Use when analyzing codebases, searching for code architecture, exploring dependencies, or building knowledge graphs from source code and documents.
---

# hedwig-kg

Build knowledge graphs from source code and documents. Search with 5-signal HybridRAG fusion (code vector + text vector + graph traversal + FTS5 keyword + community matching → RRF). Dual embedding models: `BAAI/bge-small-en-v1.5` for code, `all-MiniLM-L6-v2` for text. 100% local — no cloud APIs.

## Quick Start

```bash
# Ensure hedwig-kg is available
python3 -c "import hedwig_kg" 2>/dev/null || pip install hedwig-kg

# Build knowledge graph from current directory
hedwig-kg build .

# Search the knowledge graph (PRIMARY command)
hedwig-kg search "authentication handler"
```

## Core Commands

### Search (PRIMARY — use this first)

```bash
# 5-signal HybridRAG search — covers vector, graph, keyword, community
hedwig-kg search "database connection pool"

# More results
hedwig-kg search "error handling" --top-k 20

# Fast mode (text model only, lower latency)
hedwig-kg search "auth" --fast
```

### Build

```bash
# Full build (first time)
hedwig-kg build .

# Incremental rebuild (skips unchanged files)
hedwig-kg build . --incremental
```

### Inspect

```bash
# Graph statistics
hedwig-kg stats

# Node details (supports partial matching)
hedwig-kg node "AuthHandler"
```

## Rules

- **Always use `hedwig-kg search "<query>"` as the primary search method.** It runs 5-signal HybridRAG in a single call — no need for separate searches.
- Before grepping raw files with Glob/Grep, run `hedwig-kg search` first. Only fall back to Grep if the knowledge graph has no results.
- Run `hedwig-kg build . --incremental` after modifying code files to keep the graph current.
- Use `hedwig-kg stats` for structural overview (god nodes, communities, density).

## Output

Knowledge base: `<project>/.hedwig-kg/knowledge.db` (SQLite + FTS5 + dual FAISS vector indices).
