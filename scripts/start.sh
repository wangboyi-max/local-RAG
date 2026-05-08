#!/usr/bin/env bash
# 启动 knowledge-hub MCP Server（Daemon + Proxy 架构）
# 首次启动自动完成所有初始化：venv、依赖、.env、Neo4j、数据目录、daemon

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PLUGIN_ROOT"

# ── 日志重定向：stderr 输出会干扰 MCP stdio 协议，全部写入日志文件 ──
LOG_DIR="${HOME}/.local/share/knowledge-hub/logs"
mkdir -p "$LOG_DIR" 2>/dev/null || true
LOG_FILE="$LOG_DIR/startup.log"
exec 2>>"$LOG_FILE"

# ── 1. 确保 Python 可用 ──────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[knowledge-hub] 错误：未找到 Python3" >&2
    exit 1
fi

# ── 2. 确保 venv + 依赖 ─────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "[knowledge-hub] 首次启动：创建虚拟环境..." >&2
    if command -v uv &>/dev/null; then
        uv venv 2>>"$LOG_FILE"
    fi
    PYTHON=".venv/bin/python"
else
    PYTHON=".venv/bin/python"
fi

# 检查关键依赖是否已安装（每次启动自动同步）
if ! "$PYTHON" -c "import pydantic, httpx, mcp" 2>/dev/null; then
    echo "[knowledge-hub] 安装/更新依赖..." >&2
    if command -v uv &>/dev/null; then
        uv pip install -e . >>"$LOG_FILE" 2>&1
    else
        "$PYTHON" -m pip install -e . >>"$LOG_FILE" 2>&1
    fi
fi

# ── 3. 确保 .env ─────────────────────────────────────────
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo "[knowledge-hub] 已从 .env.example 创建 .env，请编辑 .env 设置 LLM_API_KEY" >&2
fi

# ── 4. 设置工作路径 ───────────────────────────────────────
if [ -z "$LOCAL_RAG_WORK_DIR" ]; then
    if [ -f ".env" ]; then
        _env_val=$(grep '^LOCAL_RAG_WORK_DIR=' ".env" 2>/dev/null | head -1 | cut -d= -f2-)
        if [ -n "$_env_val" ]; then
            export LOCAL_RAG_WORK_DIR="$_env_val"
        fi
    fi
    if [ -z "$LOCAL_RAG_WORK_DIR" ]; then
        export LOCAL_RAG_WORK_DIR="${HOME}/.local/share/knowledge-hub/rag"
    fi
fi

# ── 5. 确保 Neo4j 容器运行 ───────────────────────────────
if command -v docker &>/dev/null; then
    if docker ps --format '{{.Names}}' | grep -q '^neo4j-rag$'; then
        : # 已在运行
    elif docker ps -a --format '{{.Names}}' | grep -q '^neo4j-rag$'; then
        docker start neo4j-rag >>"$LOG_FILE" 2>&1
    else
        docker run -d --name neo4j-rag \
            -p 7687:7687 -p 7474:7474 \
            -v "$HOME/neo4j-rag/data:/data" \
            -e NEO4J_AUTH=neo4j/ragpassword123 \
            neo4j:2025 >>"$LOG_FILE" 2>&1
    fi
fi

# ── 6. 启动 Daemon（如未运行）────────────────────────────
DAEMON_PORT="${LOCAL_RAG_DAEMON_PORT:-27890}"

_health_check() {
    response=$(curl -s --max-time 3 "http://localhost:${DAEMON_PORT}/health" 2>/dev/null)
    echo "$response" | grep -q '"ok"'
}

if _health_check; then
    : # daemon 已在运行，静默跳过
else
    echo "[knowledge-hub] 启动 daemon..." >> "$LOG_FILE"
    "$PYTHON" -m app.daemon >>"$LOG_FILE" 2>&1 &
    # 等待 daemon 就绪（最长 60 秒）
    for i in $(seq 1 120); do
        if _health_check; then
            echo "[knowledge-hub] Daemon 就绪" >> "$LOG_FILE"
            break
        fi
        sleep 0.5
    done
fi

# ── 7. 启动 stdio Proxy（替换当前 shell 进程）────────────
# 注意：daemon 可能在旧 venv 中运行，但 proxy 通过 HTTP 通信，不影响
exec "$PYTHON" -m app.proxy
