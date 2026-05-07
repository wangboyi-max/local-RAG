"""薄 stdio MCP 代理：通过 httpx 转发所有工具调用到 daemon。"""
import httpx

from mcp.server.fastmcp import FastMCP

from app.config import settings

mcp = FastMCP(
    "Graph RAG",
    instructions="本地 Graph RAG 检索服务，支持 OCR 处理扫描版 PDF/图片，结合 Neo4j 知识图谱和向量混合检索。",
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


# ── 文档工具 ──────────────────────────────────────────────

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


# ── 笔记工具 ──────────────────────────────────────────────

@mcp.tool()
def create_note(title: str, content: str, tags: str | None = None) -> str:
    """创建 Markdown 笔记并异步同步到 RAG。tags 为逗号分隔的标签。返回 task_id，用 task_status 查询进度。"""
    return _call("/api/create_note", title=title, content=content, tags=tags)


@mcp.tool()
def get_note(title: str) -> str:
    """获取指定笔记的完整内容。title 为笔记文件名（标题）。"""
    return _call("/api/get_note", title=title)


@mcp.tool()
def list_notes(tag: str | None = None) -> str:
    """列出所有笔记，可选按标签过滤。"""
    return _call("/api/list_notes", tag=tag)


@mcp.tool()
def update_note(title: str, content: str | None = None, tags: str | None = None, new_title: str | None = None) -> str:
    """更新笔记。按标题定位，可更新内容、标签或重命名。内容变动会异步重建 RAG。"""
    return _call("/api/update_note", title=title, content=content, tags=tags, new_title=new_title)


@mcp.tool()
def reindex_note(title: str) -> str:
    """重新索引指定笔记到 RAG（手动触发）。按标题定位，适用于外部编辑 .md 文件后重建索引。"""
    return _call("/api/reindex_note", title=title)


@mcp.tool()
def delete_note(title: str) -> str:
    """删除笔记及其所有 RAG 索引数据。按标题定位。"""
    return _call("/api/delete_note", title=title)


@mcp.tool()
def search_notes(query: str, top_k: int = 5) -> str:
    """在笔记内容中搜索相关笔记（向量语义检索）。"""
    return _call("/api/search_notes", query=query, top_k=top_k)


# ── 任务状态工具 ──────────────────────────────────────────

@mcp.tool()
def task_status(task_id: str | None = None) -> str:
    """查询异步任务状态。不传 task_id 返回所有任务列表。"""
    return _call("/api/task_status", task_id=task_id)


if __name__ == "__main__":
    mcp.run(transport="stdio")
