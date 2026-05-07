#!/usr/bin/env bash
# local-rag 首次安装检查
# 实际初始化由 start.sh 自动完成（venv/依赖/.env/Neo4j/数据目录）
set -e

echo "=== Local RAG 安装检查 ==="

# 检查前置依赖
for cmd in python3 docker; do
    if command -v "$cmd" &>/dev/null; then
        echo "✓ $cmd: $("$cmd" --version 2>&1 | head -1)"
    else
        echo "✗ 未找到 $cmd，请先安装" >&2
        exit 1
    fi
done

if command -v uv &>/dev/null; then
    echo "✓ uv: $(uv --version)"
else
    echo "⚠ 未找到 uv（推荐安装），将使用系统 Python"
fi

echo ""
echo "首次启动时会自动创建 venv、安装依赖、初始化数据目录、启动 Neo4j"
echo "请确保编辑好 .env 文件中的 LLM_API_KEY"
echo ""
echo "安装完成，运行: bash scripts/start.sh"
