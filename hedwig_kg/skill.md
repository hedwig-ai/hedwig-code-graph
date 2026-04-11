---
name: hedwig-kg
description: Local-first knowledge graph builder with 5-signal HybridRAG search. Use when analyzing codebases, searching for code architecture, exploring dependencies, or building knowledge graphs from source code and documents.
---

# hedwig-kg

Builds knowledge graphs from source code and documents. Searches with 5-signal HybridRAG (code vector + text vector + graph traversal + FTS5 keyword + community → RRF fusion). Supports 17 languages with deep AST extraction. 100% local.

**IMPORTANT: Always use `--json` flag.**

## Search (PRIMARY — use this first)

```bash
# 5-signal HybridRAG search (default: 80 results)
hedwig-kg --json search "database connection pool"

# Fast mode (text model only, lower cold-start latency)
hedwig-kg --json search "auth" --fast

# Expanded search (two-stage query expansion for broader recall)
hedwig-kg --json search "payment billing" --expand

# Custom result count
hedwig-kg --json search "error handling" --top-k 30
```

Response (~140 bytes/result, compact JSON):
```json
[{"label":"build_graph","kind":"function","file":"hedwig_kg/core/build.py","lines":[15,95],"score":0.073,"sig":"(extractions: list) -> nx.DiGraph","doc":"Build graph from extractions."}]
```

- `file` + `lines`: Use to read the code directly
- `sig` / `doc`: Omitted when empty
- `score`: Higher = more relevant

## Build

```bash
hedwig-kg --json build .                # Full build
hedwig-kg --json build . --incremental  # Only changed files
```

## Inspect

```bash
hedwig-kg --json stats                  # Graph overview
hedwig-kg --json node "AuthHandler"     # Node details (partial match)
```

## Rules

- **Always search before grepping.** `hedwig-kg --json search` covers vector, graph, keyword, and community in one call.
- Use `file` and `lines` from results to read code — don't rely on search output alone.
- Run `hedwig-kg --json build . --incremental` after code changes.
- Errors return `{"error": "message"}`.
