"""Tests for the MCP server tools.

Verifies that all 5 MCP tools (search, node, stats, communities, build)
return well-formatted output and handle edge cases gracefully.
Uses mocked store/graph to avoid requiring a real database.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import networkx as nx
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_graph() -> nx.DiGraph:
    """Create a small test graph with realistic node attributes."""
    G = nx.DiGraph()
    G.add_node(
        "auth.py::AuthHandler",
        label="AuthHandler",
        kind="class",
        file_path="auth.py",
        signature="class AuthHandler",
        docstring="Handles user authentication.",
        start_line=1,
        end_line=20,
        community_ids=[0],
    )
    G.add_node(
        "auth.py::AuthHandler.login",
        label="login",
        kind="method",
        file_path="auth.py",
        signature="def login(self, username, password)",
        docstring="Authenticate a user.",
        start_line=5,
        end_line=8,
        community_ids=[0],
    )
    G.add_node(
        "server.py::handle_request",
        label="handle_request",
        kind="function",
        file_path="server.py",
        signature="def handle_request(req)",
        docstring="Handle incoming HTTP request.",
        start_line=10,
        end_line=25,
        community_ids=[1],
    )
    # Edges
    G.add_edge(
        "auth.py::AuthHandler",
        "auth.py::AuthHandler.login",
        relation="has_method",
        weight=1.0,
    )
    G.add_edge(
        "server.py::handle_request",
        "auth.py::AuthHandler",
        relation="calls",
        weight=0.8,
    )
    return G


def _make_store(G: nx.DiGraph) -> MagicMock:
    """Create a mock KnowledgeStore."""
    store = MagicMock()
    store.conn = MagicMock()
    # community_search returns list of dicts
    store.community_search.return_value = [
        {
            "community_id": 0,
            "level": 0,
            "score": 0.95,
            "node_ids": ["auth.py::AuthHandler", "auth.py::AuthHandler.login"],
            "summary": "Authentication module with login handling.",
        }
    ]
    return store


@pytest.fixture()
def mock_load():
    """Patch _load to return test graph and store."""
    G = _make_graph()
    store = _make_store(G)
    with patch("hedwig_kg.mcp_server._load", return_value=(store, G)):
        yield store, G


@pytest.fixture()
def mock_load_empty():
    """Patch _load to return empty graph."""
    G = nx.DiGraph()
    store = _make_store(G)
    with patch("hedwig_kg.mcp_server._load", return_value=(store, G)):
        yield store, G


# ---------------------------------------------------------------------------
# Tests: search tool
# ---------------------------------------------------------------------------

class TestSearchTool:
    def test_search_returns_results(self, mock_load):
        from hedwig_kg.mcp_server import search

        mock_results = [
            SimpleNamespace(
                label="AuthHandler",
                kind="class",
                file_path="auth.py",
                start_line=1,
                end_line=20,
                score=0.85,
                signal_contributions={"code_vector": 0.4, "text_vector": 0.3, "keyword": 0.15},
                neighbors=["login", "logout"],
                snippet="class AuthHandler: ...",
            ),
        ]
        with patch("hedwig_kg.query.hybrid.hybrid_search", return_value=mock_results):
            result = search("authentication")

        assert "AuthHandler" in result
        assert "auth.py:1-20" in result
        assert "0.8500" in result
        assert "code_vector" in result

    def test_search_no_results(self, mock_load):
        from hedwig_kg.mcp_server import search

        with patch("hedwig_kg.query.hybrid.hybrid_search", return_value=[]):
            result = search("nonexistent_query_xyz")

        assert "No results found" in result

    def test_search_fast_mode(self, mock_load):
        from hedwig_kg.mcp_server import search

        with patch("hedwig_kg.query.hybrid.hybrid_search", return_value=[]) as mock_hs:
            search("test query", fast=True)
            mock_hs.assert_called_once()
            _, kwargs = mock_hs.call_args
            assert kwargs.get("fast") is True

    def test_search_custom_top_k(self, mock_load):
        from hedwig_kg.mcp_server import search

        with patch("hedwig_kg.query.hybrid.hybrid_search", return_value=[]) as mock_hs:
            search("test", top_k=5)
            _, kwargs = mock_hs.call_args
            assert kwargs.get("top_k") == 5

    def test_search_result_without_end_line(self, mock_load):
        from hedwig_kg.mcp_server import search

        mock_results = [
            SimpleNamespace(
                label="func",
                kind="function",
                file_path="test.py",
                start_line=10,
                end_line=10,  # same as start
                score=0.5,
                signal_contributions={},
                neighbors=[],
                snippet=None,
            ),
        ]
        with patch("hedwig_kg.query.hybrid.hybrid_search", return_value=mock_results):
            result = search("func")

        # Should show just :10 not :10-10
        assert "test.py:10" in result
        assert "10-10" not in result

    def test_search_result_no_line_numbers(self, mock_load):
        from hedwig_kg.mcp_server import search

        mock_results = [
            SimpleNamespace(
                label="readme",
                kind="document",
                file_path="README.md",
                start_line=None,
                end_line=None,
                score=0.3,
                signal_contributions={},
                neighbors=[],
                snippet=None,
            ),
        ]
        with patch("hedwig_kg.query.hybrid.hybrid_search", return_value=mock_results):
            result = search("readme")

        assert "README.md" in result
        assert ":" not in result.split("README.md")[1].split("\n")[0]


# ---------------------------------------------------------------------------
# Tests: node tool
# ---------------------------------------------------------------------------

class TestNodeTool:
    def test_node_exact_match(self, mock_load):
        from hedwig_kg.mcp_server import node

        result = node("auth.py::AuthHandler")
        assert "AuthHandler" in result
        assert "class" in result
        assert "auth.py" in result
        assert "Handles user authentication" in result
        assert "login" in result  # outgoing edge label

    def test_node_partial_match(self, mock_load):
        from hedwig_kg.mcp_server import node

        result = node("AuthHandler")
        assert "AuthHandler" in result

    def test_node_not_found(self, mock_load):
        from hedwig_kg.mcp_server import node

        result = node("NonExistentNode12345")
        assert "No node found" in result

    def test_node_shows_edges(self, mock_load):
        from hedwig_kg.mcp_server import node

        result = node("auth.py::AuthHandler")
        assert "Outgoing edges" in result
        assert "has_method" in result
        assert "w=1.00" in result

    def test_node_shows_incoming_edges(self, mock_load):
        from hedwig_kg.mcp_server import node

        result = node("auth.py::AuthHandler")
        assert "Incoming edges" in result
        assert "calls" in result

    def test_node_case_insensitive_partial(self, mock_load):
        from hedwig_kg.mcp_server import node

        result = node("authhandler")
        assert "AuthHandler" in result

    def test_node_shows_signature(self, mock_load):
        from hedwig_kg.mcp_server import node

        result = node("auth.py::AuthHandler.login")
        assert "def login" in result

    def test_node_shows_line_numbers(self, mock_load):
        from hedwig_kg.mcp_server import node

        result = node("auth.py::AuthHandler.login")
        assert "5" in result
        assert "8" in result


# ---------------------------------------------------------------------------
# Tests: stats tool
# ---------------------------------------------------------------------------

class TestStatsTool:
    def test_stats_basic(self, mock_load):
        from hedwig_kg.mcp_server import stats

        with patch("hedwig_kg.core.analyze.analyze", return_value=SimpleNamespace(god_nodes=[])):
            result = stats()
        assert "3" in result  # 3 nodes
        assert "2" in result  # 2 edges
        assert "class" in result
        assert "method" in result
        assert "function" in result

    def test_stats_shows_communities(self, mock_load):
        from hedwig_kg.mcp_server import stats

        with patch("hedwig_kg.core.analyze.analyze", return_value=SimpleNamespace(god_nodes=[])):
            result = stats()
        assert "Communities" in result

    def test_stats_shows_density(self, mock_load):
        from hedwig_kg.mcp_server import stats

        with patch("hedwig_kg.core.analyze.analyze", return_value=SimpleNamespace(god_nodes=[])):
            result = stats()
        assert "Density" in result

    def test_stats_empty_graph(self, mock_load_empty):
        from hedwig_kg.mcp_server import stats

        with patch("hedwig_kg.core.analyze.analyze", return_value=SimpleNamespace(god_nodes=[])):
            result = stats()
        assert "Nodes" in result
        assert "0" in result


# ---------------------------------------------------------------------------
# Tests: communities tool
# ---------------------------------------------------------------------------

class TestCommunitiesTool:
    def test_communities_search(self, mock_load):
        from hedwig_kg.mcp_server import communities

        result = communities(search_query="auth")
        store, _ = mock_load
        store.community_search.assert_called_once()
        assert "Authentication" in result
        assert "Community 0" in result

    def test_communities_search_no_results(self, mock_load):
        from hedwig_kg.mcp_server import communities

        store, _ = mock_load
        store.community_search.return_value = []
        result = communities(search_query="xyz_nonexistent")
        assert "No communities found" in result

    def test_communities_list_all(self, mock_load):
        from hedwig_kg.mcp_server import communities

        store, _ = mock_load
        # Mock the SQLite query
        mock_row1 = {"id": 0, "level": 0, "summary": "Auth community"}
        mock_row2 = {"id": 1, "level": 0, "summary": "Server community"}
        mock_count = {"c": 2}
        store.conn.execute.return_value.fetchall.return_value = [mock_row1, mock_row2]
        store.conn.execute.return_value.fetchone.return_value = mock_count

        result = communities()
        assert "All Communities" in result
        assert "2 total" in result

    def test_communities_list_empty(self, mock_load):
        from hedwig_kg.mcp_server import communities

        store, _ = mock_load
        store.conn.execute.return_value.fetchall.return_value = []

        result = communities()
        assert "No communities found" in result

    def test_communities_filter_by_level(self, mock_load):
        from hedwig_kg.mcp_server import communities

        store, _ = mock_load
        store.conn.execute.return_value.fetchall.return_value = []

        communities(level=1)
        # Verify the SQL query includes level filter
        call_args = store.conn.execute.call_args_list
        sql_calls = [str(c) for c in call_args]
        assert any("level" in s for s in sql_calls)


# ---------------------------------------------------------------------------
# Tests: build tool
# ---------------------------------------------------------------------------

class TestBuildTool:
    def test_build_success(self, tmp_path):
        from hedwig_kg.mcp_server import build

        # Create a minimal project
        src = tmp_path / "proj"
        src.mkdir()
        (src / "hello.py").write_text("def hello(): pass\n")

        mock_graph = _make_graph()
        mock_result = SimpleNamespace(
            graph=mock_graph,
            detected_files=["hello.py"],
        )
        with patch("hedwig_kg.core.pipeline.run_pipeline", return_value=mock_result), \
             patch("hedwig_kg.mcp_server._reload"):
            result = build(str(src))

        assert "Build Complete" in result
        assert "incremental" in result
        assert "3" in result  # nodes from mock graph

    def test_build_invalid_directory(self):
        from hedwig_kg.mcp_server import build

        result = build("/nonexistent/path/xyz123")
        assert "Error" in result
        assert "not a valid directory" in result

    def test_build_full_mode(self, tmp_path):
        from hedwig_kg.mcp_server import build

        src = tmp_path / "proj"
        src.mkdir()
        (src / "hello.py").write_text("def hello(): pass\n")

        mock_graph = _make_graph()
        mock_result = SimpleNamespace(
            graph=mock_graph,
            detected_files=["hello.py"],
        )
        with patch("hedwig_kg.core.pipeline.run_pipeline", return_value=mock_result) as mock_pipe, \
             patch("hedwig_kg.mcp_server._reload"):
            build(str(src), incremental=False)
            _, kwargs = mock_pipe.call_args
            assert kwargs.get("incremental") is False


# ---------------------------------------------------------------------------
# Tests: _load / _get_db_path helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_get_db_path_env_var(self, tmp_path):
        import hedwig_kg.mcp_server as mod

        db_file = tmp_path / "knowledge.db"
        db_file.touch()
        mod._db_path = None  # reset cache
        with patch.dict("os.environ", {"HEDWIG_KG_DB": str(db_file)}):
            result = mod._get_db_path()
            assert result == str(db_file)
        mod._db_path = None  # cleanup

    def test_get_db_path_cwd_fallback(self, tmp_path):
        import hedwig_kg.mcp_server as mod

        mod._db_path = None
        # Create .hedwig-kg/knowledge.db in tmp_path
        (tmp_path / ".hedwig-kg").mkdir()
        (tmp_path / ".hedwig-kg" / "knowledge.db").touch()
        with patch("hedwig_kg.mcp_server.Path.cwd", return_value=tmp_path), \
             patch.dict("os.environ", {}, clear=True):
            result = mod._get_db_path()
            assert "knowledge.db" in result
        mod._db_path = None

    def test_load_file_not_found(self):
        import hedwig_kg.mcp_server as mod

        mod._store = None
        mod._graph = None
        mod._db_path = None
        with patch("hedwig_kg.mcp_server._get_db_path", return_value="/fake/path/knowledge.db"):
            with pytest.raises(FileNotFoundError, match="Run 'hedwig-kg build"):
                mod._load()

    def test_reload_clears_cache(self):
        import hedwig_kg.mcp_server as mod

        mod._store = "old"
        mod._graph = "old"
        with patch("hedwig_kg.mcp_server._load", return_value=("new_store", "new_graph")) as mock_l:
            mod._reload()
            assert mod._store is None or mock_l.called
