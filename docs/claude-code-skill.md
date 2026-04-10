# hedwig-kg — Knowledge Graph Builder (Claude Code Skill)

## Overview
hedwig-kg builds knowledge graphs from source code and documents, providing HybridRAG search that combines vector similarity, graph traversal, and full-text keyword matching. Everything runs 100% locally.

## When to Use
- When you need to understand a codebase's structure, dependencies, and key components
- When searching for relevant code by natural language query
- When analyzing code architecture (god nodes, hub detection, community structure)
- When you need context about how different parts of a codebase relate to each other

## Quick Reference

### Build a Knowledge Graph
```bash
# Analyze the current project
hedwig-kg build .

# Incremental rebuild (skips unchanged files via content hash)
hedwig-kg build . --incremental

# Build without embeddings (faster, keyword-only search)
hedwig-kg build . --no-embed

# Specify output location
hedwig-kg build ./src --output ./kb-data
```

### Search the Knowledge Graph
```bash
# 4-signal HybridRAG search (vector + graph + keyword + community)
hedwig-kg search "authentication middleware"

# Get more results
hedwig-kg search "database connection pool" --top-k 20

# Search a specific knowledge base
hedwig-kg search "error handling" --source-dir ./my-project
```

### Interactive Exploration (REPL)
```bash
# Launch interactive query session (keeps graph loaded for fast searches)
hedwig-kg query

# Inside the REPL:
#   Type any query to search
#   :node <id>   — show node details
#   :stats       — show graph statistics
#   :quit        — exit

# With options
hedwig-kg query --top-k 20 --source-dir ./my-project
```

### Explore Communities
```bash
# List all detected communities with summaries
hedwig-kg communities

# Filter by hierarchy level (0=coarsest, higher=finer)
hedwig-kg communities --level 0

# Search communities by keyword
hedwig-kg communities --search "authentication"
```

### Explore the Graph
```bash
# View statistics (nodes, edges, communities, embeddings)
hedwig-kg stats

# Inspect a specific node (supports fuzzy matching)
hedwig-kg node "AuthHandler"

# Export for external analysis
hedwig-kg export --format json
hedwig-kg export --format graphml
hedwig-kg export --format d3       # D3.js force-directed graph format

# Interactive visualization (self-contained HTML)
hedwig-kg visualize
hedwig-kg visualize --max-nodes 300 -o graph.html
```

## Typical Workflow

1. **Build** the knowledge graph once per project:
   ```bash
   hedwig-kg build .
   ```

2. **Rebuild incrementally** after changes (fast — skips unchanged files):
   ```bash
   hedwig-kg build . --incremental
   ```

3. **Search** when you need to find relevant code:
   ```bash
   hedwig-kg search "your query here"
   ```

4. **Explore communities** for high-level architecture understanding:
   ```bash
   hedwig-kg communities --search "database"
   ```

5. **Inspect** specific nodes for deeper understanding:
   ```bash
   hedwig-kg node "ClassName"
   ```

## Search Result Interpretation

Each search result includes:
- **Label**: The name of the code element (function, class, module)
- **Kind**: The type (function, class, module, method, variable)
- **File**: Source file location
- **Score**: RRF fusion score (higher = more relevant)
- **Neighbors**: Related code elements in the graph

## Integration with CLAUDE.md

Add this to your project's `CLAUDE.md` to enable AI assistants to use hedwig-kg:

```markdown
## Knowledge Graph
This project uses hedwig-kg for code intelligence.

# Build the knowledge graph (run once or after major changes)
hedwig-kg build .

# Search for relevant code
hedwig-kg search "your query here"

# View graph statistics
hedwig-kg stats

# Inspect a specific code element
hedwig-kg node "ClassName"
```

## Database Location
The knowledge base is stored at `<project>/.hedwig-kg/knowledge.db` (SQLite).
It contains the graph, embeddings, FTS5 index, and community data in a single file.

## Notes
- First build downloads the embedding model (~80MB, one-time with progress indicator)
- Supports 20+ programming languages for file detection
- Tree-sitter AST extraction for Python, JavaScript, TypeScript
- Markdown extraction: headings become section nodes, internal links become reference edges
- Regex fallback extraction for other languages
- `--incremental` flag uses SHA-256 content hashing to skip unchanged files
- Community summaries are auto-generated from node attributes (no LLM required)
- 4-signal search: vector similarity + graph expansion + FTS5 keyword + community matching
- `.hedwig-kg-ignore` file controls which files to skip (like .gitignore)
