---
name: hedwig-cg
description: Local-first code graph builder with 5-signal hybrid search. Use when analyzing codebases, searching for code architecture, exploring dependencies, or building code graphs from source code and documents.
---

# hedwig-cg

Builds code graphs from source code and documents. Searches with 5-signal hybrid search (code vector + text vector + graph traversal + FTS5 keyword + community → RRF fusion). Supports 17 languages with deep AST extraction. 100% local.

## Search (PRIMARY — use this first)

```bash
hedwig-cg search "database connection pool"       # default: 30 results
hedwig-cg search "auth" --fast                    # text model only, faster
hedwig-cg search "payment billing" --expand       # two-stage query expansion
hedwig-cg search "error handling" --top-k 10      # custom count
```

Response (compact JSON with relationship edges):
```json
{
  "results": [
    {"label":"build_graph","kind":"function","file":"core/build.py","lines":[15,95],"score":0.073,"sig":"(extractions) -> DiGraph","doc":"Build graph."},
    {"label":"KnowledgeStore","kind":"class","file":"storage/store.py","lines":[20,300],"score":0.065}
  ],
  "edges": [
    {"from":"build_graph","to":"KnowledgeStore","rel":"calls"}
  ]
}
```

- `results[].file` + `lines`: Use to read the code directly
- `results[].sig` / `doc`: Omitted when empty
- `results[].score`: Higher = more relevant
- `edges`: Relationships between result nodes (calls, imports, inherits, etc.) — use to understand how results connect

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

```bash
hedwig-cg build .                # Full build
hedwig-cg build . --incremental  # Only changed files
```

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
