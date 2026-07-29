from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentChunkRead(BaseModel):
    """查看切分结果时返回的 Chunk 数据。"""

    id: int
    document_id: int
    knowledge_base_id: int
    chunk_index: int
    content: str
    char_count: int
    start_offset: int
    end_offset: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentChunkProcessRead(BaseModel):
    """生成 Chunk 接口的处理结果。"""

    document_id: int
    status: str
    chunk_count: int
