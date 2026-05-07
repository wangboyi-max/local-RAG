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
        [sys.executable, "-m", "app.main"],
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
    print(f"   响应: {tools_resp}")

    # 3. 测试 ingest_file
    print("\n3. 调用 ingest_file 索引测试 PDF...")
    ingest_resp = send_request(proc, {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "ingest_file",
            "arguments": {"file_path": "/tmp/test_scanned.pdf"},
        },
    })
    print(f"   响应: {ingest_resp}")

    # 4. 测试 list_docs
    print("\n4. 调用 list_docs...")
    list_resp = send_request(proc, {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "tools/call",
        "params": {"name": "list_docs", "arguments": {}},
    })
    print(f"   响应: {list_resp}")

    # 5. 测试 search_docs
    print("\n5. 调用 search_docs...")
    search_resp = send_request(proc, {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "tools/call",
        "params": {
            "name": "search_docs",
            "arguments": {"query": "RAG 是什么", "top_k": 3},
        },
    })
    print(f"   响应: {search_resp}")

    # 6. 测试 graph_stats
    print("\n6. 调用 graph_stats...")
    stats_resp = send_request(proc, {
        "jsonrpc": "2.0",
        "id": 7,
        "method": "tools/call",
        "params": {"name": "graph_stats", "arguments": {}},
    })
    print(f"   响应: {stats_resp}")

    # 7. 测试 delete_docs
    print("\n7. 调用 delete_docs...")
    delete_resp = send_request(proc, {
        "jsonrpc": "2.0",
        "id": 6,
        "method": "tools/call",
        "params": {
            "name": "delete_docs",
            "arguments": {"source": "test_scanned.pdf"},
        },
    })
    print(f"   响应: {delete_resp}")

    print("\n=== MCP Server 测试完成 ===")
    proc.kill()


if __name__ == "__main__":
    main()
