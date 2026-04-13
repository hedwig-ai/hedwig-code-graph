"""End-to-end integration tests for the full pipeline.

Tests the complete flow: build → store → search → stats → export → clean.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from hedwig_cg.core.pipeline import run_pipeline
from hedwig_cg.storage.store import KnowledgeStore


@pytest.fixture()
def sample_project(tmp_path):
    """Create a minimal multi-file Python project for testing."""
    src = tmp_path / "sample_project"
    src.mkdir()

    # Python module with class and function
    (src / "auth.py").write_text("""\
class AuthHandler:
    \"\"\"Handles user authentication.\"\"\"

    def login(self, username, password):
        \"\"\"Authenticate a user with credentials.\"\"\"
        return self._verify(username, password)

    def _verify(self, username, password):
        return username == "admin"

    def logout(self, session_id):
        \"\"\"End a user session.\"\"\"
        pass


def create_auth_handler():
    \"\"\"Factory function for AuthHandler.\"\"\"
    return AuthHandler()
""")

    # Another module that imports from auth
    (src / "server.py").write_text("""\
from auth import create_auth_handler

MAX_CONNECTIONS = 100

class Server:
    \"\"\"HTTP server with authentication.\"\"\"

    def __init__(self, port):
        self.port = port
        self.auth = create_auth_handler()

    def start(self):
        \"\"\"Start the server.\"\"\"
        pass

    def handle_request(self, request):
        \"\"\"Handle incoming HTTP request.\"\"\"
        return {"status": 200}
""")

    # JavaScript file
    (src / "utils.js").write_text("""\
export class Logger {
  constructor(level) {
    this.level = level;
  }

  log(message) {
    console.log(`[${this.level}] ${message}`);
  }
}

export function formatDate(date) {
  return date.toISOString();
}

const MAX_LOG_SIZE = 1024;
""")

    # Markdown documentation
    (src / "README.md").write_text("""\
# Sample Project

## Authentication

The auth module handles user login and logout.

## Server

The server module provides HTTP handling with [auth](auth.py) integration.

## Utilities

JavaScript utilities for logging and date formatting.
""")

    return src


class TestFullPipeline:
    """Test the complete build pipeline without embeddings."""

    def test_build_creates_database(self, sample_project):
        result = run_pipeline(sample_project, embed=False)
        assert Path(result.db_path).exists()
        assert result.graph is not None
        assert result.graph.number_of_nodes() > 0

    def test_build_detects_all_files(self, sample_project):
        result = run_pipeline(sample_project, embed=False)
        detected_files = [f.path for f in result.detect_result.files]
        basenames = [Path(f).name for f in detected_files]
        assert "auth.py" in basenames
        assert "server.py" in basenames
        assert "utils.js" in basenames
        assert "README.md" in basenames

    def test_build_extracts_classes(self, sample_project):
        result = run_pipeline(sample_project, embed=False)
        labels = [
            result.graph.nodes[n].get("label", "")
            for n in result.graph.nodes
        ]
        assert "AuthHandler" in labels
        assert "Server" in labels

    def test_build_extracts_functions(self, sample_project):
        result = run_pipeline(sample_project, embed=False)
        labels = [
            result.graph.nodes[n].get("label", "")
            for n in result.graph.nodes
        ]
        assert "create_auth_handler" in labels

    def test_build_extracts_js_classes(self, sample_project):
        result = run_pipeline(sample_project, embed=False)
        labels = [
            result.graph.nodes[n].get("label", "")
            for n in result.graph.nodes
        ]
        assert "Logger" in labels

    def test_build_creates_edges(self, sample_project):
        result = run_pipeline(sample_project, embed=False)
        assert result.graph.number_of_edges() > 0
        edge_relations = [
            d.get("relation", "")
            for _, _, d in result.graph.edges(data=True)
        ]
        assert "defines" in edge_relations

    def test_build_computes_pagerank(self, sample_project):
        result = run_pipeline(sample_project, embed=False)
        pageranks = [
            result.graph.nodes[n].get("pagerank", 0)
            for n in result.graph.nodes
        ]
        assert any(pr > 0 for pr in pageranks)

    def test_build_runs_clustering(self, sample_project):
        result = run_pipeline(sample_project, embed=False)
        assert result.cluster_result is not None
        assert len(result.cluster_result.communities) >= 0

    def test_build_runs_analysis(self, sample_project):
        result = run_pipeline(sample_project, embed=False)
        assert result.analysis is not None


class TestStoreAfterBuild:
    """Test that the store is correctly populated after a build."""

    def test_store_loads_graph(self, sample_project):
        pipeline_result = run_pipeline(sample_project, embed=False)
        store = KnowledgeStore(pipeline_result.db_path)
        G = store.load_graph()
        assert G.number_of_nodes() > 0
        assert G.number_of_nodes() == pipeline_result.graph.number_of_nodes()
        store.close()

    def test_store_keyword_search(self, sample_project):
        pipeline_result = run_pipeline(sample_project, embed=False)
        store = KnowledgeStore(pipeline_result.db_path)
        results = store.keyword_search(["auth", "login"])
        assert len(results) > 0
        assert any("auth" in r["label"].lower() or "login" in r["label"].lower()
                    for r in results)
        store.close()

    def test_store_keyword_search_no_results(self, sample_project):
        pipeline_result = run_pipeline(sample_project, embed=False)
        store = KnowledgeStore(pipeline_result.db_path)
        results = store.keyword_search(["zzz_nonexistent_xyz"])
        assert len(results) == 0
        store.close()


class TestIncrementalBuild:
    """Test incremental rebuild behavior."""

    def test_incremental_skips_unchanged(self, sample_project):
        # First build
        r1 = run_pipeline(sample_project, embed=False, incremental=True)
        n1 = r1.graph.number_of_nodes()

        # Second build — same files, should produce same graph
        r2 = run_pipeline(sample_project, embed=False, incremental=True)
        n2 = r2.graph.number_of_nodes()
        assert n2 == n1

    def test_incremental_detects_new_file(self, sample_project):
        r1 = run_pipeline(sample_project, embed=False, incremental=True)
        n1 = r1.graph.number_of_nodes()

        # Add a new file
        (sample_project / "new_module.py").write_text(
            "def new_function():\n    pass\n"
        )
        r2 = run_pipeline(sample_project, embed=False, incremental=True)
        assert r2.graph.number_of_nodes() >= n1


class TestExportFormats:
    """Test export functionality after a build."""

    def test_d3_export(self, sample_project, tmp_path):
        from hedwig_cg.cli.main import _graph_to_d3

        result = run_pipeline(sample_project, embed=False)
        d3 = _graph_to_d3(result.graph)
        assert d3["metadata"]["node_count"] > 0
        assert d3["metadata"]["link_count"] >= 0

        # Verify JSON serializable
        out = tmp_path / "graph.json"
        out.write_text(json.dumps(d3, default=str))
        loaded = json.loads(out.read_text())
        assert loaded["metadata"]["node_count"] == d3["metadata"]["node_count"]

    def test_viz_html_generation(self, sample_project, tmp_path):
        from hedwig_cg.cli.main import _build_viz_html, _graph_to_d3

        result = run_pipeline(sample_project, embed=False)
        d3 = _graph_to_d3(result.graph)
        html = _build_viz_html(d3)
        assert "d3.forceSimulation" in html
        assert "AuthHandler" in html or "Server" in html


class TestCleanup:
    """Test database cleanup."""

    def test_clean_removes_db_dir(self, sample_project):
        run_pipeline(sample_project, embed=False)
        kb_dir = sample_project / ".hedwig-cg"
        assert kb_dir.exists()

        shutil.rmtree(kb_dir)
        assert not kb_dir.exists()
