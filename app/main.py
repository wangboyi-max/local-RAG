"""MCP Server 入口，通过 stdio 传输协议启动。"""
import logging
import os
import subprocess

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    # 确定数据目录
    data_dir = os.environ.get("LOCAL_RAG_DATA_DIR", "./data")

    # 自动运行迁移
    try:
        from app.migrations import run_migrations, get_installed_version, get_code_version
        installed = get_installed_version(data_dir)
        code = get_code_version()
        if installed != code:
            logger.info("[main] 版本 %s → %s，执行迁移", installed, code)
            run_migrations(data_dir)
    except Exception:
        logger.exception("[main] 迁移执行失败，继续启动服务")

    # 确保 Neo4j 容器运行
    subprocess.run(
        ["docker", "start", "neo4j-rag"],
        capture_output=True,
    )

    from app.server import mcp
    mcp.run(transport="stdio")
