---
name: hedwig-kg
description: Local-first knowledge graph builder with 4-signal HybridRAG search (vector + graph + keyword + community). Use when analyzing codebases, searching for code architecture, exploring dependencies, or building knowledge graphs from source code and documents.
---

# hedwig-kg

Build knowledge graphs from source code and documents. Search with 4-signal HybridRAG fusion (vector similarity + graph traversal + FTS5 keyword + community matching). 100% local — no cloud APIs.

## Quick Start

```bash
# Ensure hedwig-kg is available
python3 -c "import hedwig_kg" 2>/dev/null || pip install hedwig-kg

# Build knowledge graph from current directory
hedwig-kg build .

# Search the knowledge graph
hedwig-kg search "authentication handler"
```

## Core Patterns

### Build and Rebuild

```bash
# Full build (first time)
hedwig-kg build .

# Incremental rebuild (skips unchanged files via SHA-256 hash)
hedwig-kg build . --incremental

# Build without embeddings (faster, keyword-only search)
hedwig-kg build . --no-embed
```

### Search

```bash
# 4-signal HybridRAG search
hedwig-kg search "database connection pool"

# More results
hedwig-kg search "error handling" --top-k 20
```

### Explore Structure

```bash
# Graph statistics (density, components, clustering)
hedwig-kg stats

# Community exploration
hedwig-kg communities
hedwig-kg communities --search "auth"

# Node details (supports fuzzy matching)
hedwig-kg node "AuthHandler"

# Interactive REPL (graph stays loaded for fast queries)
hedwig-kg query
```

### Export and Visualize

```bash
# Export formats
hedwig-kg export --format json
hedwig-kg export --format d3

# Interactive HTML visualization
hedwig-kg visualize
hedwig-kg visualize --max-nodes 300 --offline
```

## Rules

- Check `.hedwig-kg/knowledge.db` before grepping raw files — use `hedwig-kg search` for graph-aware results.
- Run `hedwig-kg build . --incremental` after modifying code files to keep the graph current.
- Use `hedwig-kg communities --search "<topic>"` for high-level architecture understanding.
- Use `hedwig-kg stats` for structural overview (god nodes, communities, density).

## Commands Reference

| Command | Description |
|---------|-------------|
| `hedwig-kg build <dir>` | Build knowledge graph (`--incremental`, `--no-embed`) |
| `hedwig-kg search <query>` | 4-signal HybridRAG search (`--top-k`) |
| `hedwig-kg communities` | List/search communities (`--search`, `--level`) |
| `hedwig-kg stats` | Graph statistics with quality metrics |
| `hedwig-kg node <id>` | Node details with fuzzy matching |
| `hedwig-kg export` | Export as JSON, GraphML, D3.js |
| `hedwig-kg visualize` | Interactive HTML visualization (`--offline`) |
| `hedwig-kg query` | Interactive search REPL |
| `hedwig-kg clean` | Remove .hedwig-kg/ database |
| `hedwig-kg install` | Register /hedwig-kg slash command globally |
| `hedwig-kg claude install` | Per-project CLAUDE.md + PreToolUse hook |

## Output

Knowledge base: `<project>/.hedwig-kg/knowledge.db` (SQLite + FTS5 + FAISS vector index).
