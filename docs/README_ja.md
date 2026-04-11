<p align="center">
  <h1 align="center">hedwig-kg</h1>
  <p align="center">
    AIコーディングエージェント向けローカルファーストナレッジグラフビルダー
    <br />
    <a href="#aiコーディングエージェント統合">統合</a> · <a href="#クイックスタート">クイックスタート</a> · <a href="#アーキテクチャ">アーキテクチャ</a> · <a href="../README.md">English</a> · <a href="README_ko.md">한국어</a> · <a href="README_zh.md">中文</a> · <a href="README_de.md">Deutsch</a>
  </p>
</p>

---

**hedwig-kg**はソースコードとドキュメントからナレッジグラフを構築し、デュアル埋め込みモデル（コード特化＋テキスト特化）を活用した**5シグナルHybridRAG検索**をRRF融合で提供します。すべて**100%ローカル**で実行されます。

## AIコーディングエージェント統合

1コマンドで主要なAIコーディングエージェントと統合できます。各統合はプラットフォーム固有のコンテキストファイルとフックを書き込み、エージェントがファイル検索前にナレッジグラフを自動的に活用します。

```bash
pip install hedwig-kg
```

### Claude Code

```bash
hedwig-kg claude install
```

`CLAUDE.md`セクション + `.claude/settings.json` PreToolUseフックを書き込みます。

### OpenAI Codex CLI

```bash
hedwig-kg codex install
```

`AGENTS.md`セクション + `.codex/hooks.json` PreToolUseフックを書き込みます。

### Google Gemini CLI

```bash
hedwig-kg gemini install
```

`GEMINI.md`セクション + `.gemini/settings.json` BeforeToolフックを書き込みます。

### Windsurf IDE

```bash
hedwig-kg windsurf install
```

`.windsurf/rules/hedwig-kg.md` ルールファイルを作成します。

### Cline (VS Code拡張機能)

```bash
hedwig-kg cline install
```

`.clinerules` ファイルを作成します。

### 仕組み

各`install`コマンドは2つのことを行います：

1. **コンテキストファイル** — プラットフォームのコンテキストファイルに`## hedwig-kg`セクションを追加
2. **フック** — ツール呼び出し前に実行される軽量シェルフックを登録

削除: `hedwig-kg <platform> uninstall`

### 要件

- Python 3.10+
- デフォルト埋め込みモデル用に~500MBのディスク容量（初回使用時にダウンロード）

### オプション依存関係

```bash
# PDFテキスト抽出
pip install hedwig-kg[docs]
```

## クイックスタート

### 1. インストール＆ビルド

```bash
pip install hedwig-kg
cd ./my-project
hedwig-kg build .
```

初回ビルドはすべてのファイルをスキャンし、AST構造を抽出し、埋め込みを生成し（~80MBモデルの初回ダウンロード）、コミュニティを検出して`.hedwig-kg/knowledge.db`に保存します。

### 2. 検索

```bash
hedwig-kg search "authentication handler"
```

### 3. エージェント統合

```bash
hedwig-kg claude install        # Claude Code
hedwig-kg codex install         # Codex CLI
hedwig-kg gemini install        # Gemini CLI
hedwig-kg windsurf install      # Windsurf IDE
hedwig-kg cline install         # Cline (VS Code)
```

### 4. 最新状態を維持

```bash
hedwig-kg build . --incremental
```

### 5. 探索

```bash
hedwig-kg stats                           # グラフ概要
hedwig-kg communities --search "auth"     # コミュニティ探索
hedwig-kg node "AuthHandler"              # ノード詳細
hedwig-kg query                           # インタラクティブREPL
hedwig-kg visualize                       # HTML可視化
```

## アーキテクチャ

```
ソースコード/ドキュメント → 検出 → 抽出 → グラフ構築 → 埋め込み → クラスタリング → 要約 → 分析 → 保存
```

### HybridRAG検索（5シグナル）

1. **コードベクトル検索** — `BAAI/bge-small-en-v1.5`でクエリを埋め込み、コードノード（関数、クラス、メソッド）をFAISS検索
2. **テキストベクトル検索** — `all-MiniLM-L6-v2`でクエリを埋め込み、ドキュメントノード（見出し、セクション、docstring）をFAISS検索
3. **グラフ拡張** — 上位ベクトル結果からN-hopネイバーを探索
4. **キーワード検索** — FTS5全文検索（BM25ランキング）
5. **コミュニティ検索** — コミュニティ要約とクエリのマッチング
5. **RRF融合** — すべてのシグナルを統合ランキングに結合

## ライセンス

MIT License. 詳細は[LICENSE](../LICENSE)をご覧ください。
