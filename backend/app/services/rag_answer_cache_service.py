from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import logging
from typing import Any

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.rag_answer_cache_repository import RagAnswerCacheRepository
from app.services.llm_rerank_service import LlmRerankService
from app.services.rag_prompt_service import RagPromptService


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CachedRagAnswer:
    answer: str
    citations: list[dict[str, Any]]
    retrieved_chunks: list[dict[str, Any]]
    retrieved_chunk_count: int
    best_distance: float | None
    insufficient_evidence: bool


class RagAnswerCacheService:
    """管理精确问题缓存；缓存故障不能阻断正常 RAG 问答。"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repository = RagAnswerCacheRepository(db)

    def get(
        self,
        knowledge_base_id: int,
        question: str,
        top_k: int,
    ) -> CachedRagAnswer | None:
        if not settings.rag_answer_cache_enabled:
            return None

        now = self._now()
        cache_key, _ = self._build_key(knowledge_base_id, question, top_k)
        try:
            cache = self.repository.get_valid(cache_key, now)
            if cache is None:
                return None
            answer = CachedRagAnswer(
                answer=cache.answer,
                citations=list(cache.citations),
                retrieved_chunks=list(cache.retrieved_chunks),
                retrieved_chunk_count=cache.retrieved_chunk_count,
                best_distance=cache.best_distance,
                insufficient_evidence=cache.insufficient_evidence,
            )
            self.repository.record_hit(cache, now)
            return answer
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("读取 RAG 回答缓存失败，将回退到正常问答流程")
            return None

    def store(
        self,
        *,
        knowledge_base_id: int,
        question: str,
        top_k: int,
        answer: str,
        citations: list[dict[str, Any]],
        retrieved_chunks: list[dict[str, Any]],
        retrieved_chunk_count: int,
        best_distance: float | None,
        insufficient_evidence: bool,
        source_total_tokens: int,
    ) -> None:
        if not settings.rag_answer_cache_enabled:
            return

        cache_key, normalized_question = self._build_key(
            knowledge_base_id,
            question,
            top_k,
        )
        now = self._now()
        expires_at = now + timedelta(
            seconds=settings.rag_answer_cache_ttl_seconds
        )
        try:
            self.repository.upsert(
                knowledge_base_id=knowledge_base_id,
                cache_key=cache_key,
                normalized_question=normalized_question,
                top_k=top_k,
                answer=answer,
                citations=citations,
                retrieved_chunks=retrieved_chunks,
                retrieved_chunk_count=retrieved_chunk_count,
                best_distance=best_distance,
                insufficient_evidence=insufficient_evidence,
                source_total_tokens=source_total_tokens,
                expires_at=expires_at,
            )
            # 当前键刷新后先清过期数据，再按 LRU 批量限制单库和全局容量。
            self.repository.delete_expired(now, commit=False)
            self.repository.enforce_capacity(
                knowledge_base_id,
                max_entries=settings.rag_answer_cache_max_entries,
                max_entries_per_kb=settings.rag_answer_cache_max_entries_per_kb,
            )
        except SQLAlchemyError:
            self.db.rollback()
            logger.exception("写入 RAG 回答缓存失败，本次回答仍正常返回")

    def invalidate_knowledge_base(self, knowledge_base_id: int) -> int:
        """知识内容变化前主动失效缓存，宁可少命中，也不能返回旧答案。"""
        return self.repository.delete_by_knowledge_base(knowledge_base_id)

    def get_stats(self, knowledge_base_id: int) -> dict[str, int | bool]:
        stats = self.repository.get_stats(knowledge_base_id, self._now())
        return {
            "enabled": settings.rag_answer_cache_enabled,
            "ttl_seconds": settings.rag_answer_cache_ttl_seconds,
            "max_entries": settings.rag_answer_cache_max_entries,
            "max_entries_per_kb": min(
                settings.rag_answer_cache_max_entries,
                settings.rag_answer_cache_max_entries_per_kb,
            ),
            **stats,
        }

    @classmethod
    def _build_key(
        cls,
        knowledge_base_id: int,
        question: str,
        top_k: int,
    ) -> tuple[str, str]:
        normalized_question = " ".join(question.split()).casefold()
        prompt_signature = "\n".join(
            (
                RagPromptService.qa_system_message,
                RagPromptService.qa_user_message_template,
            )
        )
        prompt_hash = sha256(prompt_signature.encode("utf-8")).hexdigest()
        key_payload = {
            "version": settings.rag_answer_cache_version,
            "knowledge_base_id": knowledge_base_id,
            "question": normalized_question,
            "top_k": top_k,
            "chat_model": settings.chat_model,
            "embedding_model": settings.embedding_model,
            "distance_threshold": settings.retrieval_distance_threshold,
            "candidate_multiplier": settings.retrieval_candidate_multiplier,
            "hybrid_enabled": settings.retrieval_hybrid_enabled,
            "bm25_top_k": settings.retrieval_bm25_top_k,
            "bm25_min_score": settings.retrieval_bm25_min_score,
            "bm25_evidence_threshold": (
                settings.retrieval_bm25_evidence_threshold
            ),
            "rrf_k": settings.retrieval_rrf_k,
            "rrf_vector_weight": settings.retrieval_rrf_vector_weight,
            "rrf_bm25_weight": settings.retrieval_rrf_bm25_weight,
            "rerank_enabled": settings.retrieval_rerank_enabled,
            "rerank_strategy": settings.retrieval_rerank_strategy,
            "rerank_model": settings.retrieval_rerank_model or settings.chat_model,
            "rerank_max_candidates": settings.retrieval_rerank_max_candidates,
            "rerank_max_chunk_characters": (
                settings.retrieval_rerank_max_chunk_characters
            ),
            "rerank_prompt_version": LlmRerankService.prompt_version,
            "rerank_lexical_weight": settings.retrieval_rerank_lexical_weight,
            "prompt_hash": prompt_hash,
        }
        serialized_payload = json.dumps(
            key_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return sha256(serialized_payload.encode("utf-8")).hexdigest(), normalized_question

    @staticmethod
    def _now() -> datetime:
        # SQLite 不保存时区信息，因此统一使用 UTC 的 naive datetime 进行 TTL 比较。
        return datetime.now(UTC).replace(tzinfo=None)
