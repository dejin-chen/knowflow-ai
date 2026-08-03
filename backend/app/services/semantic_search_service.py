from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.services.embedding_service import EmbeddingService
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.lightweight_rerank_service import LightweightRerankService
from app.services.vector_store_service import ChromaVectorStoreService, VectorSearchMatch


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: int
    document_id: int
    knowledge_base_id: int
    filename: str
    chunk_index: int
    content: str
    distance: float
    rerank_score: float | None = None


class SemanticSearchService:
    """执行“问题向量化 -> Chroma 召回 -> SQLite 来源回查”的语义检索。"""

    def __init__(
        self,
        db: Session,
        embedding_service: EmbeddingService | None = None,
        vector_store: ChromaVectorStoreService | None = None,
        rerank_service: LightweightRerankService | None = None,
    ) -> None:
        self.knowledge_base_service = KnowledgeBaseService(db)
        self.chunk_repository = DocumentChunkRepository(db)
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_store = vector_store or ChromaVectorStoreService()
        self.rerank_service = rerank_service or LightweightRerankService()

    def search(
        self,
        knowledge_base_id: int,
        query: str,
        top_k: int,
    ) -> list[RetrievedChunk]:
        self.knowledge_base_service.get_required_knowledge_base(knowledge_base_id)
        query_embedding = self.embedding_service.embed_texts([query])[0]
        candidate_top_k = top_k * settings.retrieval_candidate_multiplier
        matches = self.vector_store.search(
            query_embedding=query_embedding,
            knowledge_base_id=knowledge_base_id,
            top_k=candidate_top_k,
        )
        results = self._rehydrate_matches(matches, knowledge_base_id)
        candidates = self._deduplicate(results)
        if settings.retrieval_rerank_enabled:
            candidates = self.rerank_service.rerank(query, candidates)
        return candidates[:top_k]

    @staticmethod
    def _deduplicate(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        """去除同一文档中的重复正文，同时保留 Chroma 的距离排序。"""
        unique_chunks: list[RetrievedChunk] = []
        seen_content: set[tuple[int, str]] = set()
        for chunk in chunks:
            normalized_content = " ".join(chunk.content.split()).casefold()
            deduplication_key = (chunk.document_id, normalized_content)
            if deduplication_key in seen_content:
                continue
            seen_content.add(deduplication_key)
            unique_chunks.append(chunk)
        return unique_chunks

    def _rehydrate_matches(
        self,
        matches: list[VectorSearchMatch],
        knowledge_base_id: int,
    ) -> list[RetrievedChunk]:
        rows = self.chunk_repository.list_with_document_by_ids(
            [match.chunk_id for match in matches]
        )
        rows_by_chunk_id = {chunk.id: (chunk, document) for chunk, document in rows}

        # 保持 Chroma 的相似度排序，并以 SQLite 的数据作为最终返回内容和来源。
        results: list[RetrievedChunk] = []
        for match in matches:
            row = rows_by_chunk_id.get(match.chunk_id)
            if row is None:
                continue
            chunk, document = row
            if chunk.knowledge_base_id != knowledge_base_id:
                continue
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    document_id=document.id,
                    knowledge_base_id=chunk.knowledge_base_id,
                    filename=document.filename,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    distance=match.distance,
                )
            )
        return results
