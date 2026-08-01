from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.document_summary import DocumentSummaryRead
from app.schemas.document_faq import DocumentFaqRead


class DocumentRead(BaseModel):
    id: int
    knowledge_base_id: int
    filename: str
    file_type: str
    file_size: int
    status: str
    created_at: datetime
    summary: DocumentSummaryRead | None = None
    faqs: list[DocumentFaqRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)
