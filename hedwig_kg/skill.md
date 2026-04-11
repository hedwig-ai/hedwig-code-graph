---
name: hedwig-kg
description: Local-first knowledge graph builder with 5-signal HybridRAG search. Use when analyzing codebases, searching for code architecture, exploring dependencies, or building knowledge graphs from source code and documents.
---

# hedwig-kg

Builds knowledge graphs from source code and documents. Searches with 5-signal HybridRAG (code vector + text vector + graph traversal + FTS5 keyword + community → RRF fusion). Supports 17 languages with deep AST extraction. 100% local.

**IMPORTANT: Always use `--json` flag.**

## Search (PRIMARY — use this first)

```bash
hedwig-kg --json search "database connection pool"       # default: 80 results
hedwig-kg --json search "auth" --fast                    # text model only, faster
hedwig-kg --json search "payment billing" --expand       # two-stage query expansion
hedwig-kg --json search "error handling" --top-k 30      # custom count
```

Response (~140 bytes/result, compact JSON):
```json
[{"label":"build_graph","kind":"function","file":"hedwig_kg/core/build.py","lines":[15,95],"score":0.073,"sig":"(extractions: list) -> nx.DiGraph","doc":"Build graph from extractions."}]
```

- `file` + `lines`: Use to read the code directly
- `sig` / `doc`: Omitted when empty
- `score`: Higher = more relevant

## Search Strategy — Drill Down, Don't Stop at First Results

**Don't search once and stop.** Use results to discover domain-specific terms, then search deeper.

### Example: "결제 관련 코드 찾아봐"

**Round 1** — Start broad with natural language:
```bash
hedwig-kg --json search "payment processing"
```
→ Results mention `StripeClient`, `checkout_handler`, `PaymentProvider`

**Round 2** — Drill into discovered terms:
```bash
hedwig-kg --json search "StripeClient"
```
→ Results reveal `create_charge`, `refund_payment`, `validate_card`, `WebhookHandler`

**Round 3** — Follow interesting connections:
```bash
hedwig-kg --json search "webhook payment callback"
```
→ Found `StripeWebhookHandler`, `handle_charge_succeeded`, `update_order_status`

**Round 4** — Explore the related service:
```bash
hedwig-kg --json search "order status update"
```
→ Found `OrderService.complete_order`, `NotificationService.send_receipt`

Now you have the full picture: Stripe → Webhook → Order → Notification.

### Example: "인증 로직 이해하고 싶어"

**Round 1**: `hedwig-kg --json search "authentication login"`
→ Found `AuthMiddleware`, `JWTTokenManager`, `SessionStore`

**Round 2**: `hedwig-kg --json search "JWTTokenManager"`
→ Found `generate_token`, `verify_token`, `refresh_token`, `token_blacklist`

**Round 3**: `hedwig-kg --json search "token blacklist refresh"`
→ Found `RedisTokenStore`, `cleanup_expired_tokens`, `rotate_refresh_token`

### The pattern:

1. **Start broad** — natural language describing intent
2. **Read results** — look for class names, function names, domain terms you didn't know
3. **Search specific** — use those discovered terms as next query
4. **Follow edges** — when results mention related services/modules, search those too
5. **Stop** when you have enough context to act

The knowledge graph connects code by calls, imports, and inheritance — so each search surfaces related code you wouldn't find by grepping.

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
- **Don't stop at first results.** Drill into discovered terms for deeper understanding.
- Use `file` and `lines` from results to read code — don't rely on search output alone.
- Run `hedwig-kg --json build . --incremental` after code changes.
- Errors return `{"error": "message"}`.
