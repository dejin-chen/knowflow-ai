from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document


class DocumentRepository:
    """文档元信息数据访问层。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        knowledge_base_id: int,
        filename: str,
        file_type: str,
        file_size: int,
        storage_path: str,
        status: str = "uploaded",
    ) -> Document:
        document = Document(
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            file_type=file_type,
            file_size=file_size,
            storage_path=storage_path,
            status=status,
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)
        return document

    def list_by_knowledge_base(self, knowledge_base_id: int) -> list[Document]:
        statement = (
            select(Document)
            .where(Document.knowledge_base_id == knowledge_base_id)
            .order_by(Document.created_at.desc())
        )
        return list(self.db.scalars(statement).all())

    def get_by_id(self, document_id: int) -> Document | None:
        return self.db.get(Document, document_id)

    def update_status(
        self,
        document: Document,
        status: str,
        *,
        commit: bool = True,
    ) -> Document:
        document.status = status
        if commit:
            self.db.commit()
            self.db.refresh(document)
        else:
            self.db.flush()
        return document
