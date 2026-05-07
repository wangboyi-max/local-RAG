#!/usr/bin/env python3
"""快速测试：通过 IngestionPipeline 索引 PDF，stdout 实时打印进度。"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PDF = "/home/wangboyi/workspace/tmp/幼儿英语家庭陪读指南.pdf"


def main():
    from app.services.ocr import OCRService
    from app.services.vector_store import VectorStoreService
    from app.services.graph_store import GraphStoreService
    from app.services.chunking import get_chinese_text_splitter
    from app.services.entity_extractor import create_extractor
    from app.config import settings
    from app.pipelines.ingestion import IngestionPipeline

    print(f"当前实体提取模式: {settings.graph_entity_extractor}")
    print(f"开始处理 PDF: {PDF}\n", flush=True)

    t0 = time.time()

    ocr = OCRService()
    vector_store = VectorStoreService()
    graph_store = GraphStoreService(entity_extractor=create_extractor())
    pipeline = IngestionPipeline(ocr=ocr, vector_store=vector_store, graph_store=graph_store)

    result = pipeline.ingest(PDF)

    elapsed = round(time.time() - t0, 1)
    stats = graph_store.get_stats()
    print(f"\n{'=' * 50}")
    print(f"总耗时: {elapsed}s")
    print(f"页数: {result['pages']}")
    print(f"文本块: {result['chunks']}")
    print(f"图谱: {stats['chunk_nodes']} 文本块节点, {stats['entity_nodes']} 实体节点, {stats['relationships']} 关系边")
    print(f"{'=' * 50}")

    graph_store.close()


if __name__ == "__main__":
    main()
