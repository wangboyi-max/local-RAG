"""薄 stdio MCP 代理：通过 httpx 转发所有工具调用到 daemon。"""
import httpx

from mcp.server.fastmcp import FastMCP

from app.config import settings

mcp = FastMCP(
    "Knowledge Hub",
    instructions="本地 RAG 知识库服务——支持 OCR 处理扫描版 PDF/图片，结合 Neo4j 知识图谱和向量混合检索。笔记请直接通过文件系统 Read 工具管理。",
)

DAEMON_URL = f"http://localhost:{settings.daemon_port}"
_client = httpx.Client(timeout=120.0)


def _call(endpoint: str, **kwargs) -> str:
    """调用 daemon HTTP 接口，返回格式化字符串。"""
    try:
        resp = _client.post(f"{DAEMON_URL}{endpoint}", json=kwargs)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            return f"错误：{data['error']}"
        return data["result"]
    except httpx.ConnectError:
        return "错误：无法连接 local-rag daemon，请确认服务已启动"
    except httpx.TimeoutException:
        return "错误：请求超时，请稍后重试"


@mcp.tool()
def search_docs(query: str, top_k: int = 4) -> str:
    """混合检索知识库（向量语义 + 知识图谱实体扩展），返回相关文本块及来源。"""
    return _call("/api/search_docs", query=query, top_k=top_k)


@mcp.tool()
def ingest_file(file_path: str) -> str:
    """将指定的 PDF 或图片文件索引到知识库中（含图谱构建）。file_path 为本地文件的绝对路径。"""
    return _call("/api/ingest_file", file_path=file_path)


@mcp.tool()
def list_docs() -> str:
    """列出知识库中所有已索引的文档及其统计信息。"""
    return _call("/api/list_docs")


@mcp.tool()
def delete_docs(source: str) -> str:
    """从知识库中删除指定文档及其所有索引数据（含图谱节点）。source 为文件名。"""
    return _call("/api/delete_docs", source=source)


@mcp.tool()
def graph_stats() -> str:
    """返回知识图谱的统计信息（节点数、关系数）。"""
    return _call("/api/graph_stats")


@mcp.tool()
def task_status(task_id: str | None = None) -> str:
    """查询异步任务状态。不传 task_id 返回所有任务列表。"""
    return _call("/api/task_status", task_id=task_id)


if __name__ == "__main__":
    mcp.run(transport="stdio")
