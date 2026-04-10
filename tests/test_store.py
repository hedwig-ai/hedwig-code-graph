"""Tests for SQLite storage and FTS5 search."""


import networkx as nx
import numpy as np

from hedwig_kg.storage.store import KnowledgeStore


def _sample_graph():
    G = nx.DiGraph()
    G.add_node("m::module::app", label="app", kind="module", file_path="app.py",
               language="python", start_line=0, end_line=50,
               docstring="Main application module", signature="",
               source_snippet="import os\nclass App:", pagerank=0.5,
               community_ids=[0])
    G.add_node("m::class::App", label="App", kind="class", file_path="app.py",
               language="python", start_line=2, end_line=40,
               docstring="Application class", signature="class App",
               source_snippet="class App:\n    def run(self):", pagerank=0.3,
               community_ids=[0])
    G.add_node("m::function::main", label="main", kind="function", file_path="app.py",
               language="python", start_line=42, end_line=50,
               docstring="Entry point", signature="def main()",
               source_snippet="def main():\n    app = App()", pagerank=0.2,
               community_ids=[1])
    G.add_edge("m::module::app", "m::class::App", relation="defines", confidence="EXTRACTED")
    G.add_edge("m::module::app", "m::function::main", relation="defines", confidence="EXTRACTED")
    G.add_edge("m::function::main", "m::class::App", relation="calls", confidence="INFERRED")
    return G


class TestKnowledgeStore:
    def test_save_and_load_graph(self, tmp_path):
        db = tmp_path / "test.db"
        store = KnowledgeStore(db)
        G = _sample_graph()
        store.save_graph(G)

        loaded = store.load_graph()
        assert loaded.number_of_nodes() == G.number_of_nodes()
        assert loaded.number_of_edges() == G.number_of_edges()
        assert loaded.nodes["m::class::App"]["label"] == "App"
        store.close()

    def test_fts5_search(self, tmp_path):
        db = tmp_path / "test.db"
        store = KnowledgeStore(db)
        store.save_graph(_sample_graph())

        results = store.keyword_search(["application", "class"], top_k=5)
        assert len(results) > 0
        # "App" should rank high (matches "Application class" docstring)
        labels = [r["label"] for r in results]
        assert "App" in labels or "app" in labels
        store.close()

    def test_fts5_empty_query(self, tmp_path):
        db = tmp_path / "test.db"
        store = KnowledgeStore(db)
        store.save_graph(_sample_graph())
        results = store.keyword_search([], top_k=5)
        assert results == []
        store.close()

    def test_embeddings_roundtrip(self, tmp_path):
        db = tmp_path / "test.db"
        store = KnowledgeStore(db)
        vecs = {
            "node_a": np.array([1.0, 0.0, 0.0], dtype=np.float32),
            "node_b": np.array([0.0, 1.0, 0.0], dtype=np.float32),
        }
        store.save_embeddings(vecs, model_name="test-model")
        loaded = store.load_embeddings()
        assert len(loaded) == 2
        np.testing.assert_array_almost_equal(loaded["node_a"], vecs["node_a"])
        store.close()

    def test_metadata(self, tmp_path):
        db = tmp_path / "test.db"
        store = KnowledgeStore(db)
        store.set_meta("version", "0.1.0")
        assert store.get_meta("version") == "0.1.0"
        assert store.get_meta("missing", "default") == "default"
        store.close()

    def test_vector_search(self, tmp_path):
        db = tmp_path / "test.db"
        store = KnowledgeStore(db)
        vecs = {
            "a": np.array([1.0, 0.0, 0.0], dtype=np.float32),
            "b": np.array([0.9, 0.1, 0.0], dtype=np.float32),
            "c": np.array([0.0, 0.0, 1.0], dtype=np.float32),
        }
        store.save_embeddings(vecs)
        store.build_vector_index(vecs)

        query = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        results = store.vector_search(query, top_k=2)
        assert len(results) == 2
        # "a" should be closest to query
        assert results[0][0] == "a"
        store.close()
