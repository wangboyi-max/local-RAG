#!/usr/bin/env bash
# 启动 local-rag MCP Server
# 支持插件模式（从 ${CLAUDE_PLUGIN_ROOT}）和开发模式

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"

# 如果在插件目录下运行，使用插件 venv
if [ -d "${PLUGIN_ROOT}/.venv" ]; then
    PYTHON="${PLUGIN_ROOT}/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    echo "错误：未找到 Python" >&2
    exit 1
fi

# 设置默认数据目录
if [ -z "$LOCAL_RAG_DATA_DIR" ]; then
    # 优先读 .env 里的配置
    if [ -f "${PLUGIN_ROOT}/.env" ]; then
        _env_val=$(grep '^LOCAL_RAG_DATA_DIR=' "${PLUGIN_ROOT}/.env" 2>/dev/null | head -1 | cut -d= -f2-)
        if [ -n "$_env_val" ]; then
            export LOCAL_RAG_DATA_DIR="$_env_val"
        fi
    fi
    # .env 没有则用默认路径
    if [ -z "$LOCAL_RAG_DATA_DIR" ]; then
        export LOCAL_RAG_DATA_DIR="${HOME}/.local/share/local-rag"
    fi
fi

# 确保数据目录存在
mkdir -p "$LOCAL_RAG_DATA_DIR/chroma_db" "$LOCAL_RAG_DATA_DIR/uploads" "$LOCAL_RAG_DATA_DIR/notes"

cd "$PLUGIN_ROOT"
exec "$PYTHON" -m app.main
