"""Tests for graph building and PageRank."""

import networkx as nx

from hedwig_cg.core.build import build_graph, compute_pagerank, graph_stats
from hedwig_cg.core.extract import ExtractedEdge, ExtractedNode, ExtractionResult


def _make_extractions():
    """Create sample extractions for testing."""
    ext1 = ExtractionResult(
        nodes=[
            ExtractedNode(id="a.py::module::a", name="a", kind="module",
                          file_path="a.py", language="python"),
            ExtractedNode(id="a.py::class::Foo", name="Foo", kind="class",
                          file_path="a.py", language="python"),
            ExtractedNode(id="a.py::function::bar", name="bar", kind="function",
                          file_path="a.py", language="python"),
        ],
        edges=[
            ExtractedEdge("a.py::module::a", "a.py::class::Foo", "defines"),
            ExtractedEdge("a.py::module::a", "a.py::function::bar", "defines"),
            ExtractedEdge("a.py::function::bar", "*::class::Foo", "calls"),
        ],
    )
    ext2 = ExtractionResult(
        nodes=[
            ExtractedNode(id="b.py::module::b", name="b", kind="module",
                          file_path="b.py", language="python"),
            ExtractedNode(id="b.py::class::Baz", name="Baz", kind="class",
                          file_path="b.py", language="python"),
        ],
        edges=[
            ExtractedEdge("b.py::module::b", "b.py::class::Baz", "defines"),
            ExtractedEdge("b.py::class::Baz", "*::class::Foo", "inherits"),
        ],
    )
    return [ext1, ext2]


class TestBuildGraph:
    def test_basic_build(self):
        G = build_graph(_make_extractions())
        assert isinstance(G, nx.DiGraph)
        assert G.number_of_nodes() >= 4
        assert G.number_of_edges() >= 4

    def test_wildcard_resolution(self):
        G = build_graph(_make_extractions())
        # *::class::Foo should resolve to a.py::class::Foo
        assert G.has_edge("a.py::function::bar", "a.py::class::Foo")
        assert G.has_edge("b.py::class::Baz", "a.py::class::Foo")

    def test_node_attributes(self):
        G = build_graph(_make_extractions())
        data = G.nodes["a.py::class::Foo"]
        assert data["label"] == "Foo"
        assert data["kind"] == "class"

    def test_no_duplicate_nodes(self):
        exts = _make_extractions()
        G = build_graph(exts + exts)  # Duplicate extractions
        node_ids = list(G.nodes())
        assert len(node_ids) == len(set(node_ids))


class TestPageRank:
    def test_returns_scores(self):
        G = build_graph(_make_extractions())
        pr = compute_pagerank(G)
        assert len(pr) == G.number_of_nodes()
        assert all(0 <= v <= 1 for v in pr.values())

    def test_empty_graph(self):
        pr = compute_pagerank(nx.DiGraph())
        assert pr == {}


class TestGraphStats:
    def test_stats_keys(self):
        G = build_graph(_make_extractions())
        stats = graph_stats(G)
        assert "nodes" in stats
        assert "edges" in stats
        assert "density" in stats
        assert "components" in stats
