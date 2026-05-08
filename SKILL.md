---
name: knowledge-hub
description: 本地 RAG 知识库——支持 OCR 处理扫描版 PDF/图片，结合 Neo4j 知识图谱和向量混合检索。笔记通过文件系统直接管理，不经过 MCP。
---

# Knowledge Hub

本地 RAG 知识库服务，支持 OCR 处理扫描版 PDF/图片，结合 Neo4j 知识图谱和向量混合检索。

## 检索工作流

当用户要求获取知识时：

1. **用户提到"笔记"或"我记过的"** → 直接查 Markdown 笔记（用 Glob 扫描 `.knowledge-hub/notes/` 目录，Grep 搜索，Read 读取）
2. **用户提到"文档"、"PDF"、"资料"** → 用 `search_docs` MCP 工具检索 RAG 知识库
3. **不确定** → 两个都查，合并输出

## 笔记管理

笔记存放在当前工作目录下的 `.knowledge-hub/notes/` 目录，**直接通过文件系统操作**（不经过 MCP 工具）：

- **创建/更新**: 用 Write 工具写入 `.knowledge-hub/notes/<title>.md`
- **读取**: 用 Read 工具直接读取 `.md` 文件
- **搜索**: 用 Glob + Grep 在 `notes/` 目录搜索
- **删除**: 用 Bash `rm` 删除文件

> 笔记是纯 Markdown 文件，可 git 跟踪。RAG 知识库负责处理 PDF/扫描文档等长文本。

## 文档索引

需要索引新 PDF/图片时：
1. 确认文件路径（绝对路径）
2. 调用 `ingest_file(file_path)` MCP 工具
3. 用 `task_status` 查询进度

## MCP 工具列表

| 工具 | 用途 |
|------|------|
| `search_docs` | 混合检索（向量+图谱） |
| `ingest_file` | 索引 PDF/图片 |
| `list_docs` | 查看已索引文档 |
| `delete_docs` | 删除已索引文档 |
| `graph_stats` | 知识图谱统计 |
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
