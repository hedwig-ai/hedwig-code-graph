# Contributing to hedwig-cg

Thank you for your interest in contributing to hedwig-cg! This guide will help you get started.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/hedwig-ai/hedwig-code-graph.git
cd hedwig-code-graph

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# .venv\Scripts\activate   # Windows

# Install in development mode with dev dependencies
pip install -e ".[dev]"
```

## Running Tests

```bash
# Run all tests with coverage
pytest

# Run a specific test file
pytest tests/test_store.py

# Run with verbose output
pytest -v
```

## Code Style

We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting:

```bash
# Check for issues
ruff check .

# Auto-fix issues
ruff check --fix .

# Format code
ruff format .
```

**Key conventions:**
- Line length: 100 characters
- Target Python: 3.10+
- Import sorting: isort-compatible (handled by Ruff)

## Project Structure

```
hedwig_cg/
├── cli/          # Click-based CLI interface
├── core/         # Pipeline stages (detect, extract, build, cluster, analyze)
├── query/        # Hybrid search engine (vector + graph + keyword + RRF)
└── storage/      # SQLite + FAISS storage layer
```

## Making Changes

1. **Fork** the repository and create a feature branch from `main`.
2. **Write tests** for any new functionality in `tests/`.
3. **Run the test suite** to ensure nothing is broken.
4. **Follow the existing code style** — Ruff will help enforce this.
5. **Keep commits focused** — one logical change per commit.

## Pull Request Guidelines

- Keep PRs focused on a single change.
- Include a clear description of what the PR does and why.
- Ensure all tests pass before submitting.
- Update documentation if you change public APIs or CLI commands.

## Architecture Notes

The pipeline follows a linear flow:

```
detect → extract → build → embed → cluster → analyze → store
```

- **detect**: Scans directories, classifies files by language.
- **extract**: Tree-sitter AST extraction with regex fallback.
- **build**: Assembles a NetworkX DiGraph with deduplication.
- **embed**: Generates sentence-transformer embeddings locally.
- **cluster**: Hierarchical Leiden community detection.
- **analyze**: Structural analysis (god nodes, hubs, quality metrics).
- **store**: SQLite + FTS5 + FAISS vector index, all in a single file.

## Reporting Issues

- Use [GitHub Issues](https://github.com/hedwig-ai/hedwig-code-graph/issues) for bug reports and feature requests.
- Include reproduction steps for bugs.
- Mention your Python version and OS.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
