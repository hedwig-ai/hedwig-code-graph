"""Unified storage: SQLite for graph/metadata + FAISS for vector similarity.

All data stays local. No external database required.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

import networkx as nx
import numpy as np

logger = logging.getLogger(__name__)


class KnowledgeStore:
    """Local-first knowledge store combining SQLite + FAISS vector index."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._faiss_index = None
        self._faiss_labels: list[str] = []
        self._embedding_dim: int = 0

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._init_schema()
        return self._conn

    def _init_schema(self) -> None:
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                kind TEXT NOT NULL,
                file_path TEXT,
                language TEXT,
                start_line INTEGER DEFAULT 0,
                end_line INTEGER DEFAULT 0,
                docstring TEXT DEFAULT '',
                signature TEXT DEFAULT '',
                source_snippet TEXT DEFAULT '',
                pagerank REAL DEFAULT 0.0,
                community_ids TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS edges (
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                relation TEXT NOT NULL,
                confidence TEXT DEFAULT 'EXTRACTED',
                weight REAL DEFAULT 1.0,
                PRIMARY KEY (source, target, relation)
            );

            CREATE TABLE IF NOT EXISTS communities (
                id INTEGER PRIMARY KEY,
                level INTEGER NOT NULL,
                resolution REAL NOT NULL,
                summary TEXT DEFAULT '',
                parent_id INTEGER,
                label TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS embeddings (
                node_id TEXT PRIMARY KEY,
                vector BLOB NOT NULL,
                model TEXT DEFAULT '',
                updated_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
            CREATE INDEX IF NOT EXISTS idx_nodes_file ON nodes(file_path);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target);
            CREATE INDEX IF NOT EXISTS idx_communities_level ON communities(level);
        """)

        # FTS5 virtual table for full-text search (separate statement)
        try:
            self.conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
                    node_id UNINDEXED,
                    label,
                    kind UNINDEXED,
                    file_path,
                    docstring,
                    signature,
                    source_snippet,
                    tokenize='porter unicode61'
                )
            """)
        except Exception:
            logger.debug("FTS5 not available in this SQLite build", exc_info=True)

    # --- Graph persistence ---

    def save_graph(self, G: nx.DiGraph) -> None:
        """Persist a NetworkX graph to SQLite."""
        c = self.conn.cursor()
        c.execute("DELETE FROM nodes")
        c.execute("DELETE FROM edges")

        for node_id, data in G.nodes(data=True):
            c.execute(
                """INSERT OR REPLACE INTO nodes
                   (id, label, kind, file_path, language, start_line, end_line,
                    docstring, signature, source_snippet, pagerank, community_ids, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    node_id,
                    data.get("label", ""),
                    data.get("kind", ""),
                    data.get("file_path", ""),
                    data.get("language", ""),
                    data.get("start_line", 0),
                    data.get("end_line", 0),
                    data.get("docstring", ""),
                    data.get("signature", ""),
                    data.get("source_snippet", ""),
                    data.get("pagerank", 0.0),
                    json.dumps(data.get("community_ids", [])),
                    json.dumps({k: v for k, v in data.items()
                                if k not in ("label", "kind", "file_path", "language",
                                             "start_line", "end_line", "docstring",
                                             "signature", "source_snippet", "pagerank",
                                             "community_ids")}),
                ),
            )

        for u, v, data in G.edges(data=True):
            c.execute(
                """INSERT OR REPLACE INTO edges (source, target, relation, confidence, weight)
                   VALUES (?, ?, ?, ?, ?)""",
                (u, v, data.get("relation", ""), data.get("confidence", "EXTRACTED"),
                 data.get("weight", 1.0)),
            )

        # Populate FTS5 index
        self._rebuild_fts(c, G)

        self.conn.commit()

    def load_graph(self) -> nx.DiGraph:
        """Load graph from SQLite back into NetworkX."""
        G = nx.DiGraph()
        for row in self.conn.execute("SELECT * FROM nodes"):
            G.add_node(
                row["id"],
                label=row["label"],
                kind=row["kind"],
                file_path=row["file_path"],
                language=row["language"],
                start_line=row["start_line"],
                end_line=row["end_line"],
                docstring=row["docstring"],
                signature=row["signature"],
                source_snippet=row["source_snippet"],
                pagerank=row["pagerank"],
                community_ids=json.loads(row["community_ids"]),
            )
        for row in self.conn.execute("SELECT * FROM edges"):
            G.add_edge(
                row["source"], row["target"],
                relation=row["relation"],
                confidence=row["confidence"],
                weight=row["weight"],
            )
        return G

    # --- Embedding / Vector persistence ---

    def save_embeddings(self, embeddings: dict[str, np.ndarray], model_name: str = "") -> None:
        """Save node embeddings to SQLite."""
        c = self.conn.cursor()
        for node_id, vec in embeddings.items():
            c.execute(
                """INSERT OR REPLACE INTO embeddings (node_id, vector, model)
                   VALUES (?, ?, ?)""",
                (node_id, vec.tobytes(), model_name),
            )
        self.conn.commit()

    def load_embeddings(self) -> dict[str, np.ndarray]:
        """Load embeddings from SQLite."""
        result = {}
        rows = self.conn.execute("SELECT node_id, vector FROM embeddings").fetchall()
        if not rows:
            return result
        for row in rows:
            result[row["node_id"]] = np.frombuffer(row["vector"], dtype=np.float32)
        return result

    def build_vector_index(self, embeddings: dict[str, np.ndarray] | None = None) -> None:
        """Build FAISS index for vector similarity search.

        Uses IndexFlatIP (inner product) on L2-normalized vectors,
        which is equivalent to cosine similarity.
        """
        import faiss

        if embeddings is None:
            embeddings = self.load_embeddings()

        if not embeddings:
            return

        labels = list(embeddings.keys())
        vectors = np.array([embeddings[lb] for lb in labels], dtype=np.float32)
        dim = vectors.shape[1]

        # L2 normalize → inner product == cosine similarity
        faiss.normalize_L2(vectors)

        index = faiss.IndexFlatIP(dim)
        index.add(vectors)

        self._faiss_index = index
        self._faiss_labels = labels
        self._embedding_dim = dim

    def vector_search(self, query_vec: np.ndarray, top_k: int = 10) -> list[tuple[str, float]]:
        """Search for nearest neighbors using FAISS index.

        Returns:
            List of (node_id, cosine_similarity) tuples, sorted by similarity desc.
        """
        import faiss

        if self._faiss_index is None:
            self.build_vector_index()

        if self._faiss_index is None or not self._faiss_labels:
            return []

        k = min(top_k, len(self._faiss_labels))
        qvec = query_vec.reshape(1, -1).astype(np.float32).copy()
        faiss.normalize_L2(qvec)

        scores, indices = self._faiss_index.search(qvec, k)

        results = []
        for idx, score in zip(indices[0], scores[0]):
            if 0 <= idx < len(self._faiss_labels):
                results.append((self._faiss_labels[idx], float(score)))
        return results

    # --- Community persistence ---

    def save_communities(self, communities: dict) -> None:
        """Save community data to SQLite."""
        c = self.conn.cursor()
        c.execute("DELETE FROM communities")
        for comm_id, comm in communities.items():
            c.execute(
                """INSERT INTO communities (id, level, resolution, summary, parent_id, label)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (comm.id, comm.level, comm.resolution, comm.summary,
                 comm.parent_id, getattr(comm, "label_text", "")),
            )
        self.conn.commit()

    def community_search(
        self, terms: list[str], top_k: int = 5,
    ) -> list[dict]:
        """Search community summaries and return member node IDs.

        Returns list of dicts with keys: community_id, summary, level, node_ids.
        """
        if not terms:
            return []

        rows = self.conn.execute(
            "SELECT id, level, resolution, summary FROM communities ORDER BY level"
        ).fetchall()

        scored = []
        for row in rows:
            summary = (row["summary"] or "").lower()
            score = sum(1 for t in terms if t.lower() in summary)
            if score > 0:
                scored.append((dict(row), score))

        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for row_dict, score in scored[:top_k]:
            comm_id = row_dict["id"]
            # Get member node IDs from the nodes table
            members = self.conn.execute(
                "SELECT id FROM nodes WHERE community_ids LIKE ?",
                (f"%{comm_id}%",),
            ).fetchall()
            results.append({
                "community_id": comm_id,
                "summary": row_dict["summary"],
                "level": row_dict["level"],
                "node_ids": [m["id"] for m in members],
                "score": score,
            })

        return results

    # --- Metadata ---

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()

    def get_meta(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM metadata WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    # --- FTS5 helpers ---

    def _rebuild_fts(self, cursor, G: nx.DiGraph) -> None:
        """Rebuild the FTS5 index from the current graph."""
        try:
            cursor.execute("DELETE FROM nodes_fts")
            for node_id, data in G.nodes(data=True):
                cursor.execute(
                    """INSERT INTO nodes_fts
                       (node_id, label, kind, file_path, docstring, signature, source_snippet)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        node_id,
                        data.get("label", ""),
                        data.get("kind", ""),
                        data.get("file_path", ""),
                        data.get("docstring", ""),
                        data.get("signature", ""),
                        data.get("source_snippet", "")[:500],
                    ),
                )
        except Exception:
            logger.debug("FTS5 not available, skipping index rebuild", exc_info=True)

    def _has_fts(self) -> bool:
        """Check if FTS5 table exists."""
        row = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='nodes_fts'"
        ).fetchone()
        return row is not None

    # --- Keyword search ---

    def keyword_search(self, terms: list[str], top_k: int = 20) -> list[dict]:
        """Full-text search using FTS5 with BM25 ranking, fallback to scan."""
        if not terms:
            return []

        # Try FTS5 first
        if self._has_fts():
            try:
                return self._fts5_search(terms, top_k)
            except Exception:
                logger.debug("FTS5 search failed, falling back to scan", exc_info=True)

        # Fallback: Python-side scan
        return self._scan_search(terms, top_k)

    def _fts5_search(self, terms: list[str], top_k: int) -> list[dict]:
        """FTS5-powered search with BM25 ranking."""
        # Build FTS5 query: each term joined with OR for broad matching
        fts_query = " OR ".join(f'"{t}"' for t in terms if t.strip())
        if not fts_query:
            return []

        rows = self.conn.execute(
            """SELECT f.node_id, f.label, f.kind, f.file_path,
                      bm25(nodes_fts) AS bm25_score,
                      n.pagerank
               FROM nodes_fts f
               JOIN nodes n ON n.id = f.node_id
               WHERE nodes_fts MATCH ?
               ORDER BY bm25(nodes_fts)
               LIMIT ?""",
            (fts_query, top_k),
        ).fetchall()

        return [
            {
                "id": row["node_id"],
                "label": row["label"],
                "kind": row["kind"],
                "file_path": row["file_path"],
                "score": -row["bm25_score"],  # BM25 returns negative (lower = better)
                "pagerank": row["pagerank"],
            }
            for row in rows
        ]

    def _scan_search(self, terms: list[str], top_k: int) -> list[dict]:
        """Fallback: scan all nodes in Python."""
        results = []
        for row in self.conn.execute("SELECT * FROM nodes"):
            label = (row["label"] or "").lower()
            snippet = (row["source_snippet"] or "").lower()
            docstring = (row["docstring"] or "").lower()
            score = sum(1 for t in terms if t in label or t in snippet or t in docstring)
            if score > 0:
                results.append({
                    "id": row["id"],
                    "label": row["label"],
                    "kind": row["kind"],
                    "file_path": row["file_path"],
                    "score": score,
                    "pagerank": row["pagerank"],
                })
        results.sort(key=lambda x: (x["score"], x["pagerank"]), reverse=True)
        return results[:top_k]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
