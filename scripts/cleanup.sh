#!/usr/bin/env bash
# 清空知识库所有数据：ChromaDB、Neo4j、上传文件、笔记、任务记录
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PLUGIN_ROOT"

# 确定知识库工作目录
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

if [[ "$LOCAL_RAG_WORK_DIR" = /* ]]; then
    KB_DIR="$LOCAL_RAG_WORK_DIR"
else
    KB_DIR="$(pwd)/$LOCAL_RAG_WORK_DIR"
fi

echo "=== 知识库清理工具 ==="
echo "知识库目录: $KB_DIR"
echo ""

# 1. 检查 daemon 是否运行，尝试调用 clear_all API
DAEMON_PORT="${LOCAL_RAG_DAEMON_PORT:-27890}"
_health_check() {
    response=$(no_proxy=localhost,127.0.0.1 http_proxy= https_proxy= curl -s --max-time 3 "http://localhost:${DAEMON_PORT}/health" 2>/dev/null)
    echo "$response" | grep -q '"ok"'
}

if _health_check; then
    echo "[1/4] 调用 daemon 清空 API..."
    no_proxy=localhost,127.0.0.1 http_proxy= https_proxy= curl -s -X POST "http://localhost:${DAEMON_PORT}/api/clear_all" \
        -H "Content-Type: application/json" \
        -d '{"confirm": true}' 2>&1
    echo ""
else
    echo "[1/4] Daemon 未运行，跳过 API 调用"
fi

# 2. 清理 ChromaDB 和上传文件
echo "[2/4] 清理 ChromaDB 和上传文件..."
rm -rf "$KB_DIR/rag/chroma_db" "$KB_DIR/rag/uploads" "$KB_DIR/chroma_db" "$KB_DIR/uploads"
mkdir -p "$KB_DIR/rag/chroma_db" "$KB_DIR/rag/uploads"
echo "  ✓ ChromaDB/Uploads 已清空"

# 3. 清理笔记和任务记录
echo "[3/4] 清理笔记和任务记录..."
rm -f "$KB_DIR/notes"/*.md "$KB_DIR/tasks.json"
echo "  ✓ 笔记/任务记录已清空"

# 4. 清理 Neo4j 数据
if command -v docker &>/dev/null && docker ps --format '{{.Names}}' | grep -q '^neo4j-rag$'; then
    echo "[4/4] 清空 Neo4j 知识图谱数据..."
    docker stop neo4j-rag >/dev/null 2>&1
    # 清理持久化数据卷
    NEO4J_DATA="$HOME/neo4j-rag/data"
    if [ -d "$NEO4J_DATA" ]; then
        rm -rf "$NEO4J_DATA"
        echo "  ✓ Neo4j 持久化数据已清空 ($NEO4J_DATA)"
    fi
    docker start neo4j-rag >/dev/null 2>&1
    echo "  ✓ Neo4j 容器已重启"
else
    echo "[4/4] Neo4j 容器未运行，跳过"
fi

echo ""
echo "清理完成。"
