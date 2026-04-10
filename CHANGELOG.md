# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Community-aware HybridRAG**: 4-signal search (vector + graph + keyword + community), up from 3 signals
- **Community summaries**: Auto-generated keyword-rich text from node labels, kinds, docstrings, and file paths
- **`hedwig-kg communities` CLI command**: List, filter by level, and search communities
- **Markdown document extraction**: Headings become section nodes with hierarchy, internal links become reference edges
- **Incremental build** (`--incremental`): SHA-256 content hashing skips unchanged files for fast rebuilds
- **Embedding download UX**: Rich console message on first model download (~80MB)
- `community_search()` method in KnowledgeStore for summary-based community lookup
- **D3.js export format** (`--format d3`): Force-directed graph JSON with PageRank-based sizing and kind-based grouping
- **`hedwig-kg visualize` CLI command**: Self-contained interactive HTML visualization with zoom, search, tooltips, and drag
- **`hedwig-kg clean` CLI command**: Remove .hedwig-kg/ database directory with confirmation prompt
- **Graph quality metrics in `stats`**: Density, connected components, average clustering coefficient
- Comprehensive CLI command tests (communities, search, d3 export, visualize, clean)
- Comprehensive JavaScript tree-sitter extraction tests (17 tests)
- **`hedwig-kg query` REPL**: Interactive search session with `:node`, `:stats`, `:quit` commands
- **`--offline` flag for `visualize`**: Inlines D3.js (~280KB) for airgapped/offline environments
- **TypeScript-specific extraction**: Interfaces (with extends/method signatures), type aliases, enums with member extraction
- E2E integration tests for full pipeline (build → store → search → incremental → export → clean)
- TypeScript-specific tree-sitter extraction tests (12 tests)
- 160 tests with 87% code coverage (up from 61 tests)
- **PyPI classifiers expansion**: Python 3.10/3.11/3.12, AI/NLP topics, `Typing :: Typed`, OS Independent
- **GitHub Actions PyPI publish**: Automated deployment on GitHub Release via `pypa/gh-action-pypi-publish`

### Fixed
- **Critical**: `dependencies` in pyproject.toml was under `[project.urls]` TOML section, causing wheel to declare zero dependencies
- Resolved all 27 ruff lint errors (import sorting, unused variables, line length)
- Removed legacy ignore-file backward compatibility reference
- Removed stale `build_hnsw_index` backward-compat alias from store.py
- Fixed `try_to_load_from_cache` return value check in embeddings.py (operator precedence bug)
- **Critical**: Incremental build second run returned empty graph — fixed by merging unchanged files from DB via `nx.compose()`

### Changed
- Updated CLAUDE.md and Claude Code skill docs with new commands and features
- Updated CHANGELOG.md to reflect all iterations

## [0.1.0] - 2026-04-11

### Added
- Core pipeline: detect → extract → build → embed → cluster → analyze → store
- HybridRAG search engine combining vector similarity, graph traversal, and FTS5 keyword matching with RRF fusion
- Tree-sitter AST extraction for Python, JavaScript, TypeScript with regex fallback
- Hierarchical Leiden community detection at multiple resolutions (0.25, 0.5, 1.0, 2.0)
- Local embeddings via sentence-transformers (all-MiniLM-L6-v2)
- FAISS vector index for cosine similarity search
- SQLite + FTS5 full-text search with BM25 ranking
- CLI commands: `build`, `search`, `stats`, `node`, `export`
- Graph analysis: PageRank, god node detection, hub analysis, quality metrics
- File detection for 20+ programming languages
- `.hedwig-kg-ignore` for excluding files from analysis
- Privacy-first design: 100% local, no cloud services
- Claude Code skill documentation for AI tool integration
- Multi-language README (English, Korean, Japanese)
- GitHub Actions CI (Python 3.10-3.12, Ubuntu + macOS)
- CONTRIBUTING.md with development guide

[Unreleased]: https://github.com/hedwig-ai/hedwig-knowledge-graph/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/hedwig-ai/hedwig-knowledge-graph/releases/tag/v0.1.0
