from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.document_chunk import DocumentChunk
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.vector_index_repository import VectorIndexRepository
from app.services.embedding_service import EmbeddingService
from app.services.vector_store_service import ChromaVectorStoreService


@dataclass(frozen=True)
class DocumentIndexResult:
    document_id: int
    indexed_chunk_count: int
    status: str


class DocumentVectorIndexService:
    """协调“Chunk -> Embedding -> Chroma -> SQLite 映射”的建索引流程。"""

    def __init__(
        self,
        db: Session,
        embedding_service: EmbeddingService | None = None,
        vector_store: ChromaVectorStoreService | None = None,
    ) -> None:
        self.document_repository = DocumentRepository(db)
        self.chunk_repository = DocumentChunkRepository(db)
        self.vector_index_repository = VectorIndexRepository(db)
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_store = vector_store or ChromaVectorStoreService()

    def index_document(self, document_id: int) -> DocumentIndexResult:
        document = self.document_repository.get_by_id(document_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在",
            )

        chunks = self.chunk_repository.list_by_document(document_id)
        if not chunks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文档尚未完成文本切分，无法建立向量索引",
            )

        # 只有 content 参与向量化；各类 ID 作为 Chroma metadata 保存，用于过滤和溯源。
        embeddings = self.embedding_service.embed_texts([chunk.content for chunk in chunks])
        chroma_ids = self.vector_store.upsert_chunks(chunks, embeddings)
        self.vector_index_repository.upsert_many(list(zip(
            [chunk.id for chunk in chunks], chroma_ids, strict=True
        )))
        self.document_repository.update_status(document, "indexed")

        return DocumentIndexResult(
            document_id=document.id,
            indexed_chunk_count=len(chunks),
            status="indexed",
        )
