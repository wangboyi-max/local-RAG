---
name: knowledge-hub
description: 统一知识检索——结合本地 Markdown 笔记和 RAG 知识库（PDF/文档），提供双源检索工作流。适用于需要获取领域知识、查找笔记、索引新文档的场景。
---

# Knowledge Hub

统一的知识检索接口，整合两个知识源：

| 知识源 | 类型 | 适用场景 |
|--------|------|---------|
| Markdown 笔记 | 短文本、结构化 | 具体配置、短期记录、操作指南 |
| RAG 知识库 | 长文档、PDF、理论 | 系统性知识、专业理论、长篇资料 |

## 检索工作流

当用户要求获取知识时，按以下步骤执行：

### 第一步：判断知识来源

- 用户提到"笔记"或"我记过的" → 直接查 Markdown 笔记
- 用户提到"文档"、"PDF"、"资料" → 查 RAG 知识库
- 不确定 → 两个都查

### 第二步：执行检索

**查笔记**：用 Glob 扫描 `notes/` 目录（`**/*.md`），用 Grep 关键词搜索，用 Read 读取相关文件。

**查 RAG**：用 `search_docs` MCP 工具检索已索引文档。如果用户提到的文档未索引，先用 `ingest_file` 工具索引。

### 第三步：综合回答

将两个来源的信息合并输出，标注每个信息的来源（笔记 / RAG 文档）。

## 笔记管理

笔记存放在当前工作目录下的 `.knowledge-hub/notes/` 目录。

- **创建笔记**: 直接用 Write 工具写入 `.knowledge-hub/notes/<title>.md`，然后用 `create_note` MCP 工具同步到 RAG
- **读取笔记**: 直接 Read 文件，或 `get_note(title)` MCP 工具
- **搜索笔记**: `search_notes(query)` MCP 工具，或 Grep
- **更新笔记**: 编辑文件后，调用 `reindex_note(title)` 重建 RAG 索引
- **删除笔记**: 删除文件 + `delete_note(title)` MCP 工具

## 文档索引

需要索引新 PDF/图片时：
1. 确认文件路径（绝对路径）
2. 调用 `ingest_file(file_path)` MCP 工具
3. 告知用户索引完成

## MCP 工具列表

| 工具 | 用途 |
|------|------|
| `search_docs` | 混合检索（向量+图谱） |
| `ingest_file` | 索引 PDF/图片 |
| `list_docs` | 查看已索引文档 |
| `delete_docs` | 删除已索引文档 |
| `graph_stats` | 知识图谱统计 |
| `create_note` | 创建笔记并同步 RAG |
| `get_note` | 读取笔记 |
| `list_notes` | 列出所有笔记 |
| `update_note` | 更新笔记 |
| `delete_note` | 删除笔记 |
| `reindex_note` | 重建笔记索引 |
| `search_notes` | 语义搜索笔记 |
| `task_status` | 查询异步任务状态 |

## 环境配置（首次使用前）

本 skill 自包含 RAG 服务源码和启动脚本，首次使用前需完成环境配置：

1. **检查依赖**：`bash scripts/install.sh`（Python 3.11+、Docker）
2. **配置环境变量**：复制 `.env.example` 为 `.env`，至少设置 `LLM_API_KEY`（使用 jieba 模式可跳过）
3. **启动服务**：`bash scripts/start.sh`（自动创建 `.knowledge-hub/.venv`、安装依赖、启动 Neo4j 和 daemon）
4. **模型下载**：BGE-M3 嵌入模型首次启动时自动从 ModelScope 下载（约 2-3 GB），PaddleOCR 模型约 500 MB

### 知识库目录结构

所有运行时数据存在 Claude Code 当前工作目录下的 `.knowledge-hub/` 中，skill 升级不影响知识库：

```
当前工作目录/
└── .knowledge-hub/
    ├── .venv/           ← Python 虚拟环境（自动创建）
    ├── notes/           ← 短文本 Markdown（Claude Code 直接 Read，可 git 跟踪）
    ├── rag/             ← 长文本 RAG 数据
    │   ├── chroma_db/   ← 向量数据库
    │   └── uploads/     ← 索引文件副本
    └── logs/            ← 启动日志
```

> 首次使用详细指南 → 参考：[references/setup-guide.md](references/setup-guide.md)
> 检索策略说明 → 参考：[references/workflow-detail.md](references/workflow-detail.md)
