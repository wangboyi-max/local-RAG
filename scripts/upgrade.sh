#!/usr/bin/env bash
# local-rag 升级脚本：git pull 后执行，自动检测版本差异并运行迁移
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PLUGIN_ROOT"

echo "=== Local RAG 升级检查 ==="

# 检查 Python
if ! command -v python3 &>/dev/null; then
    echo "错误：未找到 python3" >&2
    exit 1
fi

# 检查 uv
if ! command -v uv &>/dev/null; then
    echo "错误：未找到 uv" >&2
    exit 1
fi

# 检查 Docker
if ! command -v docker &>/dev/null; then
    echo "错误：未找到 docker" >&2
    exit 1
fi

echo "✓ 依赖检查通过"

# 确保 venv 存在
if [ ! -d ".venv" ]; then
    echo "→ 创建虚拟环境..."
    uv venv
fi

# 更新依赖
echo "→ 更新依赖..."
uv pip install -e .
echo "✓ 依赖已更新"

# 设置数据目录
DATA_DIR="${LOCAL_RAG_DATA_DIR:-${HOME}/.local/share/local-rag}"
echo "→ 数据目录: $DATA_DIR"

# 确保 Neo4j 运行
if docker ps --format '{{.Names}}' | grep -q '^neo4j-rag$'; then
    echo "✓ Neo4j 运行中"
elif docker ps -a --format '{{.Names}}' | grep -q '^neo4j-rag$'; then
    echo "→ 启动 Neo4j..."
    docker start neo4j-rag
else
    echo "→ 创建 Neo4j 容器..."
    docker run -d --name neo4j-rag \
        -p 7687:7687 -p 7474:7474 \
        -v "$HOME/neo4j-rag/data:/data" \
        -e NEO4J_AUTH=neo4j/ragpassword123 \
        neo4j:2025
fi
echo "✓ Neo4j 就绪"

# 运行迁移
echo "→ 检查迁移..."
.venv/bin/python -c "
import os
os.environ['LOCAL_RAG_DATA_DIR'] = '$DATA_DIR'
from app.migrations import run_migrations
run_migrations('$DATA_DIR')
"
echo "✓ 迁移完成"

VERSION=$(cat VERSION 2>/dev/null || echo "unknown")
echo ""
echo "=== 升级完成 (v${VERSION}) ==="
echo "重启 Claude Code 或重新加载 MCP server 生效"
