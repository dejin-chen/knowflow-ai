from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk

if TYPE_CHECKING:
    from app.services.text_splitter_service import TextChunk


class DocumentChunkRepository:
    """DocumentChunk 表的数据访问层。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def replace_by_document(
        self,
        document_id: int,
        knowledge_base_id: int,
        chunks: list["TextChunk"],
    ) -> list[DocumentChunk]:
        """替换某篇文档已有的 Chunk，保证重复处理不会产生重复记录。"""
        self.db.execute(
            delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
        )

        records = [
            DocumentChunk(
                document_id=document_id,
                knowledge_base_id=knowledge_base_id,
                chunk_index=chunk.index,
                content=chunk.content,
                char_count=len(chunk.content),
                start_offset=chunk.start_offset,
                end_offset=chunk.end_offset,
            )
            for chunk in chunks
        ]
        self.db.add_all(records)
        self.db.commit()
        for record in records:
            self.db.refresh(record)
        return records

    def list_by_document(self, document_id: int) -> list[DocumentChunk]:
        statement = (
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        )
        return list(self.db.scalars(statement).all())

    def list_with_document_by_ids(
        self,
        chunk_ids: list[int],
    ) -> list[tuple[DocumentChunk, Document]]:
        """批量回查 Chunk 与来源文档，避免检索后产生 N+1 次数据库查询。"""
        if not chunk_ids:
            return []

        statement = (
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.id.in_(chunk_ids))
        )
        return list(self.db.execute(statement).all())
