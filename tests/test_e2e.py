"""端到端测试：索引文件 → 检索 → 验证结果。"""
import os
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.ocr import OCRService
from app.services.vector_store import VectorStoreService
from app.pipelines.ingestion import IngestionPipeline
from app.pipelines.retrieval import RetrievalPipeline


def test_end_to_end():
    print("=" * 50)
    print("步骤 1: 初始化服务")
    print("=" * 50)
    ocr = OCRService()
    print("  OCRService 初始化完成")

    vector_store = VectorStoreService()
    print(f"  VectorStore 初始化完成，当前文档数: {vector_store.count()}")

    ingestion = IngestionPipeline(ocr=ocr, vector_store=vector_store)
    retrieval = RetrievalPipeline(vector_store=vector_store)

    print("\n" + "=" * 50)
    print("步骤 2: 索引测试图片")
    print("=" * 50)
    result = ingestion.ingest("/tmp/test_ocr_image.png")
    print(f"  结果: {result}")
    assert result["chunks"] > 0, "图片索引应产生至少一个文本块"
    print("  ✓ 图片索引成功")

    print("\n" + "=" * 50)
    print("步骤 3: 索引测试 PDF")
    print("=" * 50)
    result = ingestion.ingest("/tmp/test_scanned.pdf")
    print(f"  结果: {result}")
    assert result["chunks"] > 0, "PDF 索引应产生至少一个文本块"
    print("  ✓ PDF 索引成功")

    print("\n" + "=" * 50)
    print("步骤 4: 列出已索引文档")
    print("=" * 50)
    sources = vector_store.get_unique_sources()
    print(f"  已索引文档: {sources}")
    assert len(sources) == 2, f"应有 2 个文档，实际 {len(sources)}"
    print("  ✓ 文档列表正确")

    print("\n" + "=" * 50)
    print("步骤 5: 语义检索 - 'RAG 的工作流程是什么？'")
    print("=" * 50)
    chunks = retrieval.search("RAG 的工作流程是什么？", top_k=3)
    print(f"  找到 {len(chunks)} 个相关文本块:")
    for i, c in enumerate(chunks, 1):
        print(f"\n  [{i}] {c['source']} (第{c['page']}页) [分数: {c['score']}]")
        print(f"  {c['text'][:100]}...")
    assert len(chunks) > 0, "检索应返回至少一个结果"
    print("\n  ✓ 检索成功")

    print("\n" + "=" * 50)
    print("步骤 6: 删除测试")
    print("=" * 50)
    count = vector_store.delete_by_source("test_ocr_image.png")
    print(f"  删除图片文档，移除 {count} 个文本块")
    sources_after = vector_store.get_unique_sources()
    print(f"  剩余文档: {sources_after}")
    assert len(sources_after) == 1, "删除后应只剩 1 个文档"
    print("  ✓ 删除成功")

    print("\n" + "=" * 50)
    print("所有测试通过！")
    print("=" * 50)


if __name__ == "__main__":
    test_end_to_end()
