from pathlib import Path

from fastapi import HTTPException, status
from pypdf import PdfReader


class DocumentParserService:
    """读取 TXT、Markdown 或文本型 PDF，并转换为统一文本。"""

    supported_file_types = {"txt", "md", "markdown", "pdf"}

    def parse(self, storage_path: str, file_type: str) -> str:
        if file_type not in self.supported_file_types:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="当前文档类型暂不支持解析",
            )

        file_path = Path(storage_path)
        if not file_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="原始文档文件不存在",
            )

        if file_type == "pdf":
            return self._parse_pdf(file_path)

        file_bytes = file_path.read_bytes()
        # 优先使用 UTF-8；GB18030 作为中文 Windows 文本文档的兼容兜底。
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                return file_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="文档编码无法识别，请使用 UTF-8 或 GB18030 编码",
        )

    @staticmethod
    def _parse_pdf(file_path: Path) -> str:
        try:
            reader = PdfReader(file_path)
            pages: list[str] = []
            for page_number, page in enumerate(reader.pages, start=1):
                page_text = (page.extract_text() or "").strip()
                if page_text:
                    # 页码标记进入 Chunk 正文，使引用片段仍能展示原 PDF 页位置。
                    pages.append(f"## 第 {page_number} 页\n\n{page_text}")
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PDF 文件损坏、加密或无法解析",
            ) from error

        if not pages:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="PDF 未提取到文本，扫描件暂不支持 OCR",
            )
        return "\n\n".join(pages)
