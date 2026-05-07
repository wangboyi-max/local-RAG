import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from app.services.chunking import get_chinese_text_splitter
from app.services.ocr import OCRService
from app.services.vector_store import VectorStoreService
from app.services.graph_store import GraphStoreService
from app.config import settings

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}


class IngestionPipeline:
    def __init__(
        self,
        ocr: OCRService,
        vector_store: VectorStoreService,
        graph_store: GraphStoreService | None = None,
    ):
        self.ocr = ocr
        self.vector_store = vector_store
        self.graph_store = graph_store
        self.chunker = get_chinese_text_splitter()

    def ingest(self, file_path: str) -> dict:
        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"不支持的文件格式: {ext}")

        source = os.path.basename(file_path)

        # 覆盖模式：如果已存在同名文档，先删除
        action = "indexed"
        existing = self.vector_store.get_unique_sources()
        if source in existing:
            self.vector_store.delete_by_source(source)
            if self.graph_store:
                self.graph_store.delete_by_source(source)
            action = "replaced"

        if ext == ".pdf":
            return self._ingest_pdf(file_path, source, action)
        else:
            return self._ingest_image(file_path, source, action)

    def _ingest_pdf(self, pdf_path: str, source: str, action: str) -> dict:
        import fitz

        print(f"[Ingestion] 开始处理 PDF: {source}", file=sys.stderr, flush=True)

        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        total_chunks = 0

        # 使用线程池：OCR 主线程 + 图谱实体提取后台线程并行
        graph_futures = []
        with ThreadPoolExecutor(max_workers=2) as executor:
            for page_num in range(total_pages):
                page = doc[page_num]
                # OCR（主线程）
                pix = page.get_pixmap(dpi=settings.ocr_dpi)
                from PIL import Image
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                text = self.ocr.extract_text_from_image(image)
                pix = None  # 释放内存

                if not text.strip():
                    continue

                # 切分 + 向量存储
                chunks = self.chunker.split_text(text)
                if not chunks:
                    continue

                metadatas = [
                    {
                        "source": source,
                        "page": page_num + 1,
                        "chunk_index": i,
                        "ingested_at": datetime.now(timezone.utc).isoformat(),
                    }
                    for i in range(len(chunks))
                ]
                ids = [f"{source}-{uuid.uuid4().hex[:8]}-{i}" for i in range(len(chunks))]
                self.vector_store.add_documents(chunks, metadatas, ids)
                total_chunks += len(chunks)
                print(f"[Ingestion] 第 {page_num + 1}/{total_pages} 页，切分 {len(chunks)} 个块，累计 {total_chunks} 个", file=sys.stderr, flush=True)

                # 图谱实体提取（提交到线程池，与后续 OCR 并行）
                if self.graph_store and chunks:
                    future = executor.submit(
                        self.graph_store.add_entities, list(chunks), list(metadatas)
                    )
                    graph_futures.append(future)

            print(f"[Ingestion] OCR 和向量索引完成，等待 {len(graph_futures)} 个图谱提取任务...", file=sys.stderr, flush=True)
            # 等待所有图谱提取完成
            for i, future in enumerate(as_completed(graph_futures)):
                try:
                    future.result()
                except Exception as e:
                    print(f"[Ingestion] 图谱提取任务 {i+1} 出错: {e}", file=sys.stderr, flush=True)
            print(f"[Ingestion] 知识图谱构建完成", file=sys.stderr, flush=True)

        doc.close()
        return {
            "source": source,
            "pages": total_pages,
            "chunks": total_chunks,
            "action": action,
        }

    def _ingest_image(self, image_path: str, source: str, action: str) -> dict:
        from PIL import Image

        image = Image.open(image_path).convert("RGB")
        text = self.ocr.extract_text_from_image(image)

        chunks = self.chunker.split_text(text)
        if not chunks:
            return {"source": source, "pages": 1, "chunks": 0, "action": action}

        texts = chunks
        now = datetime.now(timezone.utc).isoformat()
        metadatas = [
            {"source": source, "page": 1, "chunk_index": i, "ingested_at": now}
            for i in range(len(texts))
        ]
        ids = [f"{source}-{uuid.uuid4().hex[:8]}-{i}" for i in range(len(texts))]
        self.vector_store.add_documents(texts, metadatas, ids)

        # 写入图谱
        if self.graph_store:
            self.graph_store.add_entities(texts, metadatas)

        return {"source": source, "pages": 1, "chunks": len(texts), "action": action}
