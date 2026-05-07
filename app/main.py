"""MCP Server 入口，通过 stdio 传输协议启动。"""
import subprocess

if __name__ == "__main__":
    # 确保 Neo4j 容器运行
    subprocess.run(
        ["docker", "start", "neo4j-rag"],
        capture_output=True,
    )

    from app.server import mcp
    mcp.run(transport="stdio")
