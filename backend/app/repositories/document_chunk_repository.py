from typing import TYPE_CHECKING

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.vector_index import VectorIndex

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
        *,
        commit: bool = True,
    ) -> list[DocumentChunk]:
        """替换某篇文档已有的 Chunk，保证重复处理不会产生重复记录。"""
        old_chunks = self.list_by_document(document_id)
        if old_chunks:
            # 显式删除映射，避免 SQLite 未启用外键时留下孤立 vector_indexes。
            self.db.execute(
                delete(VectorIndex)
                .where(VectorIndex.chunk_id.in_([chunk.id for chunk in old_chunks]))
                .execution_options(synchronize_session=False)
            )
            # 让 ORM 正确维护 identity map，避免 SQLite 复用主键时混淆新旧对象。
            for old_chunk in old_chunks:
                self.db.delete(old_chunk)
            self.db.flush()

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
        self.db.flush()
        if commit:
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

    def list_with_document_by_knowledge_base(
        self,
        knowledge_base_id: int,
    ) -> list[tuple[DocumentChunk, Document]]:
        """按稳定顺序读取知识库语料，供 BM25 构建轻量关键词索引。"""
        statement = (
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.knowledge_base_id == knowledge_base_id)
            .order_by(Document.id, DocumentChunk.chunk_index)
        )
        return list(self.db.execute(statement).all())
