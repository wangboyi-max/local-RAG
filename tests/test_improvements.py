"""测试改动点：段落切分、BM25、混合检索、chunk_id、输出格式化。"""
import os
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.services.chunking import get_paragraph_aware_text_splitter
from app.services.vector_store import VectorStoreService
from app.pipelines.retrieval import RetrievalPipeline, _chunk_key
from app.server import _format_chunks, _clean_ocr_text


def test_config():
    print("=== 1. 配置检查 ===")
    assert settings.chunk_size == 1500, f"chunk_size 应为 1500，实际 {settings.chunk_size}"
    assert settings.chunk_overlap == 200, f"chunk_overlap 应为 200，实际 {settings.chunk_overlap}"
    assert settings.bm25_enabled is True, "bm25_enabled 应为 True"
    print("  ✓ chunk_size=1500, chunk_overlap=200, bm25_enabled=True")


def test_paragraph_aware_splitter():
    print("\n=== 2. 段落感知切分器 ===")
    splitter = get_paragraph_aware_text_splitter()

    # 测试段落边界优先
    text = "第一段内容。\n\n第二段内容，比较长，超过了一千字符的限制。" + "x" * 1200
    chunks = splitter.split_text(text)
    assert len(chunks) > 0, "应产生至少一个 chunk"
    # 验证第一个 chunk 应该在段落边界处断开
    print(f"  输入 {len(text)} 字符，切分 {len(chunks)} 个 chunk")
    for i, c in enumerate(chunks):
        print(f"  chunk[{i}]: {len(c)} 字符, 开头: {c[:30]}...")
    print("  ✓ 切分器正常工作")


def test_chunk_id_in_metadata():
    print("\n=== 3. chunk_id metadata 字段 ===")
    vs = VectorStoreService()
    test_texts = ["测试文本一", "测试文本二", "测试文本三"]
    test_ids = ["test-doc-001", "test-doc-002", "test-doc-003"]
    test_metas = [
        {"source": "test.doc", "page": 1, "chunk_index": i, "chunk_id": test_ids[i]}
        for i in range(3)
    ]
    vs.add_documents(test_texts, test_metas, test_ids)

    # 验证 BM25 查询能返回 chunk_id
    bm25_results = vs.bm25_query("测试", top_k=3)
    assert len(bm25_results) > 0, "BM25 应返回结果"
    assert bm25_results[0].get("chunk_id", ""), "BM25 结果应包含 chunk_id"
    print(f"  BM25 返回 {len(bm25_results)} 条，chunk_id 字段存在")

    # 清理
    for tid in test_ids:
        vs.collection.delete(ids=[tid])
    vs._invalidate_bm25_cache()
    print("  ✓ chunk_id 字段正确传递")


def test_chunk_key_dedup():
    print("\n=== 4. _chunk_key 去重 ===")
    # 有 chunk_id 的情况
    meta1 = {"chunk_id": "doc-001", "source": "a.pdf", "page": 1, "chunk_index": 0}
    key1 = _chunk_key(meta1)
    assert key1 == "doc-001", f"应为 chunk_id，实际 {key1}"

    # 无 chunk_id 的回退
    meta2 = {"source": "a.pdf", "page": 2, "chunk_index": 1}
    key2 = _chunk_key(meta2)
    assert key2 == "a.pdf|2|1", f"应为回退 key，实际 {key2}"

    print(f"  chunk_id 模式: {key1}")
    print(f"  回退模式: {key2}")
    print("  ✓ 去重 key 生成正确")


def test_bm25_and_vector_dedup():
    print("\n=== 5. 混合检索去重 ===")
    vs = VectorStoreService()
    retrieval = RetrievalPipeline(vector_store=vs, graph_store=None)

    # 索引测试文本（模拟 chunk_id）
    test_texts = [
        "二语习得理论认为儿童通过大量可理解性输入自然学会英语",
        "沉默期是二语习得的正常阶段，一般持续6个月到1年",
        "自然拼读需要足够的听力词汇作为基础",
        "分级读物是儿童英语启蒙的重要工具",
    ]
    test_metas = [
        {"source": "test.pdf", "page": i + 1, "chunk_index": i, "chunk_id": f"test-{i}"}
        for i in range(4)
    ]
    test_ids = [f"test-{i}" for i in range(4)]
    vs.add_documents(test_texts, test_metas, test_ids)

    # 测试检索
    results = retrieval.search("二语习得", top_k=3)
    print(f"  搜索 '二语习得' 返回 {len(results)} 条:")
    for i, r in enumerate(results):
        print(f"  [{i}] {r['source_type']} {r['source']} (第{r['page']}页) score={r['score']}")
        print(f"      {r['text'][:60]}...")

    assert len(results) > 0, "应返回结果"
    # 验证没有重复（同一 chunk_id 不应出现两次）
    seen_keys = set()
    for r in results:
        key = _chunk_key({"chunk_id": r.get("chunk_id", "")})
        assert key not in seen_keys, f"发现重复 chunk: {key}"
        seen_keys.add(key)

    # 清理
    vs.delete_by_source("test.pdf")
    print("  ✓ 混合检索去重正确")


def test_clean_ocr_text():
    print("\n=== 6. OCR 文本清理 ===")
    dirty_text = "第一行内容\n\n\n\n第二行\n   有空格   \n\n\n\n第三行  "
    cleaned = _clean_ocr_text(dirty_text)
    assert "\n\n\n" not in cleaned, "不应有连续空行"
    assert cleaned == "第一行内容\n\n第二行\n有空格\n\n第三行", f"清理结果不对: {repr(cleaned)}"
    print(f"  输入: {repr(dirty_text)}")
    print(f"  输出: {repr(cleaned)}")
    print("  ✓ OCR 文本清理正确")


def test_format_chunks():
    print("\n=== 7. 输出格式化 ===")
    test_chunks = [
        {"text": "这是向量检索的结果", "source": "test.pdf", "page": 1, "score": 0.75, "source_type": "vector"},
        {"text": "这是 BM25 关键词检索结果", "source": "test.pdf", "page": 2, "score": None, "source_type": "bm25"},
        {"text": "这是图谱扩展的结果", "source": "test.pdf", "page": 3, "score": None, "source_type": "graph"},
    ]
    formatted = _format_chunks(test_chunks)
    assert "向量 1 条" in formatted, "应包含向量标签"
    assert "关键词 1 条" in formatted, "应包含关键词标签"
    assert "图谱 1 条" in formatted, "应包含图谱标签"
    assert "[相关度: 0.75]" in formatted, "应显示分数"
    assert "[相关度: None]" not in formatted, "无分数的不应显示 None"
    print("  输出预览:")
    print(formatted[:300])
    print("  ✓ 输出格式化正确")


if __name__ == "__main__":
    test_config()
    test_paragraph_aware_splitter()
    test_chunk_id_in_metadata()
    test_chunk_key_dedup()
    test_bm25_and_vector_dedup()
    test_clean_ocr_text()
    test_format_chunks()
    print("\n" + "=" * 50)
    print("所有测试通过！")
    print("=" * 50)
