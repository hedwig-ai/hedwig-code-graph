<p align="center">
  <h1 align="center">hedwig-cg</h1>
  <p align="center">
    "海德薇一定会带着消息回来的"
    <br />
    <a href="#快速开始">快速开始</a> · <a href="#支持的语言">语言</a> · <a href="#ai代理集成">集成</a> · <a href="#架构">架构</a> · <a href="../README.md">English</a> · <a href="README_ko.md">한국어</a> · <a href="README_ja.md">日本語</a> · <a href="README_de.md">Deutsch</a>
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

hedwig-cg从代码、文档和依赖关系构建统一的知识图谱——让编程代理真正理解你的整个项目，而不仅仅是搜索关键词。安装后，Claude Code就能看到全貌——无需额外的token，无需额外的命令，一切100%本地运行。

<img width="1919" height="991" alt="Code Graph" src="https://github.com/user-attachments/assets/a169c526-bb7c-4900-91dd-4db637793e32" />

## 快速开始

```bash
pip install hedwig-cg
hedwig-cg claude install
```

然后告诉Claude Code：

> "为这个项目构建知识图谱"

就这样。Claude Code会构建图谱，之后每次搜索都会自动参考。代码变更后：

> "重新构建知识图谱"

## 支持的语言

### 深度AST提取（17种语言）

hedwig-cg使用[tree-sitter tags.scm](https://tree-sitter.github.io/tree-sitter/4-code-navigation.html)进行通用结构提取——函数、类、方法、调用、import、继承——无需针对每种语言编写自定义代码。

| | | | |
|:---:|:---:|:---:|:---:|
| Python | JavaScript | TypeScript | Go |
| Rust | Java | C | C++ |
| C# | Ruby | Swift | Scala |
| Lua | PHP | Elixir | Kotlin |
| Objective-C | | | |

还可检测和索引：Markdown、PDF、HTML、CSV、YAML、JSON、TOML、Shell、R等。

### 多语言自然语言支持

文本节点（文档、注释、markdown）使用`intfloat/multilingual-e5-small`嵌入，支持**100多种自然语言**——中文、韩语、日语、德语、法语等。用你的语言搜索，找到任何语言的结果。

## AI代理集成

hedwig-cg通过一个命令与主要AI编程代理集成：

| 代理 | 安装 | 说明 |
|------|------|------|
| **Claude Code** | `hedwig-cg claude install` | Skill + CLAUDE.md + PreToolUse钩子 |
| **Codex CLI** | `hedwig-cg codex install` | AGENTS.md + PreToolUse钩子 |
| **Gemini CLI** | `hedwig-cg gemini install` | GEMINI.md + BeforeTool钩子 |
| **Cursor IDE** | `hedwig-cg cursor install` | `.cursor/rules/`规则文件 |
| **Windsurf IDE** | `hedwig-cg windsurf install` | `.windsurf/rules/`规则文件 |
| **Cline** | `hedwig-cg cline install` | `.clinerules`文件 |
| **Aider CLI** | `hedwig-cg aider install` | CONVENTIONS.md + `.aider.conf.yml` |
| **MCP服务器** | `claude mcp add hedwig-cg -- hedwig-cg mcp` | Model Context Protocol 5个工具 |

每个`install`会写入上下文文件，并（在支持的平台上）注册工具调用前的钩子。卸载：`hedwig-cg <platform> uninstall`。

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

## 架构

```
源代码/文档
       |
       v
   检测 ──> 提取 ──> 构建 ──> 嵌入 ──> 聚类 ──> 分析 ──> 存储
           tags.scm  NetworkX  双模型    Leiden    PageRank  SQLite
           (17种)    DiGraph   FAISS    层次结构   核心节点  FTS5+FAISS
```

### 5信号混合搜索

每个搜索查询经过5个独立的检索信号，然后融合为单一排名结果：

| 信号 | 引擎 | 搜索内容 |
|------|------|----------|
| **代码向量** | FAISS + `bge-small-en-v1.5` | 语义相似的代码（函数、类、方法） |
| **文本向量** | FAISS + `multilingual-e5-small` | 文档、注释、Markdown（100+语言） |
| **图扩展** | NetworkX加权BFS | 结构连接的节点（调用者、被调用者、导入） |
| **全文搜索** | SQLite FTS5 + BM25 | 源代码全文精确关键词匹配 |
| **社区上下文** | Leiden聚类 | 同一功能集群的相关节点 |
| **RRF融合** | 加权逆排名融合 | 组合所有信号——被多个信号发现的节点排名更高 |

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

## 要求

- Python 3.10+
- 嵌入模型 ~470MB（首次使用时缓存）

## 许可证

MIT License。参见[LICENSE](../LICENSE)。

## 贡献

欢迎贡献！参见[CONTRIBUTING.md](../CONTRIBUTING.md)。
