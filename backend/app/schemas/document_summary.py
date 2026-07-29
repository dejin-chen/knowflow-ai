from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DocumentSummaryRead(BaseModel):
    id: int
    document_id: int
    content: str
    citations: list[dict[str, Any]]
    model_name: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
