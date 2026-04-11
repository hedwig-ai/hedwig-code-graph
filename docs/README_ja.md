<p align="center">
  <h1 align="center">hedwig-kg</h1>
  <p align="center">
    AIコーディングエージェントのためのローカルファースト知識グラフビルダー
    <br />
    <a href="#クイックスタート">クイックスタート</a> · <a href="#対応言語">言語</a> · <a href="#aiエージェント統合">統合</a> · <a href="#アーキテクチャ">アーキテクチャ</a> · <a href="../README.md">English</a> · <a href="README_ko.md">한국어</a> · <a href="README_zh.md">中文</a> · <a href="README_de.md">Deutsch</a>
  </p>
</p>

<p align="center">
  <a href="https://github.com/hedwig-ai/hedwig-knowledge-graph/actions"><img src="https://img.shields.io/github/actions/workflow/status/hedwig-ai/hedwig-knowledge-graph/ci.yml?branch=main" alt="CI"></a>
  <a href="https://pypi.org/project/hedwig-kg/"><img src="https://img.shields.io/pypi/v/hedwig-kg" alt="PyPI"></a>
  <a href="https://github.com/hedwig-ai/hedwig-knowledge-graph/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hedwig-ai/hedwig-knowledge-graph" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

## なぜ hedwig-kg なのか？

あなたはソフトウェアエンジニアです。決済ドメインの開発を考えたとき、何が思い浮かびますか？おそらく「Paddle」や「Stripe」でしょう。

しかし、Claude Codeのようなツールは関連コードを自然に見つけることができません。意味的なつながりが存在しないからです。Claudeにとって「Payment」と「Stripe」はまったく別の世界に住んでいます。

そのため、できる唯一のことを繰り返すだけです — 「Payment」という単語をgrepし続けること。

**hedwig-kg**はこの問題を解決します。コードベースから知識グラフを構築し — 関数、クラス、import、コールグラフ、継承、コミュニティ — 人間が考えるのと同じように意味的に検索します。

「決済関連のコードを探して」と聞けば、「payment」という単語がなくても`StripeClient`、`checkout_handler`、`WebhookController`を見つけ出します。

<img width="1919" height="991" alt="Knowledge Graph" src="https://github.com/user-attachments/assets/a169c526-bb7c-4900-91dd-4db637793e32" />

## クイックスタート

```bash
pip install hedwig-kg
hedwig-kg claude install
```

Claude Codeに伝えてください：

> 「このプロジェクトのナレッジグラフをビルドして」

以上です。Claude Codeがグラフをビルドし、以降すべての検索で自動的に参照します。コードが変更されたら：

> 「ナレッジグラフを再ビルドして」

## 対応言語

### 深層AST抽出（17言語）

hedwig-kgは[tree-sitter tags.scm](https://tree-sitter.github.io/tree-sitter/4-code-navigation.html)を使用して汎用的な構造抽出を行います — 関数、クラス、メソッド、呼び出し、import、継承 — 言語別のカスタムコード不要。

| | | | |
|:---:|:---:|:---:|:---:|
| Python | JavaScript | TypeScript | Go |
| Rust | Java | C | C++ |
| C# | Ruby | Swift | Scala |
| Lua | PHP | Elixir | Kotlin |
| Objective-C | | | |

さらに検出・インデックス化：Markdown、PDF、HTML、CSV、YAML、JSON、TOML、Shell、Rなど。

### 多言語自然言語サポート

テキストノード（ドキュメント、コメント、マークダウン）は`intfloat/multilingual-e5-small`で埋め込まれ、**100以上の自然言語**をサポートします — 日本語、韓国語、中国語、ドイツ語、フランス語など。お好きな言語で検索し、あらゆる言語の結果を見つけます。

## AIエージェント統合

hedwig-kgは主要なAIコーディングエージェントと1コマンドで統合できます：

| エージェント | インストール | 説明 |
|------------|------------|------|
| **Claude Code** | `hedwig-kg claude install` | Skill + CLAUDE.md + PreToolUseフック |
| **Codex CLI** | `hedwig-kg codex install` | AGENTS.md + PreToolUseフック |
| **Gemini CLI** | `hedwig-kg gemini install` | GEMINI.md + BeforeToolフック |
| **Cursor IDE** | `hedwig-kg cursor install` | `.cursor/rules/`ルールファイル |
| **Windsurf IDE** | `hedwig-kg windsurf install` | `.windsurf/rules/`ルールファイル |
| **Cline** | `hedwig-kg cline install` | `.clinerules`ファイル |
| **Aider CLI** | `hedwig-kg aider install` | CONVENTIONS.md + `.aider.conf.yml` |
| **MCPサーバー** | `claude mcp add hedwig-kg -- hedwig-kg mcp` | Model Context Protocol 5ツール |

各`install`はコンテキストファイルの書き込みと（対応プラットフォームの場合）ツール呼び出し前のフック登録を行います。削除：`hedwig-kg <platform> uninstall`。

---

## アーキテクチャ

```
ソースコード/ドキュメント
       |
       v
   検出 ──> 抽出 ──> 構築 ──> 埋め込み ──> クラスタ ──> 分析 ──> 保存
           tags.scm  NetworkX  デュアル     Leiden     PageRank   SQLite
           (17言語)  DiGraph   FAISS      階層構造    ゴッドノード FTS5+FAISS
```

### ハイブリッド検索（5シグナル）

1. **コードベクトル** — `BAAI/bge-small-en-v1.5`でコードノードを埋め込み、FAISSコサイン検索
2. **テキストベクトル** — `intfloat/multilingual-e5-small`でテキストノードを埋め込み（100+言語）
3. **グラフ展開** — ベクトルヒットからBFS、エッジ品質で重み付け
4. **キーワード** — FTS5全文検索、ソースコード全体対象
5. **コミュニティ** — Leidenクラスタリング要約が関連ノードをブースト
6. **RRF融合** — 重み付き逆順位融合がすべてのシグナルを結合

## パフォーマンス

hedwig-kg自体のコードベースでのベンチマーク（約3,500行、90ファイル、1,300ノード）：

| 操作 | 時間 |
|------|------|
| フルビルド | ~14秒 |
| インクリメンタルビルド（変更あり） | ~4秒 |
| インクリメンタルビルド（変更なし） | ~0.4秒 |
| コールド検索（デュアルモデル） | ~2.8秒 |
| コールド検索（`--fast`） | ~0.2秒 |
| ウォーム検索 | ~0.08秒 |
| キャッシュヒット | <1ms |

## 要件

- Python 3.10+
- 埋め込みモデル ~470MB（初回使用時にキャッシュ）

## ライセンス

MIT License。[LICENSE](../LICENSE)を参照。

## コントリビューション

コントリビューションを歓迎します！[CONTRIBUTING.md](../CONTRIBUTING.md)を参照。
