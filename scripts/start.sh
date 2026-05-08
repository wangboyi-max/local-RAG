#!/usr/bin/env bash
# 启动 knowledge-hub MCP Server（Daemon + Proxy 架构）
# 首次启动自动完成所有初始化：venv、依赖、.env、Neo4j、数据目录、daemon
# 所有运行时数据（.venv、ChromaDB、uploads、notes、logs）统一存在 .knowledge-hub/ 下

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PLUGIN_ROOT"

# ── 确定知识库工作目录（与 config.py 逻辑一致）────────────
if [ -z "$LOCAL_RAG_WORK_DIR" ]; then
    if [ -f ".env" ]; then
        _env_val=$(grep '^LOCAL_RAG_WORK_DIR=' ".env" 2>/dev/null | head -1 | cut -d= -f2-)
        if [ -n "$_env_val" ]; then
            export LOCAL_RAG_WORK_DIR="$_env_val"
        fi
    fi
    if [ -z "$LOCAL_RAG_WORK_DIR" ]; then
        export LOCAL_RAG_WORK_DIR="./.knowledge-hub"
    fi
fi

# 解析为绝对路径
if [[ "$LOCAL_RAG_WORK_DIR" = /* ]]; then
    KB_DIR="$LOCAL_RAG_WORK_DIR"
else
    KB_DIR="$(pwd)/$LOCAL_RAG_WORK_DIR"
fi
KB_DIR="$(cd "$(dirname "$KB_DIR")" 2>/dev/null && pwd)/$(basename "$KB_DIR")" 2>/dev/null || KB_DIR="$(pwd)/.knowledge-hub"
mkdir -p "$KB_DIR"

# ── 日志目录 ─────────────────────────────────────────────
LOG_DIR="$KB_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/startup.log"

# ── 1. 确保 Python 可用 ──────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[knowledge-hub] 错误：未找到 Python3" >> "$LOG_FILE"
    exit 1
fi

# ── 2. 确保 venv + 依赖（放在 KB_DIR 下）─────────────────
VENV_DIR="$KB_DIR/.venv"
PYTHON="$VENV_DIR/bin/python"

if [ ! -d "$VENV_DIR" ]; then
    echo "[knowledge-hub] 首次启动：创建虚拟环境 ($KB_DIR/.venv)" >> "$LOG_FILE"
    if command -v uv &>/dev/null; then
        uv venv --python python3 "$VENV_DIR" >> "$LOG_FILE" 2>&1
    else
        python3 -m venv "$VENV_DIR" >> "$LOG_FILE" 2>&1
    fi
fi

# 检查关键依赖是否已安装（每次启动自动同步）
if ! "$PYTHON" -c "import pydantic, httpx, mcp" 2>/dev/null; then
    echo "[knowledge-hub] 安装/更新依赖..." >> "$LOG_FILE"
    if command -v uv &>/dev/null; then
        uv pip install -e "$PLUGIN_ROOT" --python "$VENV_DIR/bin/python" >> "$LOG_FILE" 2>&1
    else
        "$PYTHON" -m pip install -e "$PLUGIN_ROOT" >> "$LOG_FILE" 2>&1
    fi
fi

# ── 3. 确保 .env ─────────────────────────────────────────
if [ ! -f ".env" ] && [ -f ".env.example" ]; then
    cp .env.example .env
    echo "[knowledge-hub] 已从 .env.example 创建 .env" >> "$LOG_FILE"
fi

# ── 4. 设置工作路径环境变量（供 config.py 读取）───────────
export LOCAL_RAG_WORK_DIR="$KB_DIR"

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
    DAEMON_PID=$!
    # 等待 daemon 就绪（PaddleOCR 加载可能需 30-60 秒，最长等 120 秒）
    for i in $(seq 1 240); do
        if ! kill -0 $DAEMON_PID 2>/dev/null; then
            echo "[knowledge-hub] daemon 进程异常退出，请检查日志: $LOG_FILE" >> "$LOG_FILE"
            break
        fi
        if _health_check; then
            echo "[knowledge-hub] Daemon 就绪 (${i}/2 秒)" >> "$LOG_FILE"
            break
        fi
        sleep 0.5
    done
fi

# ── 7. 启动 stdio Proxy（替换当前 shell 进程）────────────
# 静默 stderr，避免干扰 MCP stdio 协议
exec 2>/dev/null
exec "$PYTHON" -m app.proxy
