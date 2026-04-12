---
name: hedwig-cg
description: Code graph builder with LLM semantic enrichment and 5-signal hybrid search. Use when analyzing codebases, searching for code architecture, exploring dependencies, or building code graphs from source code and documents.
---

# hedwig-cg

Builds code graphs from source code and documents with LLM semantic enrichment. Searches with 5-signal hybrid search (code vector + text vector + graph traversal + FTS5 keyword + community → RRF fusion). AST extraction for 17 languages plus LLM-powered INFERRED edges for design patterns, behavioral dependencies, and cross-module relationships.

**IMPORTANT: Always use `--json` flag.**

## Search (PRIMARY — use this first)

```bash
hedwig-cg --json search "database connection pool"       # default: 80 results
hedwig-cg --json search "auth" --fast                    # text model only, faster
hedwig-cg --json search "payment billing" --expand       # two-stage query expansion
hedwig-cg --json search "error handling" --top-k 30      # custom count
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
hedwig-cg --json search "payment processing"
```
→ Results mention `StripeClient`, `checkout_handler`, `PaymentProvider`

**Round 2** — Drill into discovered terms:
```bash
hedwig-cg --json search "StripeClient"
```
→ Results reveal `create_charge`, `refund_payment`, `validate_card`, `WebhookHandler`

**Round 3** — Follow interesting connections:
```bash
hedwig-cg --json search "webhook payment callback"
```
→ Found `StripeWebhookHandler`, `handle_charge_succeeded`, `update_order_status`

**Round 4** — Explore the related service:
```bash
hedwig-cg --json search "order status update"
```
→ Found `OrderService.complete_order`, `NotificationService.send_receipt`

Now you have the full picture: Stripe → Webhook → Order → Notification.

### Example: "인증 로직 이해하고 싶어"

**Round 1**: `hedwig-cg --json search "authentication login"`
→ Found `AuthMiddleware`, `JWTTokenManager`, `SessionStore`

**Round 2**: `hedwig-cg --json search "JWTTokenManager"`
→ Found `generate_token`, `verify_token`, `refresh_token`, `token_blacklist`

**Round 3**: `hedwig-cg --json search "token blacklist refresh"`
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
hedwig-cg --json build .
```

For incremental rebuilds (only changed files):
```bash
hedwig-cg --json build . --incremental
```

This produces the base graph with EXTRACTED edges from AST analysis + embeddings + community detection.

**Step 2 — Read graph stats to prepare semantic enrichment**

```bash
hedwig-cg --json stats
```

Note the node count. If < 5 nodes, skip semantic enrichment.

**Step 3 — Semantic enrichment via subagents**

Read the code graph nodes by searching for high-connectivity nodes, then dispatch subagents to find semantic relationships.

Run a broad search to get the important nodes:
```bash
hedwig-cg --json search "*" --top-k 200
```

Group the results by directory (nodes with similar `file` paths). Split into chunks of ~20 nodes each. For each chunk, dispatch an Agent tool with `subagent_type="general-purpose"`.

**MANDATORY: Dispatch ALL agents in a single message for parallel execution.**

Each subagent receives this prompt (substitute NODE_LIST and EXISTING_EDGES):

```
You are a code architecture analyst. Analyze these code nodes and identify semantic
relationships NOT already captured by structural analysis (imports, calls, inheritance).

Focus on:
- Design pattern connections (handler implements strategy pattern)
- Behavioral dependencies (module A's output format must match module B's input)
- Alternative implementations (two modules solve the same problem differently)
- Synchronization needs (two files that must stay in sync)
- Conceptual extensions (module B extends the concept introduced in module A)
- Wrapping/delegation (module A wraps module B's functionality)

## Nodes
NODE_LIST

## Existing structural edges (do NOT duplicate these)
EXISTING_EDGES

Return ONLY a valid JSON array. Each element:
{"source": "<exact node id from file::kind::name format>",
 "target": "<exact node id>",
 "relation": "<one of: semantically_similar_to, alternative_to, depends_on_behavior, implements_pattern, synchronize_with, extends_concept, wraps, delegates_to>",
 "rationale": "<1 sentence explaining WHY this relationship exists>"}

Rules:
- Use node IDs EXACTLY as provided (file_path::kind::name format)
- Do NOT duplicate existing structural edges listed above
- Return [] if no meaningful semantic relationships exist
- Maximum 10 relationships per batch
- Every relationship must have a specific, non-generic rationale
```

Also dispatch one **cross-directory batch** with the top ~20 highest-score nodes from different directories to find cross-module relationships.

**Step 4 — Inject INFERRED edges into the graph**

Collect all subagent JSON responses. For each valid edge, add it to the graph:

```python
# Run this Python snippet to inject edges into the SQLite database
python3 -c "
import json, sqlite3
from pathlib import Path

db = Path('.hedwig-cg/knowledge.db')
conn = sqlite3.connect(str(db))

# All edges from subagents (paste merged JSON here or read from file)
edges = MERGED_EDGES_JSON

nodes = {r[0] for r in conn.execute('SELECT id FROM nodes').fetchall()}
added = 0
for e in edges:
    src, tgt = e.get('source',''), e.get('target','')
    rel = e.get('relation','')
    if src in nodes and tgt in nodes and src != tgt:
        conn.execute(
            'INSERT OR IGNORE INTO edges (source, target, relation, confidence, rationale) VALUES (?,?,?,?,?)',
            (src, tgt, rel, 'INFERRED', e.get('rationale',''))
        )
        added += 1
conn.commit()
conn.close()
print(f'Added {added} INFERRED edges')
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
hedwig-cg --json stats
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
hedwig-cg --json stats                  # Graph overview
hedwig-cg --json node "AuthHandler"     # Node details (partial match)
```

## Rules

- **Always search before grepping.** `hedwig-cg --json search` covers vector, graph, keyword, and community in one call.
- **Don't stop at first results.** Drill into discovered terms for deeper understanding.
- Use `file` and `lines` from results to read code — don't rely on search output alone.
- Run `hedwig-cg --json build . --incremental` after code changes.
- Errors return `{"error": "message"}`.
