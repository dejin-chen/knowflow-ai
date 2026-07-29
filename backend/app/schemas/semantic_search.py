from pydantic import BaseModel, Field, field_validator


class SemanticSearchRequest(BaseModel):
    """语义检索请求。"""

    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=10)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("问题不能为空")
        return normalized_value


class RetrievedChunkRead(BaseModel):
    """语义检索命中的 Chunk 与来源信息。"""

    chunk_id: int
    document_id: int
    knowledge_base_id: int
    filename: str
    chunk_index: int
    content: str
    distance: float
