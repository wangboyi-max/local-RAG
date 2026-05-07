from paddleocr import PaddleOCR
from PIL import Image
from app.config import settings


class OCRService:
    def __init__(self, languages: str | None = None):
        lang = (languages or settings.ocr_languages).split(",")[0]
        self.client = PaddleOCR(lang=lang)

    def extract_text_from_image(self, image: Image.Image) -> str:
        import numpy as np

        img_array = np.array(image)
        result = self.client.ocr(img_array)
        return self._parse_ocr_result(result)

    def extract_text_from_pdf(self, pdf_path: str) -> list[dict]:
        """将 PDF 每页渲染为指定 DPI 图像后通过 PaddleOCR 提取文字，返回 [{page, text}] 列表。"""
        import fitz

        doc = fitz.open(pdf_path)
        pages_text = []
        for page_num in range(len(doc)):
            page = doc[page_num]
            pix = page.get_pixmap(dpi=settings.ocr_dpi)
            image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            text = self.extract_text_from_image(image)
            if text.strip():
                pages_text.append({"page": page_num + 1, "text": text})
        doc.close()
        return pages_text

    @staticmethod
    def _parse_ocr_result(result) -> str:
        """将 PaddleOCR v3 的 OCRResult 解析为纯文本。"""
        if not result:
            return ""
        texts = []
        for page_result in result:
            # v3 返回 OCRResult 对象，支持 dict-like 访问
            if hasattr(page_result, "get"):
                rec_texts = page_result.get("rec_texts", [])
                if rec_texts:
                    texts.extend(rec_texts)
                else:
                    # 回退：尝试旧版嵌套列表格式
                    for line in page_result:
                        if isinstance(line, dict) and "text" in line:
                            texts.append(line["text"])
                        elif isinstance(line, (list, tuple)) and len(line) >= 2:
                            texts.append(line[1][0])
            elif isinstance(page_result, list):
                for line in page_result:
                    if isinstance(line, dict) and "text" in line:
                        texts.append(line["text"])
                    elif isinstance(line, (list, tuple)) and len(line) >= 2:
                        texts.append(line[1][0])
        return "\n".join(texts)
