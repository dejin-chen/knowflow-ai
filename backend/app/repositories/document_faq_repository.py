from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document_faq import DocumentFaq


class DocumentFaqRepository:
    """FAQ 的读取与整批替换，避免重新生成时遗留旧问题。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def list_by_document_id(self, document_id: int) -> list[DocumentFaq]:
        statement = (
            select(DocumentFaq)
            .where(DocumentFaq.document_id == document_id)
            .order_by(DocumentFaq.sort_order)
        )
        return list(self.db.scalars(statement).all())

    def list_by_document_ids(
        self,
        document_ids: list[int],
    ) -> dict[int, list[DocumentFaq]]:
        if not document_ids:
            return {}
        statement = (
            select(DocumentFaq)
            .where(DocumentFaq.document_id.in_(document_ids))
            .order_by(DocumentFaq.document_id, DocumentFaq.sort_order)
        )
        faqs_by_document_id: dict[int, list[DocumentFaq]] = {}
        for faq in self.db.scalars(statement):
            faqs_by_document_id.setdefault(faq.document_id, []).append(faq)
        return faqs_by_document_id

    def replace_by_document(
        self,
        document_id: int,
        items: list[dict],
    ) -> list[DocumentFaq]:
        self.db.execute(delete(DocumentFaq).where(DocumentFaq.document_id == document_id))
        faqs = [
            DocumentFaq(
                document_id=document_id,
                question=item["question"],
                answer=item["answer"],
                citations=item["citations"],
                sort_order=index,
            )
            for index, item in enumerate(items, start=1)
        ]
        self.db.add_all(faqs)
        self.db.commit()
        for faq in faqs:
            self.db.refresh(faq)
        return faqs
