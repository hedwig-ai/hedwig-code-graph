<p align="center">
  <h1 align="center">hedwig-kg</h1>
  <p align="center">
    ローカルファーストのナレッジグラフビルダー — 4シグナルHybridRAG検索
    <br />
    <a href="#インストール">インストール</a> · <a href="#クイックスタート">クイックスタート</a> · <a href="#アーキテクチャ">アーキテクチャ</a> · <a href="../README.md">English</a> · <a href="README_ko.md">한국어</a>
  </p>
</p>

---

## hedwig-kgとは？

**hedwig-kg**はソースコードとドキュメントを解析してナレッジグラフを構築し、ベクトル類似度＋グラフ探索＋キーワードマッチング＋コミュニティ要約を融合した**4シグナルHybridRAG検索**を提供します。すべて**100%ローカル**で実行され、クラウドAPIは使用しません。

### 主な機能

- **4シグナルHybridRAG検索** — ベクトル類似度 → グラフN-hop拡張 → FTS5キーワードマッチング → コミュニティ要約マッチング → RRF融合
- **Tree-sitter AST抽出** — Python、JavaScript、TypeScriptの正確な構造解析
- **Markdownドキュメント抽出** — 見出しをセクションノードに、内部リンクを参照エッジに変換
- **階層的コミュニティ** — マルチ解像度Leidenクラスタリング＋自動生成キーワードサマリー
- **インクリメンタルビルド** — SHA-256ハッシュで未変更ファイルをスキップ（高速リビルド）
- **ローカル埋め込み** — sentence-transformersによるプライバシー保護されたセマンティック検索
- **SQLite + FTS5 + FAISS** — シングルファイルDBに全文検索＋ベクトルインデックスを統合
- **20+言語対応** — Python、JS/TS、Java、Go、Rust、C/C++、Rubyなど

## インストール

```bash
pip install hedwig-kg
```

ソースからインストール：

```bash
git clone https://github.com/hedwig-ai/hedwig-knowledge-graph.git
cd hedwig-knowledge-graph
pip install -e .
```

## クイックスタート

```bash
# ナレッジグラフの構築
hedwig-kg build ./my-project

# インクリメンタルリビルド（未変更ファイルをスキップ）
hedwig-kg build ./my-project --incremental

# 4シグナルハイブリッド検索
hedwig-kg search "authentication handler"

# コミュニティの探索
hedwig-kg communities
hedwig-kg communities --search "auth"

# インタラクティブ探索（REPL — グラフを一度読み込んで連続検索）
hedwig-kg query

# 統計表示（密度、クラスタリング係数、連結成分を含む）
hedwig-kg stats

# ノード詳細表示（ファジーマッチング対応）
hedwig-kg node "AuthHandler"

# グラフのエクスポート
hedwig-kg export --format json
hedwig-kg export --format d3       # D3.js互換JSON

# インタラクティブ可視化（ブラウザで開く）
hedwig-kg visualize
hedwig-kg visualize --max-nodes 300 -o my_graph.html

# データベース削除
hedwig-kg clean
hedwig-kg clean --yes              # 確認なしで削除
```

## アーキテクチャ

```
ソースコード → 検出 → 抽出 → グラフ構築 → 埋め込み → クラスタリング → 要約 → 分析 → 保存
```

| ステージ | 説明 |
|----------|------|
| **検出** | ディレクトリスキャン、20+言語分類、`.hedwig-kg-ignore`対応 |
| **抽出** | Tree-sitter AST（Python/JS/TS）、Markdown見出し/セクション抽出、正規表現フォールバック |
| **構築** | 3フェーズ重複排除で有向グラフを組み立て |
| **埋め込み** | sentence-transformersによるローカル埋め込み生成 |
| **クラスタリング** | マルチ解像度Leiden階層的コミュニティ検出 |
| **要約** | ノード属性からキーワード豊富なコミュニティサマリーを自動生成 |
| **分析** | PageRank、ゴッドノード、ハブ分析 |
| **保存** | SQLite + FTS5全文検索 + FAISSベクトルインデックス |

## ライセンス

MIT License. 詳細は[LICENSE](../LICENSE)をご覧ください。
