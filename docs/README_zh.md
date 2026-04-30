<p align="center">
<img width="2048" height="1138" alt="hegwid-cg" src="https://github.com/user-attachments/assets/2875669b-e7e3-45df-9e50-90110e2abbf1" />
<h1 align="center">hedwig-cg</h1>
  <p align="center">
    "With hedwig-cg, your coding agent knows what to read."
    <br />
    <a href="#快速开始">快速开始</a> · <a href="../README.md">English</a> · <a href="README_ko.md">한국어</a> · <a href="README_ja.md">日本語</a> · <a href="README_de.md">Deutsch</a>
  </p>
</p>

<p align="center">
  <a href="https://github.com/hedwig-ai/hedwig-code-graph/actions"><img src="https://img.shields.io/github/actions/workflow/status/hedwig-ai/hedwig-code-graph/ci.yml?branch=main" alt="CI"></a>
  <a href="https://pypi.org/project/hedwig-cg/"><img src="https://img.shields.io/pypi/v/hedwig-cg" alt="PyPI"></a>
  <a href="https://github.com/hedwig-ai/hedwig-code-graph/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hedwig-ai/hedwig-code-graph" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

## 为什么选择 hedwig-cg？

> raw data from a given number of sources is collected, then compiled by an LLM into a .md wiki, then operated on by various CLIs by the LLM to do Q&A and to incrementally enhance the wiki - Andrej Karpathy

hedwig-cg使用轻量级本地LLM模型，从10,000+文件的代码库和知识文档构建可查询的代码图和知识库。带子图响应的混合向量+关键词搜索（向量+关键词→基于MST子图的RRF融合）让编程代理真正理解你的整个项目，而不仅仅是搜索关键词。安装后Claude Code即可看到全貌——无需额外的token，无需额外的命令，一切100%本地运行。

## 快速开始

```bash
pip install hedwig-cg

cd your-project/
hedwig-cg opencode install    # 适用于OpenCode
# 或: hedwig-cg claude install  # 适用于Claude Code
```

然后告诉Claude Code或OpenCode：

> "为这个项目构建代码图"

就这样。图会构建完成，之后每次搜索都会自动参考。会话结束时图会自动重建。

## AI代理集成

hedwig-cg通过一个命令与主要AI编程代理集成：

| 代理 | 安装 | 说明 |
|------|------|------|
| **Claude Code** | `hedwig-cg claude install` | Skill + CLAUDE.md + PreToolUse钩子 |
| **OpenCode** | `hedwig-cg opencode install` | `.opencode/skills/`中的技能 |
| **Codex CLI** | `hedwig-cg codex install` | AGENTS.md + PreToolUse钩子 |
| **Gemini CLI** | `hedwig-cg gemini install` | GEMINI.md + BeforeTool钩子 |
| **Cursor IDE** | `hedwig-cg cursor install` | `.cursor/rules/`规则文件 |
| **Windsurf IDE** | `hedwig-cg windsurf install` | `.windsurf/rules/`规则文件 |
| **Cline** | `hedwig-cg cline install` | `.clinerules`文件 |
| **Aider CLI** | `hedwig-cg aider install` | CONVENTIONS.md + `.aider.conf.yml` |
| **MCP服务器** | `claude mcp add hedwig-cg -- hedwig-cg mcp` | Model Context Protocol 5个工具 |

每个`install`会写入上下文文件，并（在支持的平台上）注册工具调用前的钩子。卸载：`hedwig-cg <platform> uninstall`。

## 支持的语言

### 结构提取（20+种语言）

hedwig-cg使用tree-sitter和原生解析器提取函数、类、方法、调用、import、继承。

| | | | |
|:---:|:---:|:---:|:---:|
| Python | JavaScript | TypeScript | Go |
| Rust | Java | C | C++ |
| C# | Ruby | Swift | Scala |
| Lua | PHP | Elixir | Kotlin |
| Objective-C | Terraform/HCL | | |

配置和文档格式也支持结构提取：YAML、JSON、TOML、Markdown、PDF、HTML、CSV、Shell、R等。

### 多语言自然语言支持

文本节点（文档、注释、markdown）使用`intfloat/multilingual-e5-small`嵌入，支持**100多种自然语言**——中文、韩语、日语、德语、法语等。用你的语言搜索，找到任何语言的结果。

---

## 功能

### 自动重建

与AI编码代理（Claude Code、Codex等）集成时，hedwig-cg会在代码变更时**自动重建图**。Stop/SessionEnd钩子通过`git diff`检测变更文件，并在后台执行增量构建——无需手动操作。

### 智能忽略

支持三个来源的忽略模式，全部使用**完整的gitignore规范**（否定`!`、`**`通配符、目录专用模式）：

| 来源 | 说明 |
|------|------|
| 内置 | `.git`、`node_modules`、`__pycache__`、`dist`、`build`等 |
| `.gitignore` | 从项目根目录自动读取——现有的git忽略规则直接生效 |
| `.hedwig-cg-ignore` | 代码图专用的项目级覆盖 |

### 增量构建

逐文件SHA-256内容哈希。仅重新提取和重新嵌入变更的文件。未变更文件从现有图中合并——通常比完整构建**快95%以上**。

### 内存管理

4GB内存预算和分阶段释放。管道在每个阶段执行生成→存储→释放：提取结果在图构建后释放，嵌入以批次流式传输并在DB写入后释放，完整图在持久化后释放。GC在75%阈值时主动触发。

### 100%本地

无云服务、无API密钥、无遥测。SQLite + FAISS存储，sentence-transformers嵌入。所有数据保留在本地。

---

## 带子图响应的混合搜索

所有查询返回种子节点以及展示它们如何连接的子图：

**搜索管线**

| 信号 | 搜索内容 |
|------|----------|
| **向量搜索** | 语义相似的代码和文档（双模型：代码+文本） |
| **关键词搜索** | 通过FTS5精确匹配名称（BM25） |

结果通过加权倒数排名融合（RRF）合并，然后通过基于MST的最短路径连接，揭示种子节点间的关系。

**响应格式**
```
seeds:
hedwig_cg/core/pipeline.py:71
hedwig_cg/query/embeddings.py:70

edges:
hedwig_cg/core/pipeline.py:71 -calls-> hedwig_cg/core/extract.py:747
hedwig_cg/core/pipeline.py:0 -co_change-> hedwig_cg/query/embeddings.py:0
```

- `seeds`: 搜索找到的节点ID（文件:行号）
- `edges`: 通过最短路径连接种子节点的子图（中间节点出现在边中）

## CLI参考

所有命令默认输出紧凑文本（为AI代理消费而设计）。

| 命令 | 说明 |
|------|------|
| `build <dir>` | 构建代码图（`--incremental`） |
| `search <query>` | 带子图的混合向量+关键词搜索（`--top-k`、`--fast`） |
| `search-vector <query>` | 仅向量相似度搜索（代码+文本双模型） |
| `search-keyword <query>` | 仅FTS5关键词匹配（BM25排序） |
| `query` | 交互式搜索REPL |
| `communities` | 列出和搜索社区（`--search`、`--level`） |
| `stats` | 图统计 |
| `node <id>` | 模糊匹配节点详情 |
| `export` | 导出为JSON、GraphML或D3.js |
| `visualize` | 交互式HTML可视化 |
| `clean` | 删除.hedwig-cg/数据库 |
| `doctor` | 检查安装状态 |
| `mcp` | 启动MCP服务器（stdio） |
| `claude install\|uninstall` | 管理Claude Code集成 |
| `codex install\|uninstall` | 管理Codex CLI集成 |
| `gemini install\|uninstall` | 管理Gemini CLI集成 |
| `cursor install\|uninstall` | 管理Cursor IDE集成 |
| `windsurf install\|uninstall` | 管理Windsurf IDE集成 |
| `cline install\|uninstall` | 管理Cline集成 |
| `aider install\|uninstall` | 管理Aider CLI集成 |
| `opencode install\|uninstall` | 管理OpenCode集成 |

## 性能

在hedwig-cg自身代码库上的基准测试（约3,500行，90个文件，1,300个节点）：

| 操作 | 时间 |
|------|------|
| 完整构建 | ~14秒 |
| 增量构建（有变更） | ~4秒 |
| 增量构建（无变更） | ~0.4秒 |
| 冷搜索（双模型） | ~2.8秒 |
| 冷搜索（`--fast`） | ~0.2秒 |
| 热搜索 | ~0.08秒 |
| 缓存命中 | <1ms |

- **嵌入模型**: ~180MB，仅下载一次到`~/.hedwig-cg/models/`
- **数据库**: ~2MB（SQLite + FTS5 + FAISS索引）
- **增量构建**: SHA-256哈希，比完整构建快95%+

## 要求

- Python 3.10+
- 嵌入模型 ~180MB（首次使用时缓存）

```bash
# 可选：PDF提取
pip install hedwig-cg[docs]
```

## 开发

```bash
pip install -e ".[dev]"
pytest
ruff check hedwig_cg/
```

## 许可证

MIT License。参见[LICENSE](../LICENSE)。

## 贡献

欢迎贡献！参见[CONTRIBUTING.md](../CONTRIBUTING.md)。
