"""对比 jieba vs LLM 实体提取速度。"""
import os
import subprocess
import sys
import time
import json
import threading

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PDF_PATH = "/home/wangboyi/workspace/tmp/幼儿英语家庭陪读指南.pdf"


def _tail_stderr(proc, stop_event):
    """后台线程实时读取 stderr 并输出到控制台。"""
    while not stop_event.is_set():
        line = proc.stderr.readline()
        if line:
            print(f"  {line}", end="")
        else:
            break


def run_ingest(extractor: str) -> dict:
    """以指定提取模式索引 PDF，返回耗时和图谱统计。"""
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.main"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=os.getcwd(),
        env={**os.environ, "GRAPH_ENTITY_EXTRACTOR": extractor},
    )

    stop_event = threading.Event()
    stderr_thread = threading.Thread(target=_tail_stderr, args=(proc, stop_event), daemon=True)
    stderr_thread.start()

    def send(req):
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()
        while True:
            line = proc.stdout.readline()
            if not line:
                return None
            line = line.strip()
            if line:
                try:
                    r = json.loads(line)
                    if "id" in r or "method" in r:
                        return r
                except json.JSONDecodeError:
                    pass

    send({
        "jsonrpc": "2.0", "id": 0,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "bench"}}
    })
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
    proc.stdin.flush()

    # 先删除可能存在的旧文档
    send({
        "jsonrpc": "2.0", "id": 1,
        "method": "tools/call",
        "params": {"name": "delete_docs", "arguments": {"source": "幼儿英语家庭陪读指南.pdf"}}
    })

    # 索引
    t0 = time.time()
    resp = send({
        "jsonrpc": "2.0", "id": 2,
        "method": "tools/call",
        "params": {"name": "ingest_file", "arguments": {"file_path": PDF_PATH}}
    })
    elapsed = round(time.time() - t0, 2)

    ingest_text = resp["result"]["content"][0]["text"] if resp else "error"

    # 图谱统计
    stats_resp = send({
        "jsonrpc": "2.0", "id": 3,
        "method": "tools/call",
        "params": {"name": "graph_stats", "arguments": {}}
    })
    stats_text = stats_resp["result"]["content"][0]["text"] if stats_resp else "error"

    stop_event.set()
    proc.kill()
    proc.wait()
    return {
        "elapsed": elapsed,
        "ingest": ingest_text,
        "stats": stats_text,
    }


if __name__ == "__main__":
    print("=" * 60)
    print("实体提取速度对比测试")
    print(f"测试文件: {PDF_PATH}")
    print("=" * 60)

    # jieba 模式
    print("\n--- jieba 模式 ---")
    r1 = run_ingest("jieba")
    print(f"\n耗时: {r1['elapsed']}s")
    print(r1["ingest"])
    print(r1["stats"])

    # llm 模式
    print("\n--- LLM 模式 ---")
    r2 = run_ingest("llm")
    print(f"\n耗时: {r2['elapsed']}s")
    print(r2["ingest"])
    print(r2["stats"])

    print("\n" + "=" * 60)
    print(f"速度对比: jieba={r1['elapsed']}s vs llm={r2['elapsed']}s")
    print(f"LLM 是 jieba 的 {r2['elapsed'] / max(r1['elapsed'], 0.01):.1f}x 慢")
    print("=" * 60)
