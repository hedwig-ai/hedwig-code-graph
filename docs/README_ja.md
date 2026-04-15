<p align="center">
<img width="2048" height="1138" alt="hegwid-cg" src="https://github.com/user-attachments/assets/2875669b-e7e3-45df-9e50-90110e2abbf1" />
<h1 align="center">hedwig-cg</h1>
  <p align="center">
    "With hedwig-cg, your coding agent knows what to read."
    <br />
    <a href="#クイックスタート">クイックスタート</a> · <a href="../README.md">English</a> · <a href="README_ko.md">한국어</a> · <a href="README_zh.md">中文</a> · <a href="README_de.md">Deutsch</a>
  </p>
</p>

<p align="center">
  <a href="https://github.com/hedwig-ai/hedwig-code-graph/actions"><img src="https://img.shields.io/github/actions/workflow/status/hedwig-ai/hedwig-code-graph/ci.yml?branch=main" alt="CI"></a>
  <a href="https://pypi.org/project/hedwig-cg/"><img src="https://img.shields.io/pypi/v/hedwig-cg" alt="PyPI"></a>
  <a href="https://github.com/hedwig-ai/hedwig-code-graph/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hedwig-ai/hedwig-code-graph" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

## なぜ hedwig-cg なのか？

> raw data from a given number of sources is collected, then compiled by an LLM into a .md wiki, then operated on by various CLIs by the LLM to do Q&A and to incrementally enhance the wiki - Andrej Karpathy

hedwig-cgは10,000ファイル以上のコードベースとナレッジドキュメントから、軽量ローカルLLMモデルを使用してクエリ可能なコードグラフとナレッジベースを構築します。サブグラフレスポンスを伴うハイブリッドベクトル+キーワード検索（ベクトル+キーワード→MSTサブグラフによるRRF融合）でコーディングエージェントがプロジェクト全体を真に理解できるようになります。インストールすればClaude Codeが全体像を把握できます——追加のトークンも、追加のコマンドも不要、すべて100%ローカルで実行されます。

## クイックスタート

```bash
pip install hedwig-cg

cd your-project/
hedwig-cg claude install
```

Claude Codeに伝えてください：

> 「このプロジェクトのコードグラフをビルドして」

以上です。Claude Codeがグラフをビルドし、以降すべての検索で自動的に参照します。セッション終了時にグラフが自動的にリビルドされます。

## AIエージェント統合

hedwig-cgは主要なAIコーディングエージェントと1コマンドで統合できます：

| エージェント | インストール | 説明 |
|------------|------------|------|
| **Claude Code** | `hedwig-cg claude install` | Skill + CLAUDE.md + PreToolUseフック |
| **Codex CLI** | `hedwig-cg codex install` | AGENTS.md + PreToolUseフック |
| **Gemini CLI** | `hedwig-cg gemini install` | GEMINI.md + BeforeToolフック |
| **Cursor IDE** | `hedwig-cg cursor install` | `.cursor/rules/`ルールファイル |
| **Windsurf IDE** | `hedwig-cg windsurf install` | `.windsurf/rules/`ルールファイル |
| **Cline** | `hedwig-cg cline install` | `.clinerules`ファイル |
| **Aider CLI** | `hedwig-cg aider install` | CONVENTIONS.md + `.aider.conf.yml` |
| **MCPサーバー** | `claude mcp add hedwig-cg -- hedwig-cg mcp` | Model Context Protocol 5ツール |

各`install`はコンテキストファイルの書き込みと（対応プラットフォームの場合）ツール呼び出し前のフック登録を行います。削除：`hedwig-cg <platform> uninstall`。

## 対応言語

### 構造抽出（20以上の言語）

hedwig-cgはtree-sitterとネイティブパーサーを使用して、関数、クラス、メソッド、呼び出し、import、継承を抽出します。

| | | | |
|:---:|:---:|:---:|:---:|
| Python | JavaScript | TypeScript | Go |
| Rust | Java | C | C++ |
| C# | Ruby | Swift | Scala |
| Lua | PHP | Elixir | Kotlin |
| Objective-C | Terraform/HCL | | |

設定・ドキュメント形式も構造抽出対応：YAML、JSON、TOML、Markdown、PDF、HTML、CSV、Shell、Rなど。

### 多言語自然言語サポート

テキストノード（ドキュメント、コメント、マークダウン）は`intfloat/multilingual-e5-small`で埋め込まれ、**100以上の自然言語**をサポートします — 日本語、韓国語、中国語、ドイツ語、フランス語など。お好きな言語で検索し、あらゆる言語の結果を見つけます。

---

## 機能

### 自動リビルド

AIコーディングエージェント（Claude Code、Codexなど）と統合すると、hedwig-cgはコード変更時に**自動的にグラフをリビルド**します。Stop/SessionEndフックが`git diff`で変更ファイルを検出し、バックグラウンドでインクリメンタルビルドを実行します — 手動操作は不要です。

### スマートIgnore

3つのソースからIgnoreパターンをサポートし、すべて**完全なgitignoreスペック**（否定`!`、`**`グロブ、ディレクトリ専用パターン）に対応：

| ソース | 説明 |
|--------|------|
| ビルトイン | `.git`、`node_modules`、`__pycache__`、`dist`、`build`など |
| `.gitignore` | プロジェクトルートから自動読み込み — 既存のgit ignoreがそのまま動作 |
| `.hedwig-cg-ignore` | コードグラフ用のプロジェクト固有オーバーライド |

### インクリメンタルビルド

ファイルごとのSHA-256コンテンツハッシュ。変更されたファイルのみ再抽出・再埋め込み。未変更ファイルは既存グラフからマージ — 通常フルビルドより**95%以上高速**。

### メモリ管理

4GBメモリバジェットとステージ別解放。パイプラインは各段階で生成→保存→解放：抽出結果はグラフ構築後に解放、埋め込みはバッチ単位でストリーミングしDB書き込み後に解放、グラフ全体は永続化後に解放。GCは75%閾値で先制的にトリガー。

### 100%ローカル

クラウドサービスなし、APIキーなし、テレメトリなし。SQLite + FAISSでストレージ、sentence-transformersで埋め込み。すべてのデータがローカルに保持されます。

---

## サブグラフレスポンスを伴うハイブリッド検索

すべてのクエリはシードノードとそれらの接続関係を示すサブグラフを返します：

**検索パイプライン**

| シグナル | 検索対象 |
|----------|----------|
| **ベクトル検索** | 意味的に類似したコードとドキュメント（デュアルモデル：コード+テキスト） |
| **キーワード検索** | FTS5による正確な名前マッチ（BM25） |

結果はWeighted Reciprocal Rank Fusion（RRF）で融合され、MSTベースの最短パスで接続されてシードノードの関係を明らかにします。

**レスポンス形式**
```
seeds:
hedwig_cg/core/pipeline.py:71
hedwig_cg/query/embeddings.py:70

edges:
hedwig_cg/core/pipeline.py:71 -calls-> hedwig_cg/core/extract.py:747
hedwig_cg/core/pipeline.py:0 -co_change-> hedwig_cg/query/embeddings.py:0
```

- `seeds`: 検索で見つかったノードID（ファイル:行）
- `edges`: 最短パスでシードノードを接続するサブグラフ（中間ノードはエッジに表示）

## CLIリファレンス

すべてのコマンドはデフォルトでコンパクトなテキストを出力します（AIエージェント向けに設計）。

| コマンド | 説明 |
|----------|------|
| `build <dir>` | コードグラフをビルド（`--incremental`） |
| `search <query>` | サブグラフ付きハイブリッドベクトル+キーワード検索（`--top-k`、`--fast`） |
| `search-vector <query>` | ベクトル類似度のみ（コード+テキストデュアルモデル） |
| `search-keyword <query>` | FTS5キーワードマッチのみ（BM25ランキング） |
| `query` | インタラクティブ検索REPL |
| `communities` | コミュニティの一覧と検索（`--search`、`--level`） |
| `stats` | グラフ統計 |
| `node <id>` | ファジーマッチによるノード詳細 |
| `export` | JSON、GraphML、D3.jsでエクスポート |
| `visualize` | インタラクティブHTML可視化 |
| `clean` | .hedwig-cg/データベースを削除 |
| `doctor` | インストール状態の確認 |
| `mcp` | MCPサーバーを起動（stdio） |
| `claude install\|uninstall` | Claude Code統合管理 |
| `codex install\|uninstall` | Codex CLI統合管理 |
| `gemini install\|uninstall` | Gemini CLI統合管理 |
| `cursor install\|uninstall` | Cursor IDE統合管理 |
| `windsurf install\|uninstall` | Windsurf IDE統合管理 |
| `cline install\|uninstall` | Cline統合管理 |
| `aider install\|uninstall` | Aider CLI統合管理 |

## パフォーマンス

hedwig-cg自体のコードベースでのベンチマーク（約3,500行、90ファイル、1,300ノード）：

| 操作 | 時間 |
|------|------|
| フルビルド | ~14秒 |
| インクリメンタルビルド（変更あり） | ~4秒 |
| インクリメンタルビルド（変更なし） | ~0.4秒 |
| コールド検索（デュアルモデル） | ~2.8秒 |
| コールド検索（`--fast`） | ~0.2秒 |
| ウォーム検索 | ~0.08秒 |
| キャッシュヒット | <1ms |

- **埋め込みモデル**: ~180MB、`~/.hedwig-cg/models/`に一度だけダウンロード
- **データベース**: ~2MB（SQLite + FTS5 + FAISSインデックス）
- **インクリメンタルビルド**: SHA-256ハッシュ、フルビルドより95%+高速

## 要件

- Python 3.10+
- 埋め込みモデル ~180MB（初回使用時にキャッシュ）

```bash
# オプション: PDF抽出
pip install hedwig-cg[docs]
```

## 開発

```bash
pip install -e ".[dev]"
pytest
ruff check hedwig_cg/
```

## ライセンス

MIT License。[LICENSE](../LICENSE)を参照。

## コントリビューション

コントリビューションを歓迎します！[CONTRIBUTING.md](../CONTRIBUTING.md)を参照。
