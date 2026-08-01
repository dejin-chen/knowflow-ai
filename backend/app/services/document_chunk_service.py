from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document_chunk import DocumentChunk
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_faq_repository import DocumentFaqRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.document_summary_repository import DocumentSummaryRepository
from app.services.document_parser_service import DocumentParserService
from app.services.text_splitter_service import TextSplitterService
from app.services.vector_store_service import ChromaVectorStoreService


class DocumentChunkService:
    """协调文档读取、文本清洗、切分和 Chunk 持久化。"""

    def __init__(
        self,
        db: Session,
        vector_store: ChromaVectorStoreService | None = None,
    ) -> None:
        self.db = db
        self.document_repository = DocumentRepository(db)
        self.chunk_repository = DocumentChunkRepository(db)
        self.summary_repository = DocumentSummaryRepository(db)
        self.faq_repository = DocumentFaqRepository(db)
        self.vector_store = vector_store or ChromaVectorStoreService()
        self.parser = DocumentParserService()
        self.splitter = TextSplitterService(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )

    def process_document(self, document_id: int) -> list[DocumentChunk]:
        document = self.document_repository.get_by_id(document_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在",
            )

        raw_text = self.parser.parse(document.storage_path, document.file_type)
        chunks = self.splitter.split_text(raw_text)
        if not chunks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文档中没有可切分的有效文本",
            )

        # Chunk 是向量、摘要和 FAQ 的上游数据。重新切分时必须先让旧派生数据失效。
        self.vector_store.delete_by_document(document.id)
        try:
            records = self.chunk_repository.replace_by_document(
                document_id=document.id,
                knowledge_base_id=document.knowledge_base_id,
                chunks=chunks,
                commit=False,
            )
            self.summary_repository.delete_by_document(document.id, commit=False)
            self.faq_repository.delete_by_document(document.id, commit=False)
            self.document_repository.update_status(document, "chunked", commit=False)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return records

    def list_chunks(self, document_id: int) -> list[DocumentChunk]:
        if self.document_repository.get_by_id(document_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在",
            )
        return self.chunk_repository.list_by_document(document_id)
