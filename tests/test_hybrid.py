"""Tests for hybrid search and RRF fusion."""

from hedwig_kg.query.hybrid import SearchResult, reciprocal_rank_fusion


class TestRRF:
    def test_single_list(self):
        ranked = [("a", 0.9), ("b", 0.5), ("c", 0.1)]
        fused = reciprocal_rank_fusion(ranked)
        assert fused[0][0] == "a"
        assert fused[1][0] == "b"
        assert fused[2][0] == "c"

    def test_multi_list_fusion(self):
        list1 = [("a", 0.9), ("b", 0.5)]
        list2 = [("b", 0.8), ("c", 0.3)]
        list3 = [("a", 0.7), ("c", 0.6)]
        fused = reciprocal_rank_fusion(list1, list2, list3)
        scores = {item: score for item, score in fused}
        # "a" appears in list1 rank 1 and list3 rank 1 → high score
        # "b" appears in list1 rank 2 and list2 rank 1 → high score
        assert len(scores) == 3
        assert all(s > 0 for s in scores.values())

    def test_item_in_all_lists_ranks_higher(self):
        list1 = [("x", 0.9), ("y", 0.5)]
        list2 = [("x", 0.8), ("z", 0.3)]
        list3 = [("x", 0.7), ("w", 0.6)]
        fused = reciprocal_rank_fusion(list1, list2, list3)
        # "x" is in all three lists, should be ranked first
        assert fused[0][0] == "x"

    def test_empty_lists(self):
        fused = reciprocal_rank_fusion([], [])
        assert fused == []

    def test_rrf_constant(self):
        ranked = [("a", 0.9)]
        fused_k60 = reciprocal_rank_fusion(ranked, k=60)
        fused_k1 = reciprocal_rank_fusion(ranked, k=1)
        # Lower k gives higher individual scores
        assert fused_k1[0][1] > fused_k60[0][1]


class TestSearchResult:
    def test_dataclass(self):
        sr = SearchResult(
            node_id="test::func::foo",
            label="foo",
            kind="function",
            file_path="test.py",
            score=0.95,
            source="fused",
        )
        assert sr.label == "foo"
        assert sr.neighbors == []
