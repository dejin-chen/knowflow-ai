from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document_summary import DocumentSummary


class DocumentSummaryRepository:
    """文档摘要的读写与覆盖更新。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_document_id(self, document_id: int) -> DocumentSummary | None:
        statement = select(DocumentSummary).where(DocumentSummary.document_id == document_id)
        return self.db.scalar(statement)

    def get_by_document_ids(
        self,
        document_ids: list[int],
    ) -> dict[int, DocumentSummary]:
        if not document_ids:
            return {}
        statement = select(DocumentSummary).where(
            DocumentSummary.document_id.in_(document_ids)
        )
        summaries = self.db.scalars(statement).all()
        return {summary.document_id: summary for summary in summaries}

    def upsert(
        self,
        document_id: int,
        content: str,
        citations: list[dict],
        model_name: str | None,
        prompt_tokens: int | None,
        completion_tokens: int | None,
        total_tokens: int | None,
    ) -> DocumentSummary:
        summary = self.get_by_document_id(document_id)
        if summary is None:
            summary = DocumentSummary(document_id=document_id, content=content)
            self.db.add(summary)

        summary.content = content
        summary.citations = citations
        summary.model_name = model_name
        summary.prompt_tokens = prompt_tokens
        summary.completion_tokens = completion_tokens
        summary.total_tokens = total_tokens
        self.db.commit()
        self.db.refresh(summary)
        return summary

    def delete_by_document(self, document_id: int, *, commit: bool = True) -> None:
        self.db.execute(
            delete(DocumentSummary).where(DocumentSummary.document_id == document_id)
        )
        if commit:
            self.db.commit()
        else:
            self.db.flush()
