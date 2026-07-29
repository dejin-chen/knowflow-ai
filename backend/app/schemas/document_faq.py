from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentFaqDraft(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    answer: str = Field(min_length=1, max_length=3000)
    reference_ids: list[int] = Field(min_length=1)

    @field_validator("question", "answer")
    @classmethod
    def strip_text(cls, value: str) -> str:
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("FAQ 文本不能为空。")
        return normalized_value


class DocumentFaqRead(BaseModel):
    id: int
    document_id: int
    question: str
    answer: str
    citations: list[dict[str, Any]]
    sort_order: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
