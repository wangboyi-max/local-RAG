# Graph RAG MCP Server

本地部署的 Graph RAG（知识图谱 + 向量混合检索）MCP Server，支持扫描版 PDF 和图片的 OCR 处理，可被 Claude Code 等 Agent 框架通过 MCP 协议调用。

## 功能特性

- **PaddleOCR GPU 加速**：处理扫描版 PDF 和 PNG/JPG/BMP/TIFF 图片，文字版 PDF 优先提取内置文字层
- **GPU 加速推理**：PaddleOCR 和 BGE-M3 均支持 GPU 加速
- **BGE-M3 中文增强嵌入**：支持 100+ 语言，中文检索效果优异
- **Neo4j 知识图谱**：自动从文档中提取实体和关系，构建可查询的知识图谱
- **混合检索**：ChromaDB 向量语义检索 + Neo4j 图谱实体扩展，互补提升召回率
- **MCP Server 协议**：Agent 可直接通过 stdio 调用工具，检索到的文本片段由 Agent 自行理解整合

## 架构

```
文档 → OCR → 切分 → ┬→ ChromaDB (向量索引)
                     └→ Neo4j (知识图谱：实体/关系)

查询 → ┬→ 向量语义检索（余弦相似度）
       └→ 图谱实体扩展（BFS 共现关联）
            ↓
       合并去重 → 返回结果
```

## 快速开始

### 前置要求

- Python 3.10+
- Docker（用于运行 Neo4j）
- [uv](https://docs.astral.sh/uv/) 包管理器（推荐）或 pip

### 安装

```bash
cd /home/wangboyi/workspace/local_rag

# 使用 uv（推荐，速度快）
uv venv
source .venv/bin/activate
uv pip install -e .
```

### 启动 Neo4j

```bash
docker run -d --name neo4j-rag \
  -p 7687:7687 -p 7474:7474 \
  -v $HOME/neo4j-rag/data:/data \
  -e NEO4J_AUTH=neo4j/ragpassword123 \
  neo4j:2025
```

- `bolt://localhost:7687` — 数据库连接地址
- `http://localhost:7474` — Neo4j Browser（可视化查询图谱）
- 默认用户名/密码：`neo4j` / `ragpassword123`

### 下载嵌入模型

BGE-M3 模型约 2.3GB，首次启动时会自动下载。国内用户推荐从 ModelScope 下载：

```bash
# 方式一：启动前手动下载（更快更稳定）
uv pip install modelscope
python -c "from modelscope import snapshot_download; snapshot_download('BAAI/bge-m3')"
```

### 配置

```bash
cp .env.example .env
```

编辑 `.env` 可按需调整检索参数（chunk_size、top_k、Neo4j 连接等）。

### 启动

```bash
python -m app.main
```

服务将以 stdio 模式运行（不监听端口，通过标准输入输出与 MCP Client 通信）。

### 配置 MCP Client（Claude Code 示例）

在 `~/.claude/settings.json` 中添加：

```json
{
  "mcpServers": {
    "local-rag": {
      "command": "/home/wangboyi/workspace/local_rag/.venv/bin/python",
      "args": ["-m", "app.main"],
      "cwd": "/home/wangboyi/workspace/local_rag"
    }
  }
}
```

重启 Claude Code 后即可自动连接。

## MCP 工具列表

| 工具 | 描述 | 参数 |
|------|------|------|
| `search_docs` | 混合检索知识库（向量语义 + 知识图谱实体扩展），返回相关文本片段 | `query` (str), `top_k` (int, 默认 4) |
| `ingest_file` | 将指定的 PDF 或图片文件索引到知识库中（同时构建图谱）。文字版 PDF 秒级完成，扫描版走 GPU OCR | `file_path` (str, 本地文件绝对路径) |
| `list_docs` | 列出所有已索引的文档及其统计信息 | 无 |
| `delete_docs` | 从知识库中删除指定文档及其所有索引数据（含图谱节点） | `source` (str, 文件名) |
| `graph_stats` | 返回知识图谱的统计信息（文本块节点数、实体节点数、关系边数） | 无 |

## 使用示例

在 Claude Code 中可以直接对话调用：

```
> 帮我搜索一下关于用户权限管理的内容
  (Claude 自动调用 search_docs 工具，获取相关文本片段后自行回答)

> 把 /path/to/scanned.pdf 索引到知识库
  (Claude 自动调用 ingest_file 工具)

> 看看知识图谱现在有多少实体
  (Claude 自动调用 graph_stats 工具)
```

## 配置项

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `EMBEDDING_MODEL` | 嵌入模型名称 | `BAAI/bge-m3` |
| `EMBEDDING_DEVICE` | 嵌入模型运行设备 | `cpu` |
| `NEO4J_URI` | Neo4j 连接地址 | `bolt://localhost:7687` |
| `NEO4J_USER` | Neo4j 用户名 | `neo4j` |
| `NEO4J_PASSWORD` | Neo4j 密码 | `ragpassword123` |
| `GRAPH_ENTITY_EXTRACTOR` | 实体提取模式（jieba 或 llm） | `jieba` |
| `LLM_API_KEY` | LLM API Key（OpenAI 兼容格式，LLM 模式必填） | 空 |
| `LLM_API_BASE` | LLM API Base URL | `https://api.minimaxi.com/v1` |
| `LLM_MODEL` | 模型名称 | `MiniMax-M2.7` |
| `GRAPH_MAX_ENTITIES` | 每个文本块最多提取实体数 | `10` |
| `GRAPH_MAX_DEPTH` | 图谱扩展的最大跳数 | `2` |
| `CHROMA_DB_PATH` | ChromaDB 数据存储路径 | `./data/chroma_db` |
| `CHROMA_COLLECTION_NAME` | ChromaDB 集合名称 | `documents` |
| `CHUNK_SIZE` | 文本块大小 | `500` |
| `CHUNK_OVERLAP` | 文本块重叠 | `100` |
| `TOP_K` | 向量检索返回的文档数量 | `4` |
| `OCR_LANGUAGES` | OCR 识别语言 | `ch,en` |
| `OCR_DPI` | PDF 渲染 DPI | `200` |
| `UPLOAD_DIR` | 上传文件存储路径 | `./data/uploads` |

## 支持的文件格式

| 类型 | 格式 |
|------|------|
| PDF | `.pdf`（扫描版和文字版均可；文字版优先提取内置文字，秒级完成） |
| 图片 | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.tiff`, `.tif` |

## 知识图谱

### 图谱结构

文档索引时，系统自动从文本块中提取实体（基于 jieba 关键词 TF-IDF 提取），并构建以下图谱结构：

```
(Chunk {source, page, text}) -[MENTIONS]-> (Entity {name, type})
(Entity) -[RELATED_TO {weight}]-> (Entity)   // 共现关系
```

- `Chunk` 节点：每个文本块作为一个节点，存储原文和来源信息
- `Entity` 节点：从文本中提取的关键词作为实体
- `MENTIONS` 关系：文本块提及了某个实体
- `RELATED_TO` 关系：两个实体在同一文本块中共现，weight 表示共现次数

### 实体提取策略

支持两种实体提取模式，通过 `GRAPH_ENTITY_EXTRACTOR` 环境变量切换：

| 模式 | 说明 | 速度 | 质量 |
|------|------|------|------|
| `jieba`（默认） | TF-IDF 关键词提取，纯本地 | 快（毫秒级/块） | 一般 |
| `llm` | LLM API 语义实体提取 | 慢（秒级/块） | 高 |

**jieba 模式**：
- 基于 TF-IDF 算法提取关键词作为实体
- 过滤常见中文停用词，只保留长度 > 1 的实体

**LLM 模式**：
- 通过 LLM API（OpenAI 兼容格式）进行语义级实体提取
- 每个实体包含名称（name）和类型（type，如 concept/organization/technology 等）
- 支持任意兼容的 LLM API（MiniMax M2.7、通义千问、智谱、DeepSeek 等）
- 内置重试机制（最多 2 次）和错误日志，调用失败时不阻塞索引流程
- 每个文本块最多提取 `GRAPH_MAX_ENTITIES` 个实体

### 检索流程

`search_docs` 执行混合检索：
1. **向量分支**：BGE-M3 将查询转为向量，在 ChromaDB 中 cosine 相似度检索 top_k 个文本块
2. **图谱分支**：从查询中提取关键词，在 Neo4j 中匹配实体节点，BFS 扩展 2 跳获取关联的文本块
3. **合并去重**：向量结果 + 图谱结果，按 chunkId 去重后返回

### Neo4j Browser 可视化

1. 浏览器打开 `http://localhost:7474`
2. 输入用户名 `neo4j`，密码 `ragpassword123`
3. 执行 Cypher 查询查看图谱：
   ```cypher
   MATCH (n) OPTIONAL MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 100
   ```

## GPU 加速

本项目默认支持 GPU 加速：

- **PaddleOCR**：安装 `paddlepaddle-gpu` 后自动使用 GPU，无需额外配置
- **BGE-M3**：设置 `EMBEDDING_DEVICE=gpu` 即可启用 GPU 推理

安装 GPU 版本：

```bash
# 卸载 CPU 版本
uv pip uninstall paddlepaddle
# 安装 GPU 版本（从 paddle 官方源，CUDA 13.0）
uv pip install --no-deps "paddlepaddle-gpu>=3.3.0" --index-strategy unsafe-best-match --extra-index-url https://www.paddlepaddle.org.cn/packages/stable/cu130/
```

## 开发

```bash
# 安装开发依赖
uv pip install -e ".[dev]"

# 运行端到端测试
python tests/test_e2e.py

# 运行 MCP 协议测试
python tests/test_mcp.py

# 快速索引单个 PDF（实时显示进度）
python scripts/quick_ingest.py
```

## License

MIT
