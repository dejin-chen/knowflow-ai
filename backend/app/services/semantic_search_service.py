from dataclasses import dataclass, replace

from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.services.embedding_service import EmbeddingService
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.llm_rerank_service import LlmRerankService, RerankExecutionResult
from app.services.lightweight_rerank_service import LightweightRerankService
from app.services.chat_completion_service import ChatCompletionResult
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
    vector_rank: int | None = None
    rerank_rank: int | None = None
    rerank_method: str | None = None


@dataclass(frozen=True)
class SemanticSearchResult:
    chunks: list[RetrievedChunk]
    rerank_model_usage: ChatCompletionResult | None
    rerank_method: str
    rerank_fallback_used: bool
    rerank_fallback_reason: str | None
    rerank_latency_ms: float


class SemanticSearchService:
    """执行“问题向量化 -> Chroma 召回 -> SQLite 来源回查”的语义检索。"""

    def __init__(
        self,
        db: Session,
        embedding_service: EmbeddingService | None = None,
        vector_store: ChromaVectorStoreService | None = None,
        rerank_service=None,
    ) -> None:
        self.knowledge_base_service = KnowledgeBaseService(db)
        self.chunk_repository = DocumentChunkRepository(db)
        self.embedding_service = embedding_service or EmbeddingService()
        self.vector_store = vector_store or ChromaVectorStoreService()
        self.rerank_service = rerank_service or LlmRerankService()
        self.lexical_rerank_service = LightweightRerankService()

    def search(
        self,
        knowledge_base_id: int,
        query: str,
        top_k: int,
    ) -> list[RetrievedChunk]:
        return self.search_with_metadata(knowledge_base_id, query, top_k).chunks

    def search_with_metadata(
        self,
        knowledge_base_id: int,
        query: str,
        top_k: int,
    ) -> SemanticSearchResult:
        candidates = self.retrieve_candidates(knowledge_base_id, query, top_k)
        execution = self._rerank(query, candidates)
        return SemanticSearchResult(
            chunks=execution.chunks[:top_k],
            rerank_model_usage=execution.model_usage,
            rerank_method=execution.method,
            rerank_fallback_used=execution.fallback_used,
            rerank_fallback_reason=execution.fallback_reason,
            rerank_latency_ms=execution.latency_ms,
        )

    def retrieve_candidates(
        self,
        knowledge_base_id: int,
        query: str,
        top_k: int,
    ) -> list[RetrievedChunk]:
        self.knowledge_base_service.get_required_knowledge_base(knowledge_base_id)
        query_embedding = self.embedding_service.embed_texts([query])[0]
        return self.retrieve_candidates_by_embedding(
            knowledge_base_id,
            query_embedding,
            top_k,
            validate_knowledge_base=False,
        )

    def retrieve_candidates_by_embedding(
        self,
        knowledge_base_id: int,
        query_embedding: list[float],
        top_k: int,
        *,
        validate_knowledge_base: bool = True,
    ) -> list[RetrievedChunk]:
        """复用预先生成的问题向量，主要用于批量离线评测。"""
        if validate_knowledge_base:
            self.knowledge_base_service.get_required_knowledge_base(
                knowledge_base_id
            )
        candidate_top_k = max(
            top_k,
            min(
                top_k * settings.retrieval_candidate_multiplier,
                settings.retrieval_rerank_max_candidates,
            ),
        )
        matches = self.vector_store.search(
            query_embedding=query_embedding,
            knowledge_base_id=knowledge_base_id,
            top_k=candidate_top_k,
        )
        results = self._rehydrate_matches(matches, knowledge_base_id)
        candidates = self._deduplicate(results)
        return [
            replace(chunk, vector_rank=rank)
            for rank, chunk in enumerate(candidates, start=1)
        ]

    def _rerank(
        self,
        query: str,
        candidates: list[RetrievedChunk],
    ) -> RerankExecutionResult:
        if not settings.retrieval_rerank_enabled:
            return RerankExecutionResult(
                chunks=candidates,
                model_usage=None,
                method="vector",
                fallback_used=False,
                fallback_reason=None,
                latency_ms=0.0,
            )

        service = (
            self.lexical_rerank_service
            if settings.retrieval_rerank_strategy == "lexical"
            else self.rerank_service
        )
        if hasattr(service, "rerank_with_metadata"):
            return service.rerank_with_metadata(query, candidates)

        reranked_chunks = service.rerank(query, candidates)
        return RerankExecutionResult(
            chunks=reranked_chunks,
            model_usage=None,
            method=settings.retrieval_rerank_strategy,
            fallback_used=False,
            fallback_reason=None,
            latency_ms=0.0,
        )

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
