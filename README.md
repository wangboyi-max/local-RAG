# Local RAG — Claude Code 插件

本地部署的 Graph RAG（知识图谱 + 向量混合检索）MCP Server，支持 OCR 处理 PDF/图片，结合 Neo4j 知识图谱和向量混合检索。可作为 Claude Code 插件安装，支持升级不破坏已有数据。

## 功能特性

- **PaddleOCR GPU 加速**：处理扫描版 PDF 和 PNG/JPG/BMP/TIFF 图片，文字版 PDF 优先提取内置文字层
- **GPU 加速推理**：PaddleOCR 和 BGE-M3 均支持 GPU 加速
- **BGE-M3 中文增强嵌入**：支持 100+ 语言，中文检索效果优异
- **Neo4j 知识图谱**：自动从文档中提取实体和关系，构建可查询的知识图谱
- **混合检索**：ChromaDB 向量语义检索 + Neo4j 图谱实体扩展 + BM25 关键词匹配
- **笔记系统**：纯 Markdown 文件存储，支持文件重命名自动迁移 RAG 数据
- **MCP Server 协议**：Agent 可直接通过 stdio 调用工具

## 架构

```
文档 → OCR → 切分 → ┬→ ChromaDB (向量索引)
                     └→ Neo4j (知识图谱：实体/关系)

查询 → ┬→ 向量语义检索（余弦相似度）
       ├→ BM25 关键词匹配
       └→ 图谱实体扩展（BFS 共现关联）
            ↓
       合并去重 → 返回结果
```

## 安装

### 前置要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) 包管理器
- Docker（用于运行 Neo4j）

### 插件安装（推荐）

在 Claude Code 中运行：

```
/plugin marketplace add wangboyi-max/local-RAG
/plugin install local-rag@local-rag-mcp
```

首次调用 MCP 工具时会自动完成所有初始化：创建虚拟环境、安装依赖、初始化数据目录、启动 Neo4j 容器。只需确保编辑 `.env` 设置 `LLM_API_KEY` 即可开始使用。

### 开发模式

```bash
cd /path/to/local_rag
bash scripts/install.sh   # 检查前置依赖
bash scripts/start.sh     # 启动 MCP Server
```

### 升级

在 Claude Code 中运行 `/plugin update local-rag`，或在开发目录：

```bash
git pull
bash scripts/upgrade.sh
```

升级只替换代码，外部数据目录 `~/.local/share/local-rag/` 完全不受影响。迁移系统在启动时自动检测版本差异并执行。

## 数据目录

```
~/.local/share/local-rag/
├── chroma_db/          # ChromaDB 向量数据
├── uploads/            # 已索引文件
├── notes/              # Markdown 笔记（纯 .md 文件）
│   ├── *.md
│   └── index.json      # 笔记元数据索引
├── tasks.json          # 异步任务状态
└── .installed_version  # 当前安装的版本号
```

可通过 `LOCAL_RAG_DATA_DIR` 环境变量或 `.env` 自定义路径。

## 下载嵌入模型

BGE-M3 模型约 2.3GB，首次启动时会自动下载。国内用户推荐从 ModelScope 手动下载：

```bash
uv pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('BAAI/bge-m3')"
```

## MCP 工具列表

| 工具 | 描述 |
|------|------|
| `search_docs` | 混合检索（向量 + BM25 + 图谱） |
| `ingest_file` | 索引 PDF/图片文件 |
| `list_docs` | 列出所有已索引文档 |
| `delete_docs` | 删除文档及其索引 |
| `graph_stats` | 图谱统计信息 |
| `create_note` | 创建 Markdown 笔记 |
| `get_note` | 获取笔记内容 |
| `update_note` | 更新笔记（支持重命名） |
| `delete_note` | 删除笔记 |
| `list_notes` | 列出所有笔记 |
| `reindex_note` | 手动重新索引笔记 |
| `search_notes` | 在笔记中搜索 |

## 配置项

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `LOCAL_RAG_DATA_DIR` | 外部数据目录 | `~/.local/share/local-rag` |
| `EMBEDDING_MODEL` | 嵌入模型 | `BAAI/bge-m3` |
| `EMBEDDING_DEVICE` | 嵌入设备 | `cpu` |
| `NEO4J_URI` | Neo4j 连接 | `bolt://localhost:7687` |
| `NEO4J_USER` | Neo4j 用户 | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j 密码 | `ragpassword123` |
| `GRAPH_ENTITY_EXTRACTOR` | 实体提取（jieba/llm） | `jieba` |
| `LLM_API_KEY` | LLM API Key（llm 模式必填） | 空 |
| `LLM_API_BASE` | LLM API Base | `https://api.minimaxi.com/v1` |
| `LLM_MODEL` | LLM 模型 | `MiniMax-M2.7` |
| `CHUNK_SIZE` | 文本块大小 | `1500` |
| `CHUNK_OVERLAP` | 文本块重叠 | `200` |
| `TOP_K` | 检索返回数量 | `4` |
| `BM25_ENABLED` | 启用 BM25 | `true` |
| `OCR_LANGUAGES` | OCR 语言 | `ch,en` |
| `OCR_DPI` | PDF 渲染 DPI | `200` |

## 支持的文件格式

| 类型 | 格式 |
|------|------|
| PDF | `.pdf`（扫描版和文字版均可） |
| 图片 | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff`, `.tif` |
| 笔记 | `.md`（纯 Markdown） |

## 知识图谱

### 图谱结构

```
(Chunk {source, page, text}) -[MENTIONS]-> (Entity {name, type})
(Entity) -[RELATED_TO {weight}]-> (Entity)   // 共现关系
```

支持 jieba（TF-IDF 快速）和 LLM（语义级高质量）两种实体提取模式。

### Neo4j Browser 可视化

打开 `http://localhost:7474`，登录 `neo4j` / `ragpassword123`：

```cypher
MATCH (n) OPTIONAL MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100
```

## GPU 加速

PaddleOCR 默认安装 GPU 版本（CUDA 13.0）。设置 `EMBEDDING_DEVICE=gpu` 启用 BGE-M3 GPU 推理。

## 开发

```bash
uv pip install -e ".[dev]"
python tests/test_e2e.py
python tests/test_mcp.py
```

## License

MIT
