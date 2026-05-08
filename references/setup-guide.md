# 新机部署指南

## A. 环境依赖

### 必选
- **Python 3.11+**：`python3 --version`
- **Docker**：`docker --version`（用于 Neo4j 知识图谱容器）

### 推荐
- **uv**：`pip install uv`（加速虚拟环境创建和依赖安装）

### 快速检查
```bash
bash scripts/install.sh
```

## B. 环境变量配置

复制模板并编辑：
```bash
cp .env.example .env
```

必须/建议修改的配置项：

| 配置项 | 默认值 | 必须修改 | 说明 |
|--------|--------|---------|------|
| `LLM_API_KEY` | `your-api-key-here` | **必改** | LLM API 密钥。使用 jieba 实体提取时可不改 |
| `NEO4J_PASSWORD` | `ragpassword123` | 推荐 | Neo4j 数据库密码 |
| `EMBEDDING_DEVICE` | `cpu` | GPU 机器必改 | 设为 `gpu` 启用 GPU 加速 |
| `LOCAL_RAG_WORK_DIR` | `~/.local/share/local-rag` | 可选 | 自定义 RAG 数据目录 |
| `LLM_API_BASE` | `https://api.minimaxi.com/v1` | 可选 | 国内镜像需修改 |
| `LLM_MODEL` | `MiniMax-M2.7` | 可选 | 任意 OpenAI 兼容模型 |
| `GRAPH_ENTITY_EXTRACTOR` | `jieba` | 可选 | `jieba`（快速）或 `llm`（高质量） |

> `GRAPH_ENTITY_EXTRACTOR=jieba` 时，LLM_API_KEY 可以不修改。jieba 基于 TF-IDF 提取实体，无需调用 LLM。

## C. 一键启动

```bash
bash scripts/start.sh
```

start.sh 会自动完成以下步骤：
1. 创建 Python 虚拟环境（`.venv/`）
2. 安装依赖（`pyproject.toml` 已配置清华 PyPI 镜像 + PaddlePaddle CUDA 13.0 镜像）
3. 从 `.env.example` 创建 `.env`（如果不存在）
4. 启动 Neo4j Docker 容器（首次自动创建，后续自动启动）
5. 启动 RAG daemon（HTTP 后端服务）
6. 连接 stdio proxy（MCP 通信层）

首次启动约需 5-10 分钟（依赖安装 + Neo4j 拉取 + 模型下载）。

## D. 模型下载（国内镜像）

嵌入模型 `BAAI/bge-m3` 会自动从 ModelScope 下载（约 2-3 GB）：
- `pyproject.toml` 已配置清华 PyPI 镜像：`pypi.tuna.tsinghua.edu.cn`
- PaddleOCR 配置了 PaddlePaddle CUDA 13.0 国内镜像

如 ModelScope 不可用，会从 HuggingFace 下载（需网络代理或设置 `HF_ENDPOINT=https://hf-mirror.com`）。

## E. 验证服务

启动后，检查 daemon 是否运行：
```bash
curl -s http://localhost:27890/health
# 应返回: {"ok": true, ...}
```

或在 Claude Code 中调用 `graph_stats` MCP 工具测试连接。
