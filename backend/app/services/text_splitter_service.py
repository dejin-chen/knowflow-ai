import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    """切分器输出的中间对象，尚未写入数据库。"""

    index: int
    content: str
    start_offset: int
    end_offset: int


class TextSplitterService:
    """按字符数切分文本，并尽可能在自然边界处结束 Chunk。"""

    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size 必须大于 0")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须大于等于 0 且小于 chunk_size")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def clean_text(self, text: str) -> str:
        """统一换行并去除多余空白，保留 Markdown 标题和段落结构。"""
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        return normalized.strip()

    def split_text(self, text: str) -> list[TextChunk]:
        cleaned_text = self.clean_text(text)
        if not cleaned_text:
            return []

        chunks: list[TextChunk] = []
        start = 0
        text_length = len(cleaned_text)

        while start < text_length:
            maximum_end = min(start + self.chunk_size, text_length)
            end = self._find_natural_end(cleaned_text, start, maximum_end)
            raw_content = cleaned_text[start:end]
            content = raw_content.strip()

            if content:
                leading_spaces = len(raw_content) - len(raw_content.lstrip())
                chunk_start = start + leading_spaces
                chunks.append(
                    TextChunk(
                        index=len(chunks),
                        content=content,
                        start_offset=chunk_start,
                        end_offset=chunk_start + len(content),
                    )
                )

            if end >= text_length:
                break
            start = max(end - self.chunk_overlap, start + 1)

        return chunks

    def _find_natural_end(self, text: str, start: int, maximum_end: int) -> int:
        """优先在段落、换行或句末附近切分，避免把短段落切得过碎。"""
        if maximum_end == len(text):
            return maximum_end

        search_start = start + self.chunk_size // 2
        for separator in ("\n\n", "\n", "。", "！", "？", ". ", " "):
            position = text.rfind(separator, search_start, maximum_end)
            if position != -1:
                return position + len(separator)
        return maximum_end
