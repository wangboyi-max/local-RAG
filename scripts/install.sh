#!/usr/bin/env bash
# local-rag 首次安装脚本
# 检查依赖、创建 venv、安装依赖、创建数据目录、启动 Neo4j、运行迁移
set -e

PLUGIN_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PLUGIN_ROOT"

echo "=== Local RAG 安装检查 ==="

# 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "错误：未找到 python3" >&2
    exit 1
fi
echo "✓ Python: $(python3 --version)"

# 检查 uv
if ! command -v uv &>/dev/null; then
    echo "错误：未找到 uv，请先安装: https://docs.astral.sh/uv/" >&2
    exit 1
fi
echo "✓ uv: $(uv --version)"

# 检查 Docker
if ! command -v docker &>/dev/null; then
    echo "错误：未找到 docker" >&2
    exit 1
fi
echo "✓ Docker: $(docker --version)"

# 创建虚拟环境
if [ ! -d ".venv" ]; then
    echo "→ 创建虚拟环境..."
    uv venv
fi
echo "✓ 虚拟环境就绪"

# 安装依赖
echo "→ 安装依赖..."
uv pip install -e .
echo "✓ 依赖安装完成"

# 创建 .env
if [ ! -f ".env" ]; then
    echo "→ 从 .env.example 创建 .env..."
    cp .env.example .env
    echo "⚠ 请编辑 .env 设置 LLM_API_KEY"
fi
echo "✓ 配置文件就绪"

# 选择数据目录
DEFAULT_DATA_DIR="${HOME}/.local/share/local-rag"
echo ""
echo "请选择数据目录路径："
echo "  1) $DEFAULT_DATA_DIR (推荐)"
echo "  2) 自定义路径"
read -p "选择 [1/2]: " dir_choice

if [ "$dir_choice" = "2" ]; then
    read -p "输入数据目录路径: " DATA_DIR
    # 展开 ~ 符号
    DATA_DIR="${DATA_DIR/#\~/$HOME}"
    if [ -z "$DATA_DIR" ]; then
        echo "路径为空，使用默认路径: $DEFAULT_DATA_DIR"
        DATA_DIR="$DEFAULT_DATA_DIR"
    fi
else
    DATA_DIR="$DEFAULT_DATA_DIR"
fi
echo "→ 数据目录: $DATA_DIR"
mkdir -p "$DATA_DIR/chroma_db" "$DATA_DIR/uploads" "$DATA_DIR/notes"
echo "✓ 数据目录已创建"

# 写入 .env
if grep -q "^LOCAL_RAG_DATA_DIR" .env 2>/dev/null; then
    sed -i "s|^LOCAL_RAG_DATA_DIR=.*|LOCAL_RAG_DATA_DIR=$DATA_DIR|" .env
else
    echo "LOCAL_RAG_DATA_DIR=$DATA_DIR" >> .env
fi
echo "✓ .env 已写入 LOCAL_RAG_DATA_DIR=$DATA_DIR"

# 启动 Neo4j
if ! docker ps -a --format '{{.Names}}' | grep -q '^neo4j-rag$'; then
    echo "→ 启动 Neo4j 容器..."
    docker run -d --name neo4j-rag \
        -p 7687:7687 -p 7474:7474 \
        -v "$HOME/neo4j-rag/data:/data" \
        -e NEO4J_AUTH=neo4j/ragpassword123 \
        neo4j:2025
    echo "✓ Neo4j 已启动"
else
    echo "✓ Neo4j 容器已存在"
fi

# 运行迁移
echo "→ 运行数据迁移..."
export LOCAL_RAG_DATA_DIR="$DATA_DIR"
.venv/bin/python -c "
import os
os.environ['LOCAL_RAG_DATA_DIR'] = '$DATA_DIR'
from app.migrations import run_migrations
run_migrations('$DATA_DIR')
"
echo "✓ 迁移完成"

VERSION=$(cat VERSION 2>/dev/null || echo "unknown")
echo ""
echo "=== 安装完成 (v${VERSION}) ==="
echo "数据目录: $DATA_DIR"
echo "启动服务: bash scripts/start.sh"
echo "MCP 配置: 在 Claude Code 中运行 claude mcp add --transport stdio local-rag -- bash ${PLUGIN_ROOT}/scripts/start.sh"
