import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from app.services.chunking import get_paragraph_aware_text_splitter
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
        self.chunker = get_paragraph_aware_text_splitter()

    def ingest(self, file_path: str, progress_callback=None) -> dict:
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
            return self._ingest_pdf(file_path, source, action, progress_callback)
        else:
            return self._ingest_image(file_path, source, action)

    def _report(self, progress_callback, message):
        if progress_callback:
            progress_callback(message)

    def _ingest_pdf(self, pdf_path: str, source: str, action: str, progress_callback=None) -> dict:
        import fitz

        doc = fitz.open(pdf_path)
        total_pages = len(doc)
        total_chunks = 0
        total_graph_tasks = 0

        # 第一遍：统计需要 OCR 的页数
        for page_num in range(total_pages):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=settings.ocr_dpi)
            from PIL import Image
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = self.ocr.extract_text_from_image(image)
            pix = None

            if not text.strip():
                continue

            chunks = self.chunker.split_text(text)
            if not chunks:
                continue

            ids = [f"{source}-{uuid.uuid4().hex[:8]}-{i}" for i in range(len(chunks))]
            metadatas = [
                {
                    "source": source,
                    "page": page_num + 1,
                    "chunk_index": i,
                    "chunk_id": ids[i],
                    "ingested_at": datetime.now(timezone.utc).isoformat(),
                }
                for i in range(len(chunks))
            ]
            self.vector_store.add_documents(chunks, metadatas, ids)
            total_chunks += len(chunks)

            self._report(progress_callback, f"OCR + 向量化: {page_num + 1}/{total_pages} 页，累计 {total_chunks} 个文本块")

            # 图谱实体提取（提交到线程池，与后续 OCR 并行）
            if self.graph_store and chunks:
                self.graph_store.add_entities(list(chunks), list(metadatas))
                total_graph_tasks += 1
                self._report(progress_callback, f"图谱实体: {total_graph_tasks}/{total_pages} 页")

        doc.close()
        self._report(progress_callback, f"知识图谱构建完成，共 {total_graph_tasks} 页实体")
        self._report(progress_callback, f"完成: {total_pages} 页，{total_chunks} 个文本块")

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

        ids = [f"{source}-{uuid.uuid4().hex[:8]}-{i}" for i in range(len(texts))]
        now = datetime.now(timezone.utc).isoformat()
        metadatas = [
            {"source": source, "page": 1, "chunk_index": i, "chunk_id": ids[i], "ingested_at": now}
            for i in range(len(texts))
        ]
        self.vector_store.add_documents(texts, metadatas, ids)

        # 写入图谱
        if self.graph_store:
            self.graph_store.add_entities(texts, metadatas)

        return {"source": source, "pages": 1, "chunks": len(texts), "action": action}
