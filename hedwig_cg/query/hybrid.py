"""ハイブリッド検索エンジン: ベクター + キーワード + 最短経路サブグラフ。

2シグナル検索 + 最短経路によるサブグラフ応答:
1. ベクターサーチ (dual-model) → シードノード選別
2. キーワードサーチ (FTS5) → 正確名マッチング補助
3. RRF fusion → 統一ランキング
4. シードノード間の最短経路計算 → サブグラフ応答
"""

from __future__ import annotations

import hashlib
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import networkx as nx

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from hedwig_cg.storage.store import KnowledgeStore


# --- ストップワード（キーワード検索ノイズ除去） ---
STOPWORDS: frozenset[str] = frozenset({
    "the", "is", "at", "which", "on", "a", "an", "and", "or", "but",
    "in", "with", "to", "for", "of", "not", "no", "can", "had", "has",
    "have", "was", "were", "been", "being", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "shall", "must", "need",
    "this", "that", "these", "those", "it", "its", "from", "by", "as",
    "are", "be", "if", "so", "than", "too", "very", "just", "about",
    "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "then", "once",
    "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such",
    "only", "own", "same", "also", "what", "who", "whom",
})


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    """検索結果の個別ノード。"""
    node_id: str
    label: str
    kind: str
    file_path: str
    score: float
    source: str  # "seed" | "path"
    start_line: int = 0
    end_line: int = 0
    signature: str = ""
    docstring: str = ""
    signal_contributions: dict[str, float] = field(default_factory=dict)


@dataclass
class SearchEdge:
    """サブグラフ内のエッジ（最短経路上のエッジ）。"""
    source: str
    target: str
    relation: str


@dataclass
class SearchGraph:
    """検索結果をサブグラフとして返す。

    シードノード + 経路ノード（MSTの中間ノード）+ エッジ（MST経路上のみ）。
    孤立シード（他のシードと接続不可能）は isolated に分類。
    """
    nodes: list[SearchResult]
    edges: list[SearchEdge]
    isolated: list[SearchResult] = field(default_factory=list)

    def to_text(self, source_dir: str = "") -> str:
        """MCP/CLI共通のコンパクトなグラフ応答を生成。

        フォーマット:
            seeds: node_id1, node_id2, ...

            edges:
            node_a -relation-> node_b
            node_b -relation-> node_c
        """
        def _s(node_id: str) -> str:
            """source_dirプレフィックスを除去して相対パスに変換。"""
            if source_dir and node_id.startswith(source_dir):
                return node_id[len(source_dir):]
            return node_id

        seed_ids = [_s(n.node_id) for n in self.nodes if n.source == "seed"]
        lines = ["seeds:"]
        for sid in seed_ids:
            lines.append(sid)

        if self.edges:
            lines.append("")
            lines.append("edges:")
            for e in self.edges:
                lines.append(f"{_s(e.source)} -{e.relation}-> {_s(e.target)}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# キャッシュ
# ---------------------------------------------------------------------------

_search_cache: OrderedDict[str, SearchGraph] = OrderedDict()
_CACHE_MAX_SIZE = 128


def _cache_key(query: str, top_k: int) -> str:
    """検索クエリのキャッシュキーを生成。"""
    raw = f"{query}|{top_k}"
    return hashlib.md5(raw.encode()).hexdigest()


def clear_search_cache() -> None:
    """検索キャッシュをクリア（グラフ再構築後に呼び出す）。"""
    _search_cache.clear()


# ---------------------------------------------------------------------------
# シグナル設定（2シグナル: ベクター + キーワード）
# ---------------------------------------------------------------------------

SIGNAL_NAMES = ["vector", "keyword"]

# ベクター(1.5): コードのセマンティック検索
# キーワード(1.5): 正確名マッチング（関数名、クラス名など）
DEFAULT_WEIGHTS = [1.5, 1.5]


def reciprocal_rank_fusion(
    *ranked_lists: list[tuple[str, float]],
    k: int = 60,
    weights: list[float] | None = None,
    signal_names: list[str] | None = None,
) -> tuple[list[tuple[str, float]], dict[str, dict[str, float]]]:
    """Weighted Reciprocal Rank Fusionで複数ランキングを統合。

    RRF score = sum(w_i / (k + rank_i))
    """
    if weights is None:
        weights = [1.0] * len(ranked_lists)
    if signal_names is None:
        signal_names = SIGNAL_NAMES[:len(ranked_lists)]

    scores: dict[str, float] = {}
    breakdowns: dict[str, dict[str, float]] = {}
    for w, rlist, sname in zip(weights, ranked_lists, signal_names):
        for rank, (item_id, _) in enumerate(rlist):
            contribution = w / (k + rank + 1)
            scores[item_id] = scores.get(item_id, 0) + contribution
            if item_id not in breakdowns:
                breakdowns[item_id] = {}
            breakdowns[item_id][sname] = breakdowns[item_id].get(sname, 0) + contribution

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return fused, breakdowns


def extract_search_terms(query: str) -> list[str]:
    """ストップワードと短いトークンを除外して検索語を抽出。"""
    return [
        t.lower() for t in query.split()
        if len(t) > 2 and t.lower() not in STOPWORDS
    ]


# ---------------------------------------------------------------------------
# 最短経路サブグラフ
# ---------------------------------------------------------------------------

def _build_seed_subtree(
    G: nx.DiGraph,
    seed_ids: list[str],
    max_path_length: int = 6,
) -> tuple[list[str], list[SearchEdge], list[str]]:
    """全シードを接続するMSTベースの最小サブツリーを構築。

    Steiner Tree近似:
    1. シードペア間の最短距離行列を計算
    2. シード間のMST（最小全域木）を構築
    3. MST辺に対応する実際の最短経路を展開
    4. 到達不能シードをisolatedとして分離

    Args:
        G: コードグラフ
        seed_ids: シードノードIDリスト
        max_path_length: 最大経路長（これより長い経路はMSTに含めない）

    Returns:
        (中間ノードIDリスト, 経路上のエッジリスト, 孤立シードIDリスト)
    """
    if len(seed_ids) < 2:
        return [], [], []

    undirected = G.to_undirected(as_view=True)
    seed_set = set(seed_ids)

    # Step 1: シードペア間の最短距離と経路を計算
    # {(src_idx, tgt_idx): (distance, path)} のマップ
    pair_paths: dict[tuple[int, int], list[str]] = {}
    valid_seeds = [s for s in seed_ids if undirected.has_node(s)]

    for i, src in enumerate(valid_seeds):
        for j in range(i + 1, len(valid_seeds)):
            tgt = valid_seeds[j]
            try:
                path = nx.shortest_path(undirected, src, tgt)
            except nx.NetworkXNoPath:
                continue
            if len(path) <= max_path_length:
                pair_paths[(i, j)] = path

    if not pair_paths:
        # 接続可能なペアがない → 全シード孤立
        return [], [], list(seed_ids)

    # Step 2: MSTを構築（Kruskal法）
    # エッジ = (距離, src_idx, tgt_idx)、距離順ソート
    mst_edges: list[tuple[int, int, int]] = sorted(
        (len(path) - 1, i, j) for (i, j), path in pair_paths.items()
    )

    # Union-Find
    parent = list(range(len(valid_seeds)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: int, y: int) -> bool:
        rx, ry = find(x), find(y)
        if rx == ry:
            return False
        parent[rx] = ry
        return True

    selected_pairs: list[tuple[int, int]] = []
    for _dist, i, j in mst_edges:
        if union(i, j):
            selected_pairs.append((i, j))
            if len(selected_pairs) == len(valid_seeds) - 1:
                break

    # Step 3: MST辺の実際の経路からノードとエッジを収集
    intermediate_ids: set[str] = set()
    edges: list[SearchEdge] = []
    seen_edges: set[tuple[str, str]] = set()
    connected_seeds: set[str] = set()

    for i, j in selected_pairs:
        path = pair_paths[(i, j)]
        connected_seeds.add(valid_seeds[i])
        connected_seeds.add(valid_seeds[j])

        # 中間ノード収集
        for node_id in path[1:-1]:
            if node_id not in seed_set:
                intermediate_ids.add(node_id)

        # エッジ収集（方向はオリジナルグラフから取得）
        for k in range(len(path) - 1):
            a, b = path[k], path[k + 1]
            edge_key = (min(a, b), max(a, b))
            if edge_key in seen_edges:
                continue
            seen_edges.add(edge_key)

            if G.has_edge(a, b):
                rel = G.edges[a, b].get("relation", "")
                edges.append(SearchEdge(source=a, target=b, relation=rel))
            elif G.has_edge(b, a):
                rel = G.edges[b, a].get("relation", "")
                edges.append(SearchEdge(source=b, target=a, relation=rel))

    # Step 4: 孤立シード（MSTに含まれなかったシード）
    isolated = [s for s in seed_ids if s not in connected_seeds]

    return list(intermediate_ids), edges, isolated


# ---------------------------------------------------------------------------
# メイン検索関数
# ---------------------------------------------------------------------------

def hybrid_search(
    query: str,
    store: "KnowledgeStore",
    G: nx.DiGraph,
    top_k: int = 10,
    vector_candidates: int = 40,
    weights: list[float] | None = None,
    use_cache: bool = True,
    fast: bool = False,
    text_model: str | None = None,
    *,
    graph_hops: int = 2,  # 後方互換（未使用）
) -> SearchGraph:
    """2シグナル検索 + 最短経路サブグラフ応答。

    Args:
        query: 自然言語クエリ。
        store: エンベディング付きKnowledgeStore。
        G: コードグラフ。
        top_k: シードノード数。
        vector_candidates: ベクター検索候補数。
        weights: シグナルウェイト [vector, keyword]。
        use_cache: LRUキャッシュ使用有無。
        fast: テキストモデルのみ使用（コールドスタート短縮）。
        text_model: テキストモデル名オーバーライド。
        graph_hops: 後方互換のため残す（未使用）。

    Returns:
        SearchGraph — シードノード + 経路ノード + エッジのサブグラフ。
    """
    # キャッシュチェック
    if use_cache:
        key = _cache_key(query, top_k)
        if key in _search_cache:
            _search_cache.move_to_end(key)
            return _search_cache[key]

    signal_weights = weights or DEFAULT_WEIGHTS

    # Stage 1: ベクターサーチ（dual-model）
    if fast:
        from hedwig_cg.query.embeddings import TEXT_MODEL, embed_query
        effective_text = text_model or TEXT_MODEL
        query_vec = embed_query(query, effective_text)
        text_vector_hits = store.vector_search(
            query_vec, top_k=vector_candidates, model_type="text",
        )
        code_vector_hits = store.vector_search(
            query_vec, top_k=vector_candidates, model_type="code",
        )
    else:
        from hedwig_cg.query.embeddings import embed_query_dual
        query_vecs = embed_query_dual(query, text_model=text_model)
        code_vector_hits = store.vector_search(
            query_vecs["code"], top_k=vector_candidates, model_type="code",
        )
        text_vector_hits = store.vector_search(
            query_vecs["text"], top_k=vector_candidates, model_type="text",
        )

    # code + text をマージして1つのベクターシグナルに
    vector_hits = sorted(
        code_vector_hits + text_vector_hits, key=lambda x: x[1], reverse=True,
    )[:vector_candidates]

    # Stage 2: キーワードサーチ（FTS5）
    terms = extract_search_terms(query)
    keyword_results = store.keyword_search(terms, top_k=vector_candidates) if terms else []
    keyword_hits = [(r["id"], r["score"]) for r in keyword_results]

    # Stage 3: 2シグナルRRF fusion
    fused, breakdowns = reciprocal_rank_fusion(
        vector_hits, keyword_hits,
        weights=signal_weights,
        signal_names=SIGNAL_NAMES,
    )

    # Stage 4: シードノード選別
    seed_nodes: list[tuple[str, float, dict]] = []
    for node_id, rrf_score in fused:
        if len(seed_nodes) >= top_k:
            break
        data = G.nodes.get(node_id, {})
        if not data:
            continue
        kind = data.get("kind", "")
        if kind in ("external", "directory"):
            continue
        seed_nodes.append((node_id, rrf_score, data))

    # Stage 5: MSTベースの最小サブツリー構築
    seed_ids = [nid for nid, _, _ in seed_nodes]
    intermediate_ids, path_edges, isolated_ids = _build_seed_subtree(G, seed_ids)
    isolated_set = set(isolated_ids)

    # Stage 6: SearchGraph構築
    nodes: list[SearchResult] = []
    isolated_nodes: list[SearchResult] = []

    def _make_result(node_id: str, score: float, data: dict,
                     source: str) -> SearchResult:
        return SearchResult(
            node_id=node_id,
            label=data.get("label", node_id),
            kind=data.get("kind", ""),
            file_path=data.get("file_path", ""),
            score=round(score, 4),
            source=source,
            start_line=data.get("start_line", 0),
            end_line=data.get("end_line", 0),
            signature=data.get("signature", ""),
            docstring=data.get("docstring", ""),
            signal_contributions=breakdowns.get(node_id, {}),
        )

    # シードノード（接続済み vs 孤立）
    for node_id, score, data in seed_nodes:
        sr = _make_result(node_id, score, data, "seed")
        if node_id in isolated_set:
            isolated_nodes.append(sr)
        else:
            nodes.append(sr)

    # 経路上の中間ノード
    for node_id in intermediate_ids:
        data = G.nodes.get(node_id, {})
        if not data:
            continue
        nodes.append(_make_result(node_id, 0.0, data, "path"))

    result = SearchGraph(nodes=nodes, edges=path_edges, isolated=isolated_nodes)

    # キャッシュ保存
    if use_cache:
        key = _cache_key(query, top_k)
        _search_cache[key] = result
        if len(_search_cache) > _CACHE_MAX_SIZE:
            _search_cache.popitem(last=False)

    return result


def extract_result_edges(
    G: nx.DiGraph,
    results: SearchGraph | list[SearchResult],
) -> list[dict]:
    """後方互換のためのエッジ抽出ヘルパー。

    SearchGraphの場合はedgesをdict形式に変換。
    list[SearchResult]の場合は既存のノード間エッジを抽出。
    """
    if isinstance(results, SearchGraph):
        edges = []
        for e in results.edges:
            src_label = G.nodes.get(e.source, {}).get("label", e.source)
            tgt_label = G.nodes.get(e.target, {}).get("label", e.target)
            edges.append({
                "from": src_label,
                "to": tgt_label,
                "rel": e.relation,
            })
        return edges

    # レガシー: list[SearchResult]の場合
    result_ids = {getattr(r, "node_id", None) for r in results} - {None}
    if not result_ids:
        return []
    edges = []
    seen: set[tuple[str, str]] = set()
    for r in results:
        nid = getattr(r, "node_id", None)
        if not nid or not G.has_node(nid):
            continue
        for _, target, edata in G.out_edges(nid, data=True):
            if target in result_ids:
                key = (nid, target)
                if key not in seen:
                    seen.add(key)
                    edges.append({
                        "from": G.nodes[nid].get("label", nid),
                        "to": G.nodes[target].get("label", target),
                        "rel": edata.get("relation", ""),
                    })
    return edges
