from pydantic import BaseModel


class DocumentIndexRead(BaseModel):
    """文档建立向量索引后的处理结果。"""

    document_id: int
    indexed_chunk_count: int
    status: str
