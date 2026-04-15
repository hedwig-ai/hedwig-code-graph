"""Tests for graph building and PageRank."""

import networkx as nx

from hedwig_cg.core.build import build_graph, compute_pagerank, graph_stats
from hedwig_cg.core.extract import ExtractedEdge, ExtractedNode, ExtractionResult


def _make_extractions():
    """Create sample extractions for testing."""
    ext1 = ExtractionResult(
        nodes=[
            ExtractedNode(id="a.py:0", name="a", kind="module",
                          file_path="a.py", language="python"),
            ExtractedNode(id="a.py:1", name="Foo", kind="class",
                          file_path="a.py", language="python", start_line=1),
            ExtractedNode(id="a.py:10", name="bar", kind="function",
                          file_path="a.py", language="python", start_line=10),
        ],
        edges=[
            ExtractedEdge("a.py:0", "a.py:1", "defines"),
            ExtractedEdge("a.py:0", "a.py:10", "defines"),
            ExtractedEdge("a.py:10", "*::class::Foo", "calls"),
        ],
    )
    ext2 = ExtractionResult(
        nodes=[
            ExtractedNode(id="b.py:0", name="b", kind="module",
                          file_path="b.py", language="python"),
            ExtractedNode(id="b.py:5", name="Baz", kind="class",
                          file_path="b.py", language="python", start_line=5),
        ],
        edges=[
            ExtractedEdge("b.py:0", "b.py:5", "defines"),
            ExtractedEdge("b.py:5", "*::class::Foo", "inherits"),
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
        # *::class::Foo should resolve to a.py:1
        assert G.has_edge("a.py:10", "a.py:1")
        assert G.has_edge("b.py:5", "a.py:1")

    def test_node_attributes(self):
        G = build_graph(_make_extractions())
        data = G.nodes["a.py:1"]
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


class TestMergeTier3Nodes:
    def test_constructor_merged_into_class(self):
        from hedwig_cg.core.build import merge_tier3_nodes
        G = nx.DiGraph()
        G.add_node("a.py:1", label="Foo", kind="class", file_path="a.py",
                    language="python", start_line=1, end_line=20, docstring="", signature="",
                    source_snippet="", decorators=[])
        G.add_node("a.py:2", label="__init__", kind="constructor",
                    file_path="a.py", language="python", start_line=2, end_line=5,
                    docstring="Initialize Foo.", signature="def __init__(self, x)",
                    source_snippet="", decorators=[])
        G.add_edge("a.py:1", "a.py:2", relation="defines",
                   confidence="EXTRACTED")
        G = merge_tier3_nodes(G)
        assert "a.py:2" not in G.nodes
        assert G.nodes["a.py:1"]["signature"] == "def __init__(self, x)"
        assert G.nodes["a.py:1"]["docstring"] == "Initialize Foo."

    def test_variable_merged_into_module(self):
        from hedwig_cg.core.build import merge_tier3_nodes
        G = nx.DiGraph()
        G.add_node("a.py:0", label="a", kind="module", file_path="a.py",
                    language="python", start_line=0, end_line=0, docstring="", signature="",
                    source_snippet="", decorators=[])
        G.add_node("a.py:3", label="X", kind="variable", file_path="a.py",
                    language="python", start_line=3, end_line=3, docstring="", signature="",
                    source_snippet="", decorators=[])
        G.add_edge("a.py:0", "a.py:3", relation="defines",
                   confidence="EXTRACTED")
        G = merge_tier3_nodes(G)
        assert "a.py:3" not in G.nodes
        assert "X" in G.nodes["a.py:0"].get("merged_members", [])

    def test_external_nodes_removed(self):
        from hedwig_cg.core.build import merge_tier3_nodes
        G = nx.DiGraph()
        G.add_node("a.py:0", label="a", kind="module", file_path="a.py",
                    language="python", start_line=0, end_line=0, docstring="", signature="",
                    source_snippet="", decorators=[])
        G.add_node("external::requests", label="requests", kind="external", file_path="",
                    language="")
        G.add_edge("a.py:0", "external::requests", relation="imports",
                   confidence="INFERRED")
        G = merge_tier3_nodes(G)
        assert "external::requests" not in G.nodes

    def test_edges_redirected(self):
        from hedwig_cg.core.build import merge_tier3_nodes
        G = nx.DiGraph()
        G.add_node("a.py:1", label="Foo", kind="class", file_path="a.py",
                    language="python", start_line=1, end_line=20, docstring="", signature="",
                    source_snippet="", decorators=[])
        G.add_node("a.py:2", label="__init__", kind="constructor",
                    file_path="a.py", language="python", start_line=2, end_line=5,
                    docstring="", signature="def __init__(self)",
                    source_snippet="", decorators=[])
        G.add_node("b.py:1", label="bar", kind="function", file_path="b.py",
                    language="python", start_line=1, end_line=5, docstring="", signature="",
                    source_snippet="", decorators=[])
        G.add_edge("a.py:1", "a.py:2", relation="defines",
                   confidence="EXTRACTED")
        G.add_edge("a.py:2", "b.py:1", relation="calls",
                   confidence="EXTRACTED")
        G = merge_tier3_nodes(G)
        # constructorのcalls→barがclassにリダイレクトされるべき
        assert G.has_edge("a.py:1", "b.py:1")


class TestGraphStats:
    def test_stats_keys(self):
        G = build_graph(_make_extractions())
        stats = graph_stats(G)
        assert "nodes" in stats
        assert "edges" in stats
        assert "density" in stats
        assert "components" in stats
