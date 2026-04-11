<p align="center">
  <h1 align="center">hedwig-kg</h1>
  <p align="center">
    面向AI编程代理的本地优先知识图谱构建器
    <br />
    <a href="#快速开始">快速开始</a> · <a href="#支持的语言">语言</a> · <a href="#ai代理集成">集成</a> · <a href="#架构">架构</a> · <a href="../README.md">English</a> · <a href="README_ko.md">한국어</a> · <a href="README_ja.md">日本語</a> · <a href="README_de.md">Deutsch</a>
  </p>
</p>

<p align="center">
  <a href="https://github.com/hedwig-ai/hedwig-knowledge-graph/actions"><img src="https://img.shields.io/github/actions/workflow/status/hedwig-ai/hedwig-knowledge-graph/ci.yml?branch=main" alt="CI"></a>
  <a href="https://pypi.org/project/hedwig-kg/"><img src="https://img.shields.io/pypi/v/hedwig-kg" alt="PyPI"></a>
  <a href="https://github.com/hedwig-ai/hedwig-knowledge-graph/blob/main/LICENSE"><img src="https://img.shields.io/github/license/hedwig-ai/hedwig-knowledge-graph" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
</p>

---

## 为什么选择 hedwig-kg？

用Claude Code开发时，你是否感觉到某些不对劲的地方？

比如，在开发支付领域时，我们自然会联想到信用卡、Stripe、钱——这些概念直觉地联系在一起。

但编程代理看不到这些联系。它只是反复搜索"Payment"这个词。对它来说，"Payment"和"Card"是完全不相关的。

为了弥合这个差距，我构建了一个通过创建知识图谱为知识赋予意义的产品——让编程代理能够像人类一样推理。

有了它，Claude Code可以更直观地探索代码库，节省token，甚至发现以前找不到的代码。

<img width="1919" height="991" alt="Knowledge Graph" src="https://github.com/user-attachments/assets/a169c526-bb7c-4900-91dd-4db637793e32" />

## 快速开始

```bash
pip install hedwig-kg
hedwig-kg claude install
```

然后告诉Claude Code：

> "为这个项目构建知识图谱"

就这样。Claude Code会构建图谱，之后每次搜索都会自动参考。代码变更后：

> "重新构建知识图谱"

## 支持的语言

### 深度AST提取（17种语言）

hedwig-kg使用[tree-sitter tags.scm](https://tree-sitter.github.io/tree-sitter/4-code-navigation.html)进行通用结构提取——函数、类、方法、调用、import、继承——无需针对每种语言编写自定义代码。

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

hedwig-kg通过一个命令与主要AI编程代理集成：

| 代理 | 安装 | 说明 |
|------|------|------|
| **Claude Code** | `hedwig-kg claude install` | Skill + CLAUDE.md + PreToolUse钩子 |
| **Codex CLI** | `hedwig-kg codex install` | AGENTS.md + PreToolUse钩子 |
| **Gemini CLI** | `hedwig-kg gemini install` | GEMINI.md + BeforeTool钩子 |
| **Cursor IDE** | `hedwig-kg cursor install` | `.cursor/rules/`规则文件 |
| **Windsurf IDE** | `hedwig-kg windsurf install` | `.windsurf/rules/`规则文件 |
| **Cline** | `hedwig-kg cline install` | `.clinerules`文件 |
| **Aider CLI** | `hedwig-kg aider install` | CONVENTIONS.md + `.aider.conf.yml` |
| **MCP服务器** | `claude mcp add hedwig-kg -- hedwig-kg mcp` | Model Context Protocol 5个工具 |

每个`install`会写入上下文文件，并（在支持的平台上）注册工具调用前的钩子。卸载：`hedwig-kg <platform> uninstall`。

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

### 混合搜索（5个信号）

1. **代码向量** — `BAAI/bge-small-en-v1.5`嵌入代码节点，FAISS余弦搜索
2. **文本向量** — `intfloat/multilingual-e5-small`嵌入文本节点（100+语言）
3. **图扩展** — 从向量命中进行BFS，按边质量加权
4. **关键词** — FTS5全文搜索，覆盖完整源代码
5. **社区** — Leiden聚类摘要提升相关节点
6. **RRF融合** — 加权逆排名融合组合所有信号

## 性能

在hedwig-kg自身代码库上的基准测试（约3,500行，90个文件，1,300个节点）：

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
