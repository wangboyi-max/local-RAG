---
name: knowledge-hub
description: 本地 RAG 知识库——支持 OCR 处理扫描版 PDF/图片，结合 Neo4j 知识图谱和向量混合检索。笔记通过文件系统直接管理，遵循 LLM Wiki 渐进式文档管理方法论。
---

# Knowledge Hub

本地 RAG 知识库服务，支持 OCR 处理扫描版 PDF/图片，结合 Neo4j 知识图谱和向量混合检索。

## 知识管理方法论

本系统基于 Karpathy 的 **LLM Wiki** 理念，采用**渐进式文档管理**：

- **Raw 层（原始资料）**：PDF/图片等原始文档，通过 `ingest_file` 索引到 RAG，LLM 只读不改
- **Wiki 层（编译笔记）**：`.knowledge-hub/notes/` 下的 Markdown 文件，LLM 主动阅读、编译、组织、链接
- **Schema 层（指令规则）**：即本文件，定义知识库结构、命名规范、操作流程

### 核心工作流：Ingest → Compile → Lint

1. **Ingest（摄入）**：将新资料（PDF/网页/笔记）纳入知识库，LLM 通读后提取关键观点、建立反向链接、更新索引
2. **Compile（编译）**：LLM 将原始资料"消化"为结构化的 Wiki 笔记——写摘要、建概念页、关联已有知识。一次摄入，全局更新
3. **Lint（检查）**：定期自检——发现矛盾标注、知识缺口建议、过时内容标记、死链修复

### 渐进式组织原则

- **起步阶段**：笔记直接放 `notes/` 根目录，不要预设分类
- **成长阶段**：当笔记超过 ~10 篇时，按主题自然分化出子目录（如 `notes/英语/`、`notes/编程/`）
- **复利效应**：每次查询生成的答案/总结应归档回 notes/，成为知识库的永久资产，而非一次性对话
- **质量优于数量**：少而精的笔记胜过多而杂，定期 Lint 清理低质量内容

## 检索工作流

当用户要求获取知识时：

1. **用户提到"笔记"或"我记过的"** → 先 Read `notes/index.md` 了解目录结构，按需 Read 具体笔记（笔记少时可直接 Glob `**/*.md` 全读）
2. **用户提到"文档"、"PDF"、"资料"** → 用 `search_docs` MCP 工具检索 RAG 知识库
3. **不确定** → 两个都查，合并输出

## 笔记管理

笔记存放在 `.knowledge-hub/notes/` 目录，**直接通过文件系统操作**（不经过 MCP 工具）。

### 目录索引

`notes/` 根目录下维护一个 `index.md`，作为渐进式披露的目录文件：
- **格式**：每个条目包含笔记标题、一句话摘要、相对路径
- **维护**：创建/删除/移动笔记时，LLM 同步更新 `index.md`
- **读取策略**：先读 `index.md` 了解全局结构 → 按需深入具体笔记文件

```markdown
# 知识库索引

## 英语
- [英语学习规划要点](英语/英语学习规划要点.md) — 二语习得理论、自然拼读、各年龄阶段规划
## 编程
- [RAG 架构设计](编程/RAG架构设计.md) — daemon + proxy 架构、OCR 索引流程
```

### 操作方式

- **创建/更新**: 用 Write 工具写入 `.knowledge-hub/notes/[<category>/]<title>.md`，同时更新 `index.md`
- **读取**: 先 Read `notes/index.md` 了解目录，再按需 Read 具体笔记
- **搜索**: 笔记少时直接读 index.md 定位；笔记多时用 Grep 递归搜索关键词
- **删除**: 用 Bash `rm` 删除文件或子目录，同时从 `index.md` 移除对应条目

> 笔记是纯 Markdown 文件，可 git 跟踪。index.md 是渐进式组织的骨架，保持精简可读。

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
    ├── notes/           ← Wiki 编译层：短文本 Markdown + index.md 目录索引
    │   ├── index.md     ← 渐进式披露：笔记目录 + 一句话摘要
    │   └── **/*.md      ← 按主题渐进式组织（如 notes/英语/、notes/编程/）
    ├── rag/             ← Raw 原始层：长文本 RAG 数据
    │   ├── chroma_db/   ← 向量数据库
    │   └── uploads/     ← 索引文件副本
    └── logs/            ← 启动日志
```

> 首次使用详细指南 → 参考：[references/setup-guide.md](references/setup-guide.md)
> 检索策略说明 → 参考：[references/workflow-detail.md](references/workflow-detail.md)
