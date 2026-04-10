"""Tests for community summary generation and community-aware search."""

import networkx as nx

from hedwig_kg.core.cluster import (
    ClusterResult,
    Community,
    community_label,
    summarize_communities,
)


def _build_graph():
    """Build a small test graph with known structure."""
    G = nx.DiGraph()
    # Auth module
    G.add_node("auth::module", label="auth", kind="module", file_path="auth.py",
               docstring="Authentication module")
    G.add_node("auth::class::AuthHandler", label="AuthHandler", kind="class",
               file_path="auth.py", docstring="Handles user authentication")
    G.add_node("auth::method::login", label="login", kind="method",
               file_path="auth.py", docstring="Log in a user")
    G.add_node("auth::method::logout", label="logout", kind="method",
               file_path="auth.py")

    # DB module
    G.add_node("db::module", label="db", kind="module", file_path="db.py",
               docstring="Database layer")
    G.add_node("db::class::Connection", label="Connection", kind="class",
               file_path="db.py", docstring="Database connection pool")
    G.add_node("db::method::query", label="query", kind="method",
               file_path="db.py")

    # Edges
    G.add_edge("auth::module", "auth::class::AuthHandler", relation="defines")
    G.add_edge("auth::class::AuthHandler", "auth::method::login", relation="defines")
    G.add_edge("auth::class::AuthHandler", "auth::method::logout", relation="defines")
    G.add_edge("db::module", "db::class::Connection", relation="defines")
    G.add_edge("db::class::Connection", "db::method::query", relation="defines")
    G.add_edge("auth::method::login", "db::method::query", relation="calls")

    return G


def _build_cluster_result():
    """Build a cluster result with two communities."""
    cr = ClusterResult(hierarchy_levels=1)
    cr.communities[0] = Community(
        id=0, level=0, resolution=1.0,
        node_ids=["auth::module", "auth::class::AuthHandler",
                   "auth::method::login", "auth::method::logout"],
    )
    cr.communities[1] = Community(
        id=1, level=0, resolution=1.0,
        node_ids=["db::module", "db::class::Connection", "db::method::query"],
    )
    return cr


class TestCommunitySummary:
    def test_summarize_generates_text(self):
        G = _build_graph()
        cr = _build_cluster_result()
        result = summarize_communities(G, cr)
        assert result.communities[0].summary
        assert result.communities[1].summary

    def test_summary_contains_labels(self):
        G = _build_graph()
        cr = _build_cluster_result()
        summarize_communities(G, cr)
        summary = cr.communities[0].summary
        # Should mention auth-related labels
        assert "AuthHandler" in summary or "auth" in summary

    def test_summary_contains_kind_info(self):
        G = _build_graph()
        cr = _build_cluster_result()
        summarize_communities(G, cr)
        summary = cr.communities[1].summary
        assert "module" in summary or "class" in summary or "method" in summary

    def test_summary_contains_file_info(self):
        G = _build_graph()
        cr = _build_cluster_result()
        summarize_communities(G, cr)
        summary = cr.communities[0].summary
        assert "auth.py" in summary

    def test_does_not_overwrite_existing_summary(self):
        G = _build_graph()
        cr = _build_cluster_result()
        cr.communities[0].summary = "Existing summary"
        summarize_communities(G, cr)
        assert cr.communities[0].summary == "Existing summary"

    def test_community_label(self):
        G = _build_graph()
        cr = _build_cluster_result()
        label = community_label(G, cr.communities[0], max_labels=3)
        assert len(label) > 0
        parts = label.split(", ")
        assert len(parts) <= 3


class TestCommunitySearch:
    def test_community_search_in_pipeline(self, tmp_path):
        """Integration test: build pipeline produces community summaries."""
        from hedwig_kg.core.pipeline import run_pipeline

        src = tmp_path / "src"
        src.mkdir()
        (src / "app.py").write_text(
            "class Application:\n"
            '    """Main application controller."""\n'
            "    def start(self):\n"
            "        pass\n"
            "    def stop(self):\n"
            "        pass\n"
        )
        (src / "handler.py").write_text(
            "from app import Application\n"
            "class RequestHandler:\n"
            '    """Handles HTTP requests."""\n'
            "    def handle(self, req):\n"
            "        pass\n"
        )

        out = tmp_path / "out"
        result = run_pipeline(src, output_dir=out, embed=False)

        # Check communities were generated with summaries
        if result.cluster_result and result.cluster_result.communities:
            for comm in result.cluster_result.communities.values():
                assert comm.summary, f"Community {comm.id} has no summary"
