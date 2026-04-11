"""Tests for graph visualization export features."""

from __future__ import annotations

import json

import networkx as nx

from hedwig_cg.cli.main import _build_viz_html, _graph_to_d3


def _make_graph() -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_node("mod::ClassA", label="ClassA", kind="class",
               file_path="src/a.py", pagerank=0.5, community_ids=[0])
    G.add_node("mod::func_b", label="func_b", kind="function",
               file_path="src/b.py", pagerank=0.1, community_ids=[1])
    G.add_node("mod::ClassA::method_x", label="method_x", kind="method",
               file_path="src/a.py", pagerank=0.3, community_ids=[0])
    G.add_edge("mod::ClassA", "mod::ClassA::method_x",
               relation="HAS_METHOD", weight=1.0)
    G.add_edge("mod::func_b", "mod::ClassA",
               relation="CALLS", weight=0.8)
    return G


class TestGraphToD3:
    def test_basic_structure(self):
        d3 = _graph_to_d3(_make_graph())
        assert "nodes" in d3
        assert "links" in d3
        assert "metadata" in d3

    def test_node_count(self):
        d3 = _graph_to_d3(_make_graph())
        assert len(d3["nodes"]) == 3
        assert d3["metadata"]["node_count"] == 3

    def test_link_count(self):
        d3 = _graph_to_d3(_make_graph())
        assert len(d3["links"]) == 2
        assert d3["metadata"]["link_count"] == 2

    def test_node_has_required_fields(self):
        d3 = _graph_to_d3(_make_graph())
        for node in d3["nodes"]:
            assert "id" in node
            assert "label" in node
            assert "kind" in node
            assert "group" in node
            assert "size" in node

    def test_link_has_required_fields(self):
        d3 = _graph_to_d3(_make_graph())
        for link in d3["links"]:
            assert "source" in link
            assert "target" in link
            assert "relation" in link
            assert "value" in link

    def test_group_assignment(self):
        d3 = _graph_to_d3(_make_graph())
        kind_groups = d3["metadata"]["kind_groups"]
        assert "class" in kind_groups
        assert "function" in kind_groups
        assert "method" in kind_groups
        # Groups should be unique integers
        groups = list(kind_groups.values())
        assert len(groups) == len(set(groups))

    def test_node_size_scales_with_pagerank(self):
        d3 = _graph_to_d3(_make_graph())
        nodes_by_id = {n["id"]: n for n in d3["nodes"]}
        # ClassA has highest pagerank (0.5), func_b lowest (0.1)
        assert nodes_by_id["mod::ClassA"]["size"] > nodes_by_id["mod::func_b"]["size"]

    def test_empty_graph(self):
        d3 = _graph_to_d3(nx.DiGraph())
        assert d3["nodes"] == []
        assert d3["links"] == []
        assert d3["metadata"]["node_count"] == 0

    def test_json_serializable(self):
        d3 = _graph_to_d3(_make_graph())
        serialized = json.dumps(d3, default=str)
        parsed = json.loads(serialized)
        assert parsed["metadata"]["node_count"] == 3


class TestBuildVizHtml:
    def test_html_contains_d3_script(self):
        d3 = _graph_to_d3(_make_graph())
        html = _build_viz_html(d3)
        assert "d3.v7.min.js" in html
        assert "d3.forceSimulation" in html

    def test_html_contains_graph_data(self):
        d3 = _graph_to_d3(_make_graph())
        html = _build_viz_html(d3)
        assert "ClassA" in html
        assert "func_b" in html

    def test_html_contains_legend(self):
        d3 = _graph_to_d3(_make_graph())
        html = _build_viz_html(d3)
        assert "class" in html
        assert "function" in html

    def test_html_is_valid_structure(self):
        d3 = _graph_to_d3(_make_graph())
        html = _build_viz_html(d3)
        assert html.startswith("<!DOCTYPE html>")
        assert "</html>" in html
        assert "<svg>" in html
