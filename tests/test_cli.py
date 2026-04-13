"""Tests for CLI commands — smoke tests and basic functionality."""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
from click.testing import CliRunner

from hedwig_cg.cli.main import cli
from hedwig_cg.storage.store import KnowledgeStore


def _create_test_project(tmp_path: Path) -> Path:
    """Create a minimal test project with Python files."""
    src = tmp_path / "project"
    src.mkdir()
    (src / "main.py").write_text(
        "from app import App\n\n"
        "def main():\n"
        "    app = App()\n"
        "    app.run()\n"
    )
    (src / "app.py").write_text(
        "class App:\n"
        '    """Application class."""\n'
        "    def run(self):\n"
        "        pass\n"
    )
    return src


def _create_test_db(tmp_path: Path) -> Path:
    """Create a pre-built knowledge base for search/stats/export tests."""
    db_dir = tmp_path / ".hedwig-cg"
    db_dir.mkdir()
    db_path = db_dir / "knowledge.db"

    store = KnowledgeStore(db_path)
    G = nx.DiGraph()
    G.add_node(
        "m::module::app", label="app", kind="module", file_path="app.py",
        language="python", start_line=0, end_line=10,
        docstring="App module", signature="", source_snippet="class App:",
        pagerank=0.5, community_ids=[0],
    )
    G.add_node(
        "m::class::App", label="App", kind="class", file_path="app.py",
        language="python", start_line=1, end_line=8,
        docstring="Application class", signature="class App",
        source_snippet="class App:\n    def run(self):", pagerank=0.3,
        community_ids=[0],
    )
    G.add_edge("m::module::app", "m::class::App", relation="defines",
               confidence="EXTRACTED")
    store.save_graph(G)

    from hedwig_cg.core.cluster import Community
    communities = {
        0: Community(id=0, level=0, resolution=1.0,
                     node_ids=["m::module::app", "m::class::App"],
                     summary="app, App"),
    }
    store.save_communities(communities)
    store.set_meta("source_dir", str(tmp_path))
    store.set_meta("status", "complete")
    store.close()
    return tmp_path


class TestCLIHelp:
    """Test that all commands show help without errors."""

    def test_main_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "hedwig-cg" in result.output

    def test_build_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["build", "--help"])
        assert result.exit_code == 0
        assert "SOURCE_DIR" in result.output

    def test_search_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["search", "--help"])
        assert result.exit_code == 0
        assert "QUERY" in result.output

    def test_stats_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["stats", "--help"])
        assert result.exit_code == 0

    def test_export_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["export", "--help"])
        assert result.exit_code == 0
        assert "json" in result.output.lower() or "graphml" in result.output.lower()

    def test_node_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["node", "--help"])
        assert result.exit_code == 0
        assert "NODE_ID" in result.output

    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "hedwig-cg" in result.output


class TestCLIBuild:
    """Test the build command."""

    def test_build_basic(self, tmp_path):
        src = _create_test_project(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["build", str(src),
                                     "--output", str(tmp_path / "out")])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "nodes" in data
        assert (tmp_path / "out" / "knowledge.db").exists()

    def test_build_nonexistent_dir(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["build", "/nonexistent/path"])
        assert result.exit_code != 0


class TestCLIStats:
    """Test the stats command."""

    def test_stats_with_db(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["stats", "--source-dir", str(project_dir)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "nodes" in data
        assert "edges" in data

    def test_stats_shows_graph_quality(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["stats", "--source-dir", str(project_dir)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "density" in data
        assert "connected_components" in data
        assert "avg_clustering_coeff" in data

    def test_stats_no_db(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["stats", "--source-dir", str(tmp_path)])
        assert result.exit_code != 0


class TestCLIExport:
    """Test the export command."""

    def test_export_json(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        out_file = tmp_path / "export.json"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "export", "--source-dir", str(project_dir),
            "--format", "json", "-o", str(out_file),
        ])
        assert result.exit_code == 0
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert "nodes" in data or "links" in data

    def test_export_graphml(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        out_file = tmp_path / "export.graphml"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "export", "--source-dir", str(project_dir),
            "--format", "graphml", "-o", str(out_file),
        ])
        assert result.exit_code == 0
        assert out_file.exists()


class TestCLICommunities:
    """Test the communities command."""

    def test_communities_list(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["communities", "--source-dir", str(project_dir)])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_communities_search(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "communities", "--source-dir", str(project_dir),
            "--search", "app",
        ])
        assert result.exit_code == 0

    def test_communities_no_db(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["communities", "--source-dir", str(tmp_path)])
        assert result.exit_code != 0

    def test_communities_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["communities", "--help"])
        assert result.exit_code == 0


class TestCLISearch:
    """Test the search command."""

    def test_search_no_db(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "search", "test query",
            "--source-dir", str(tmp_path),
        ])
        assert result.exit_code != 0

    def test_search_keyword(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "search", "App",
            "--source-dir", str(project_dir),
        ])
        # May return results or "No results" depending on vector index
        assert result.exit_code == 0


class TestCLIExportD3:
    """Test D3 export format."""

    def test_export_d3(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        out_file = tmp_path / "graph_d3.json"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "export", "--source-dir", str(project_dir),
            "--format", "d3", "-o", str(out_file),
        ])
        assert result.exit_code == 0
        assert out_file.exists()
        data = json.loads(out_file.read_text())
        assert "nodes" in data
        assert "links" in data
        assert "metadata" in data
        assert data["metadata"]["node_count"] == 2


class TestCLIVisualize:
    """Test the visualize command."""

    def test_visualize_creates_html(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        out_file = tmp_path / "viz.html"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "visualize", "--source-dir", str(project_dir),
            "-o", str(out_file),
        ])
        assert result.exit_code == 0
        assert out_file.exists()
        html = out_file.read_text()
        assert "d3.forceSimulation" in html

    def test_visualize_offline(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        out_file = tmp_path / "viz_offline.html"
        runner = CliRunner()
        result = runner.invoke(cli, [
            "visualize", "--source-dir", str(project_dir),
            "--offline", "-o", str(out_file),
        ])
        assert result.exit_code == 0
        assert out_file.exists()
        html = out_file.read_text()
        # CDN script tag should be replaced (D3 source itself contains the URL)
        assert '<script src="https://d3js.org/d3.v7.min.js">' not in html
        assert len(html) > 280000  # ~280KB D3 inlined
        assert "d3.forceSimulation" in html
        assert "Offline mode" in result.output or "offline" in result.output.lower()

    def test_visualize_no_db(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "visualize", "--source-dir", str(tmp_path),
        ])
        assert result.exit_code != 0

    def test_visualize_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["visualize", "--help"])
        assert result.exit_code == 0
        assert "max-nodes" in result.output
        assert "offline" in result.output


class TestCLIQuery:
    """Test the query REPL command."""

    def test_query_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["query", "--help"])
        assert result.exit_code == 0
        assert "Interactive search REPL" in result.output

    def test_query_no_db(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, ["query", "--source-dir", str(tmp_path)])
        assert result.exit_code != 0

    def test_query_exit_immediately(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "query", "--source-dir", str(project_dir),
        ], input=":quit\n")
        assert result.exit_code == 0
        data = json.loads(result.output.splitlines()[0])
        assert data["status"] == "ready"
        assert "session_ended" in result.output

    def test_query_search_and_exit(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "query", "--source-dir", str(project_dir),
        ], input="App\nexit\n")
        assert result.exit_code == 0
        data = json.loads(result.output.splitlines()[0])
        assert data["status"] == "ready"

    def test_query_stats_command(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "query", "--source-dir", str(project_dir),
        ], input=":stats\n:quit\n")
        assert result.exit_code == 0
        assert '"nodes":' in result.output

    def test_query_node_command(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "query", "--source-dir", str(project_dir),
        ], input=":node App\n:quit\n")
        assert result.exit_code == 0
        # Should show node details or "not found"
        assert "App" in result.output or "not found" in result.output


class TestCLIClean:
    """Test the clean command."""

    def test_clean_removes_db(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        kb_dir = project_dir / ".hedwig-cg"
        assert kb_dir.exists()
        runner = CliRunner()
        result = runner.invoke(cli, [
            "clean", "--source-dir", str(project_dir), "--yes",
        ])
        assert result.exit_code == 0
        assert not kb_dir.exists()

    def test_clean_no_db(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(cli, [
            "clean", "--source-dir", str(tmp_path), "--yes",
        ])
        assert result.exit_code == 0
        assert "No .hedwig-cg/" in result.output

    def test_clean_specific_file(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        db_file = project_dir / ".hedwig-cg" / "knowledge.db"
        assert db_file.exists()
        runner = CliRunner()
        result = runner.invoke(cli, [
            "clean", "--db", str(db_file), "--yes",
        ])
        assert result.exit_code == 0
        assert not db_file.exists()

    def test_clean_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["clean", "--help"])
        assert result.exit_code == 0
        assert "yes" in result.output


class TestCLINode:
    """Test the node command."""

    def test_node_exact_match(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "node", "m::class::App",
            "--source-dir", str(project_dir),
        ])
        assert result.exit_code == 0
        assert "App" in result.output

    def test_node_fuzzy_match(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "node", "App",
            "--source-dir", str(project_dir),
        ])
        assert result.exit_code == 0
        assert "App" in result.output

    def test_node_not_found(self, tmp_path):
        project_dir = _create_test_db(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, [
            "node", "NonExistentNode12345",
            "--source-dir", str(project_dir),
        ])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "not found" in data["error"].lower()


# ---------------------------------------------------------------------------
# Cline integration tests
# ---------------------------------------------------------------------------

class TestClineIntegration:
    def test_cline_install_creates_rules(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["cline", "install"])
            assert result.exit_code == 0
            rules = Path(".clinerules")
            assert rules.exists()
            content = rules.read_text()
            assert "hedwig-cg" in content
            assert "HybridRAG" in content

    def test_cline_install_idempotent(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["cline", "install"])
            result = runner.invoke(cli, ["cline", "install"])
            assert result.exit_code == 0
            assert "already" in result.output.lower()

    def test_cline_install_appends_to_existing(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            Path(".clinerules").write_text("# Existing rules\nDo stuff.\n")
            result = runner.invoke(cli, ["cline", "install"])
            assert result.exit_code == 0
            content = Path(".clinerules").read_text()
            assert "Existing rules" in content
            assert "hedwig-cg" in content

    def test_cline_uninstall(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            runner.invoke(cli, ["cline", "install"])
            result = runner.invoke(cli, ["cline", "uninstall"])
            assert result.exit_code == 0

    def test_cline_uninstall_no_file(self, tmp_path):
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(cli, ["cline", "uninstall"])
            assert result.exit_code == 0
            assert "not found" in result.output.lower()
