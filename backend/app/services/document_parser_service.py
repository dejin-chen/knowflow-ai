from pathlib import Path

from fastapi import HTTPException, status


class DocumentParserService:
    """读取原始 TXT / Markdown 文件并转换为统一文本。"""

    supported_file_types = {"txt", "md", "markdown"}

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
