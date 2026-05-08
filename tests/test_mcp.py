"""测试 MCP Server stdio 通信。"""
import json
import subprocess
import sys
import os

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def send_request(proc, request):
    """发送 JSON-RPC 请求并读取响应。"""
    proc.stdin.write(json.dumps(request) + "\n")
    proc.stdin.flush()
    # 读取响应（可能有多行，最后一行是 JSON-RPC 响应）
    lines = []
    while True:
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if line:
            try:
                resp = json.loads(line)
                if "id" in resp or "method" in resp:
                    return resp
            except json.JSONDecodeError:
                pass


def main():
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.proxy"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )

    # 1. 初始化
    print("1. 发送 initialize 请求...")
    init_resp = send_request(proc, {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1.0.0"},
        },
    })
    print(f"   响应: {init_resp}")

    # 发送 initialized 通知
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    proc.stdin.flush()

    # 2. 工具列表
    print("\n2. 请求 tools/list...")
    tools_resp = send_request(proc, {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {},
    })
    tool_names = [t["name"] for t in tools_resp.get("result", {}).get("tools", [])]
    print(f"   工具列表: {tool_names}")
    # 验证没有笔记相关工具
    assert "create_note" not in tool_names, "不应包含 create_note"
    assert "get_note" not in tool_names, "不应包含 get_note"
    assert "list_notes" not in tool_names, "不应包含 list_notes"
    # 验证核心工具存在
    assert "ingest_file" in tool_names, "应包含 ingest_file"
    assert "search_docs" in tool_names, "应包含 search_docs"
    assert "task_status" in tool_names, "应包含 task_status"
    print("  ✓ 工具列表正确（无笔记相关工具）")

    print("\n=== MCP Server 测试完成 ===")
    proc.kill()


if __name__ == "__main__":
    main()
