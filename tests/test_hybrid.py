"""Tests for hybrid search and RRF fusion."""

from hedwig_cg.query.hybrid import (
    SearchEdge,
    SearchGraph,
    SearchResult,
    reciprocal_rank_fusion,
)


class TestRRF:
    def test_single_list(self):
        ranked = [("a", 0.9), ("b", 0.5), ("c", 0.1)]
        fused, breakdowns = reciprocal_rank_fusion(ranked)
        assert fused[0][0] == "a"
        assert fused[1][0] == "b"
        assert fused[2][0] == "c"
        # Breakdowns should have entries for all items
        assert "a" in breakdowns
        assert len(breakdowns["a"]) > 0

    def test_multi_list_fusion(self):
        list1 = [("a", 0.9), ("b", 0.5)]
        list2 = [("b", 0.8), ("c", 0.3)]
        list3 = [("a", 0.7), ("c", 0.6)]
        fused, breakdowns = reciprocal_rank_fusion(list1, list2, list3)
        scores = {item: score for item, score in fused}
        assert len(scores) == 3
        assert all(s > 0 for s in scores.values())

    def test_item_in_all_lists_ranks_higher(self):
        list1 = [("x", 0.9), ("y", 0.5)]
        list2 = [("x", 0.8), ("z", 0.3)]
        list3 = [("x", 0.7), ("w", 0.6)]
        fused, breakdowns = reciprocal_rank_fusion(
            list1, list2, list3,
            signal_names=["s1", "s2", "s3"],
        )
        assert fused[0][0] == "x"
        assert len(breakdowns["x"]) == 3

    def test_empty_lists(self):
        fused, breakdowns = reciprocal_rank_fusion([], [])
        assert fused == []
        assert breakdowns == {}

    def test_rrf_constant(self):
        ranked = [("a", 0.9)]
        fused_k60, _ = reciprocal_rank_fusion(ranked, k=60)
        fused_k1, _ = reciprocal_rank_fusion(ranked, k=1)
        assert fused_k1[0][1] > fused_k60[0][1]


class TestSearchResult:
    def test_dataclass(self):
        sr = SearchResult(
            node_id="test.py:1",
            label="foo",
            kind="function",
            file_path="test.py",
            score=0.95,
            source="seed",
        )
        assert sr.label == "foo"
        assert sr.signal_contributions == {}


class TestSearchGraph:
    def test_graph_structure(self):
        nodes = [
            SearchResult(node_id="a", label="a", kind="function",
                         file_path="a.py", score=0.9, source="seed"),
            SearchResult(node_id="b", label="b", kind="function",
                         file_path="b.py", score=0.8, source="seed"),
            SearchResult(node_id="m", label="m", kind="module",
                         file_path="m.py", score=0.0, source="path"),
        ]
        edges = [
            SearchEdge(source="a", target="m", relation="defines"),
            SearchEdge(source="m", target="b", relation="co_change"),
        ]
        sg = SearchGraph(nodes=nodes, edges=edges)
        assert len(sg.nodes) == 3
        assert len(sg.edges) == 2
        seed_nodes = [n for n in sg.nodes if n.source == "seed"]
        path_nodes = [n for n in sg.nodes if n.source == "path"]
        assert len(seed_nodes) == 2
        assert len(path_nodes) == 1
