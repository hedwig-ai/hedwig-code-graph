---
name: hedwig-cg
description: Code graph builder with LLM semantic enrichment and 5-signal hybrid search. Use when analyzing codebases, searching for code architecture, exploring dependencies, or building code graphs from source code and documents.
---

# hedwig-cg

Builds code graphs from source code and documents with LLM semantic enrichment. Searches with 5-signal hybrid search (code vector + text vector + graph traversal + FTS5 keyword + community → RRF fusion). AST extraction for 17 languages plus LLM-powered INFERRED edges for design patterns, behavioral dependencies, and cross-module relationships.

**All commands output JSON by default.**

## Search (PRIMARY — use this first)

```bash
hedwig-cg search "database connection pool"       # default: 80 results
hedwig-cg search "auth" --fast                    # text model only, faster
hedwig-cg search "payment billing" --expand       # two-stage query expansion
hedwig-cg search "error handling" --top-k 30      # custom count
```

Response (~140 bytes/result, compact JSON):
```json
[{"label":"build_graph","kind":"function","file":"hedwig_cg/core/build.py","lines":[15,95],"score":0.073,"sig":"(extractions: list) -> nx.DiGraph","doc":"Build graph from extractions."}]
```

- `file` + `lines`: Use to read the code directly
- `sig` / `doc`: Omitted when empty
- `score`: Higher = more relevant

## Search Strategy — Drill Down, Don't Stop at First Results

**Don't search once and stop.** Use results to discover domain-specific terms, then search deeper.

### Example: "결제 관련 코드 찾아봐"

**Round 1** — Start broad with natural language:
```bash
hedwig-cg search "payment processing"
```
→ Results mention `StripeClient`, `checkout_handler`, `PaymentProvider`

**Round 2** — Drill into discovered terms:
```bash
hedwig-cg search "StripeClient"
```
→ Results reveal `create_charge`, `refund_payment`, `validate_card`, `WebhookHandler`

**Round 3** — Follow interesting connections:
```bash
hedwig-cg search "webhook payment callback"
```
→ Found `StripeWebhookHandler`, `handle_charge_succeeded`, `update_order_status`

**Round 4** — Explore the related service:
```bash
hedwig-cg search "order status update"
```
→ Found `OrderService.complete_order`, `NotificationService.send_receipt`

Now you have the full picture: Stripe → Webhook → Order → Notification.

### Example: "인증 로직 이해하고 싶어"

**Round 1**: `hedwig-cg search "authentication login"`
→ Found `AuthMiddleware`, `JWTTokenManager`, `SessionStore`

**Round 2**: `hedwig-cg search "JWTTokenManager"`
→ Found `generate_token`, `verify_token`, `refresh_token`, `token_blacklist`

**Round 3**: `hedwig-cg search "token blacklist refresh"`
→ Found `RedisTokenStore`, `cleanup_expired_tokens`, `rotate_refresh_token`

### The pattern:

1. **Start broad** — natural language describing intent
2. **Read results** — look for class names, function names, domain terms you didn't know
3. **Search specific** — use those discovered terms as next query
4. **Follow edges** — when results mention related services/modules, search those too
5. **Stop** when you have enough context to act

The code graph connects code by calls, imports, and inheritance — so each search surfaces related code you wouldn't find by grepping.

## Build

When building a code graph, **always run the full pipeline** — AST structural extraction followed by LLM semantic enrichment. This produces both EXTRACTED edges (imports, calls, inheritance) and INFERRED edges (design patterns, behavioral dependencies, cross-module relationships) in a single pass.

### Full pipeline (always use this)

**Step 1 — AST structural extraction**

```bash
hedwig-cg build .
```

For incremental rebuilds (only changed files):
```bash
hedwig-cg build . --incremental
```

This produces the base graph with EXTRACTED edges from AST analysis + embeddings + community detection.

**Step 2 — Read graph stats to prepare semantic enrichment**

```bash
hedwig-cg stats
```

Note the node count. If < 5 nodes, skip semantic enrichment.

**Step 3 — Semantic enrichment via subagents (file-based)**

Get the file list grouped by directory:

```bash
hedwig-cg files --page 1           # first 3 chunks
hedwig-cg files --page 2           # next 3 chunks
hedwig-cg files                    # all chunks (small projects)
```

Each chunk contains ~20 files from the same directory plus existing AST edges between them. Response includes `total_pages` for pagination.

For each chunk, dispatch an Agent with `subagent_type="general-purpose"`. The subagent **reads the actual files** and extracts semantic relationships. Process page by page until `page == total_pages`.

**MANDATORY: Dispatch ALL agents for the current page in a single message for parallel execution.**

Each subagent receives this prompt (substitute FILE_LIST and EXISTING_EDGES):

```
You are a code architecture analyst. Read the files listed below and extract a knowledge
graph fragment — both NEW concept nodes and semantic edges that AST extraction missed.

**Read each file using the Read tool**, then:

1. Extract CONCEPT NODES — abstract ideas, patterns, or cross-cutting concerns that
   are NOT individual functions/classes but represent higher-level architectural concepts.
   Examples: "AuthenticationFlow", "ErrorHandlingStrategy", "CachingLayer"
   Only create concept nodes when they add information beyond what AST already captured.

2. Extract SEMANTIC EDGES between any nodes (existing AST nodes or new concept nodes).
   Focus on relationships AST cannot find:
   - Design pattern connections (handler implements strategy pattern)
   - Behavioral dependencies (module A's output format must match module B's input)
   - Shared data / synchronization needs (two files that must stay in sync)
   - Conceptual relationships (module B extends the concept from module A)
   - Rationale: comments/docstrings explaining WHY → `rationale_for` edge
   - Semantic similarity: two entities solving the same problem without structural link

## Files to read
FILE_LIST

## Existing structural edges (do NOT duplicate these — AST already found them)
EXISTING_EDGES

After reading ALL files, output EXACTLY this JSON (no other text):
{
  "nodes": [
    {
      "id": "concept_snake_case_name",
      "label": "Human Readable Name",
      "kind": "concept",
      "file_path": "source/file.py",
      "docstring": "Brief description of this concept"
    }
  ],
  "edges": [
    {
      "source": "node_id",
      "target": "node_id",
      "relation": "relation_type",
      "confidence": "INFERRED",
      "confidence_score": 0.8,
      "rationale": "Why this relationship exists"
    }
  ]
}

Node ID format for EXISTING nodes: file_path::kind::name
Node ID format for NEW concept nodes: concept_snake_case_name

Edge relation types:
  calls, implements, references, conceptually_related_to, shares_data_with,
  semantically_similar_to, depends_on_behavior, synchronize_with,
  extends_concept, wraps, delegates_to, rationale_for

Confidence tagging:
- EXTRACTED: relationship explicit in source (confidence_score = 1.0)
- INFERRED: reasonable inference with evidence (confidence_score = 0.6-0.9)
- AMBIGUOUS: uncertain — flag for review, do NOT omit (confidence_score = 0.1-0.3)

confidence_score is REQUIRED on every edge — never omit, never default to 0.5.

Rules:
- Read the actual files — do not guess from file names alone
- Do NOT duplicate existing structural edges listed above
- Only create concept nodes when they represent genuine architectural abstractions
- Return {"nodes": [], "edges": []} if nothing meaningful found
- Maximum 10 concept nodes and 15 edges per chunk
- Every edge must have a specific rationale based on code you actually read
```

**Step 4 — Inject nodes and edges into the graph**

Collect all subagent JSON responses. Merge and inject both new nodes and edges:

```python
python3 -c "
import json, sqlite3
from pathlib import Path

db = Path('.hedwig-cg/knowledge.db')
conn = sqlite3.connect(str(db))

# All results from subagents merged into one dict
data = MERGED_RESULTS_JSON  # {'nodes': [...], 'edges': [...]}

# Inject new concept nodes
nodes_added = 0
for n in data.get('nodes', []):
    nid = n.get('id', '')
    if not nid:
        continue
    try:
        conn.execute(
            'INSERT OR IGNORE INTO nodes (id, label, kind, file_path, docstring) VALUES (?,?,?,?,?)',
            (nid, n.get('label', ''), n.get('kind', 'concept'),
             n.get('file_path', ''), n.get('docstring', ''))
        )
        nodes_added += 1
    except Exception:
        pass

# Inject edges (between existing + new nodes)
all_nodes = {r[0] for r in conn.execute('SELECT id FROM nodes').fetchall()}
edges_added = 0
for e in data.get('edges', []):
    src, tgt = e.get('source', ''), e.get('target', '')
    rel = e.get('relation', '')
    conf = e.get('confidence', 'INFERRED')
    score = e.get('confidence_score', 0.5)
    rationale = e.get('rationale', '')
    if src in all_nodes and tgt in all_nodes and src != tgt:
        try:
            conn.execute(
                'INSERT OR IGNORE INTO edges (source, target, relation, confidence, rationale) VALUES (?,?,?,?,?)',
                (src, tgt, rel, conf, rationale)
            )
            edges_added += 1
        except Exception:
            pass

conn.commit()
conn.close()
print(f'Added {nodes_added} concept nodes, {edges_added} INFERRED edges')
"
```

After injection, clear the search cache so new edges are reflected:
```python
python3 -c "
from hedwig_cg.query.hybrid import clear_search_cache
clear_search_cache()
print('Search cache cleared')
"
```

**Step 5 — Verify**

```bash
hedwig-cg stats
```

Compare edge count before and after. The new INFERRED edges strengthen graph N-hop traversal and community detection signals in search.

### Why this matters

AST extraction finds structural relationships (who imports whom, who calls whom). But it misses:
- `rate_limiter` ↔ `billing_module` — "rate limit triggers billing policy changes"
- `migration_v3` ↔ `deprecated_handler` — "handler is deletion target after migration"
- `error_codes.py` ↔ `frontend/errors.ts` — "these two files must stay in sync"

LLM semantic enrichment finds these. Combined with 5-signal HybridRAG search, the graph becomes significantly more useful.

## Inspect

```bash
hedwig-cg stats                  # Graph overview
hedwig-cg node "AuthHandler"     # Node details (partial match)
```

## Rules

- **Always search before grepping.** `hedwig-cg search` covers vector, graph, keyword, and community in one call.
- **Don't stop at first results.** Drill into discovered terms for deeper understanding.
- Use `file` and `lines` from results to read code — don't rely on search output alone.
- Run `hedwig-cg build . --incremental` after code changes.
- Errors return `{"error": "message"}`.
