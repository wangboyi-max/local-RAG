#!/usr/bin/env bash
# 启动 local-rag MCP Server（Daemon + Proxy 架构）
# 首次启动自动完成所有初始化：venv、依赖、.env、Neo4j、数据目录、daemon

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PLUGIN_ROOT"

# ── 1. 确保 Python 可用 ──────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[local-rag] 错误：未找到 Python3" >&2
    exit 1
fi

# ── 2. 确保 venv + 依赖 ─────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "[local-rag] 首次启动：创建虚拟环境..." >&2
    if command -v uv &>/dev/null; then
        uv venv 2>&1 >&2
    fi
    PYTHON=".venv/bin/python"
else
    PYTHON=".venv/bin/python"
fi

# 检查关键依赖是否已安装（每次启动自动同步）
if ! "$PYTHON" -c "import pydantic, httpx, mcp" 2>/dev/null; then
    echo "[local-rag] 安装/更新依赖..." >&2
    if command -v uv &>/dev/null; then
        uv pip install -e . 2>&1 >&2
    else
        "$PYTHON" -m pip install -e . >&2
    fi
fi

# ── 3. 确保 .env ─────────────────────────────────────────
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo "[local-rag] 已从 .env.example 创建 .env，请编辑 .env 设置 LLM_API_KEY" >&2
fi

# ── 4. 设置数据目录 ──────────────────────────────────────
if [ -z "$LOCAL_RAG_DATA_DIR" ]; then
    # 优先读 .env 里的配置
    if [ -f ".env" ]; then
        _env_val=$(grep '^LOCAL_RAG_DATA_DIR=' ".env" 2>/dev/null | head -1 | cut -d= -f2-)
        if [ -n "$_env_val" ]; then
            export LOCAL_RAG_DATA_DIR="$_env_val"
        fi
    fi
    # 没有则用默认路径
    if [ -z "$LOCAL_RAG_DATA_DIR" ]; then
        export LOCAL_RAG_DATA_DIR="${HOME}/.local/share/local-rag"
    fi
fi

mkdir -p "$LOCAL_RAG_DATA_DIR/chroma_db" "$LOCAL_RAG_DATA_DIR/uploads" "$LOCAL_RAG_DATA_DIR/notes"

# ── 5. 确保 Neo4j 容器运行 ───────────────────────────────
if command -v docker &>/dev/null; then
    if docker ps --format '{{.Names}}' | grep -q '^neo4j-rag$'; then
        : # 已在运行
    elif docker ps -a --format '{{.Names}}' | grep -q '^neo4j-rag$'; then
        docker start neo4j-rag
    else
        docker run -d --name neo4j-rag \
            -p 7687:7687 -p 7474:7474 \
            -v "$HOME/neo4j-rag/data:/data" \
            -e NEO4J_AUTH=neo4j/ragpassword123 \
            neo4j:2025
    fi
fi

# ── 6. 启动 Daemon（如未运行）────────────────────────────
DAEMON_PORT="${LOCAL_RAG_DAEMON_PORT:-27890}"

_health_check() {
    response=$(curl -s --max-time 3 "http://localhost:${DAEMON_PORT}/health" 2>/dev/null)
    echo "$response" | grep -q '"ok"'
}

if _health_check; then
    echo "[local-rag] Daemon 已在运行 (port ${DAEMON_PORT})" >&2
else
    echo "[local-rag] 启动 daemon..." >&2
    "$PYTHON" -m app.daemon >> "$LOCAL_RAG_DATA_DIR/daemon.log" 2>&1 &

    # 等待 daemon 就绪（最长 60 秒）
    for i in $(seq 1 120); do
        if _health_check; then
            echo "[local-rag] Daemon 就绪" >&2
            break
        fi
        sleep 0.5
    done
fi

# ── 7. 启动 stdio Proxy（替换当前 shell 进程）────────────
exec "$PYTHON" -m app.proxy
