<p align="center">
  <h1 align="center">hedwig-kg</h1>
  <p align="center">
    面向 AI 编程代理的本地优先知识图谱构建器
    <br />
    <a href="#ai-编程代理集成">集成</a> · <a href="#快速开始">快速开始</a> · <a href="#架构">架构</a> · <a href="../README.md">English</a> · <a href="README_ko.md">한국어</a> · <a href="README_ja.md">日本語</a> · <a href="README_de.md">Deutsch</a>
  </p>
</p>

---

**hedwig-kg** 从源代码和文档构建知识图谱，并通过双嵌入模型（代码专用 + 文本专用）经 RRF 融合提供 **5 信号 HybridRAG 搜索**。一切 **100% 本地运行** — 无需云端 API，数据不会离开您的机器。

## AI 编程代理集成

一条命令即可与主流 AI 编程代理集成。每个集成会写入平台专用的上下文文件和 hook，使代理在搜索原始文件之前自动利用知识图谱。

```bash
pip install hedwig-kg
```

### Claude Code

```bash
hedwig-kg claude install
```

写入 `CLAUDE.md` 段落 + `.claude/settings.json` PreToolUse hook。

### OpenAI Codex CLI

```bash
hedwig-kg codex install
```

写入 `AGENTS.md` 段落 + `.codex/hooks.json` PreToolUse hook。

### Google Gemini CLI

```bash
hedwig-kg gemini install
```

写入 `GEMINI.md` 段落 + `.gemini/settings.json` BeforeTool hook。

### 工作原理

每个 `install` 命令执行两项操作：

1. **上下文文件** — 在平台上下文文件中添加 `## hedwig-kg` 段落
2. **Hook** — 注册一个在工具调用前触发的轻量 shell hook

卸载：`hedwig-kg <platform> uninstall`

### 系统要求

- Python 3.10+
- 双嵌入模型约需 ~250MB 磁盘空间（首次使用时缓存至 `~/.hedwig-kg/models/`）

### 可选依赖

```bash
# PDF 文本提取
pip install hedwig-kg[docs]
```

## 快速开始

### 1. 安装与构建

```bash
pip install hedwig-kg
cd ./my-project
hedwig-kg build .
```

首次构建会扫描所有文件、提取 AST 结构、使用双模型生成嵌入（首次运行约下载 ~250MB，缓存至 `~/.hedwig-kg/models/`）、检测社区，并将所有内容存储在 `.hedwig-kg/knowledge.db` 中。

### 2. 搜索

```bash
hedwig-kg search "认证处理器"
```

### 3. 集成代理

```bash
hedwig-kg claude install   # Claude Code
hedwig-kg codex install    # Codex CLI
hedwig-kg gemini install   # Gemini CLI
```

### 4. 保持更新

```bash
hedwig-kg build . --incremental
```

### 5. 探索

```bash
hedwig-kg stats                           # 图谱概览
hedwig-kg communities --search "auth"     # 社区探索
hedwig-kg node "AuthHandler"              # 节点详情
hedwig-kg query                           # 交互式 REPL
hedwig-kg visualize                       # HTML 可视化
```

## 架构

```
源代码/文档 → 检测 → 提取 → 构建图谱 → 嵌入 → 聚类 → 摘要 → 分析 → 存储
```

### HybridRAG 搜索（5 信号）

1. **代码向量搜索** — 使用 `BAAI/bge-small-en-v1.5` 嵌入查询，通过 FAISS 搜索代码节点（函数、类、方法）
2. **文本向量搜索** — 使用 `all-MiniLM-L6-v2` 嵌入查询，通过 FAISS 搜索文档节点（标题、段落、文档字符串）
3. **图谱扩展** — 从顶部向量结果遍历 N 跳邻居
4. **关键词搜索** — FTS5 全文搜索（BM25 排序）
5. **社区搜索** — 将查询与社区摘要匹配
5. **RRF 融合** — 将所有信号合并为统一排序

## 许可证

MIT License。详情参见 [LICENSE](../LICENSE)。
