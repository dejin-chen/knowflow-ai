from datetime import datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.rag_answer_cache import RagAnswerCache


class RagAnswerCacheRepository:
    """封装回答缓存的查询、回写、统计和失效操作。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_valid(self, cache_key: str, now: datetime) -> RagAnswerCache | None:
        statement = select(RagAnswerCache).where(
            RagAnswerCache.cache_key == cache_key,
            RagAnswerCache.expires_at > now,
        )
        return self.db.scalar(statement)

    def upsert(
        self,
        *,
        knowledge_base_id: int,
        cache_key: str,
        normalized_question: str,
        top_k: int,
        answer: str,
        citations: list[dict[str, Any]],
        retrieved_chunks: list[dict[str, Any]],
        retrieved_chunk_count: int,
        best_distance: float | None,
        insufficient_evidence: bool,
        source_total_tokens: int,
        expires_at: datetime,
    ) -> RagAnswerCache:
        cache = self.db.scalar(
            select(RagAnswerCache).where(RagAnswerCache.cache_key == cache_key)
        )
        if cache is None:
            cache = RagAnswerCache(
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
            self.db.add(cache)
        else:
            cache.answer = answer
            cache.citations = citations
            cache.retrieved_chunks = retrieved_chunks
            cache.retrieved_chunk_count = retrieved_chunk_count
            cache.best_distance = best_distance
            cache.insufficient_evidence = insufficient_evidence
            cache.source_total_tokens = source_total_tokens
            cache.expires_at = expires_at
            cache.hit_count = 0
            cache.last_hit_at = None

        try:
            self.db.commit()
            self.db.refresh(cache)
            return cache
        except IntegrityError:
            # 两个相同问题并发回写时，保留先提交的结果即可。
            self.db.rollback()
            winner = self.db.scalar(
                select(RagAnswerCache).where(RagAnswerCache.cache_key == cache_key)
            )
            if winner is None:
                raise
            return winner

    def record_hit(self, cache: RagAnswerCache, now: datetime) -> None:
        cache.hit_count += 1
        cache.last_hit_at = now
        self.db.commit()

    def delete_by_knowledge_base(
        self,
        knowledge_base_id: int,
        *,
        commit: bool = True,
    ) -> int:
        result = self.db.execute(
            delete(RagAnswerCache).where(
                RagAnswerCache.knowledge_base_id == knowledge_base_id
            )
        )
        if commit:
            self.db.commit()
        return result.rowcount or 0

    def delete_expired(self, now: datetime, *, commit: bool = True) -> int:
        result = self.db.execute(
            delete(RagAnswerCache).where(RagAnswerCache.expires_at <= now)
        )
        if commit:
            self.db.commit()
        return result.rowcount or 0

    def enforce_capacity(
        self,
        knowledge_base_id: int,
        *,
        max_entries: int,
        max_entries_per_kb: int,
        commit: bool = True,
    ) -> int:
        """先限制当前知识库，再限制全局；超限时批量淘汰最久未使用记录。"""
        effective_per_kb_limit = min(max_entries, max_entries_per_kb)
        evicted_count = self._evict_lru(
            max_entries=effective_per_kb_limit,
            knowledge_base_id=knowledge_base_id,
        )
        evicted_count += self._evict_lru(max_entries=max_entries)
        if commit:
            self.db.commit()
        return evicted_count

    def _evict_lru(
        self,
        *,
        max_entries: int,
        knowledge_base_id: int | None = None,
    ) -> int:
        conditions = []
        if knowledge_base_id is not None:
            conditions.append(RagAnswerCache.knowledge_base_id == knowledge_base_id)

        count_statement = select(func.count(RagAnswerCache.id)).where(*conditions)
        current_count = int(self.db.scalar(count_statement) or 0)
        overflow_count = current_count - max_entries
        if overflow_count <= 0:
            return 0

        # last_hit_at 表示真实命中时间；从未命中的记录使用最近写入时间。
        last_used_at = func.coalesce(
            RagAnswerCache.last_hit_at,
            RagAnswerCache.updated_at,
            RagAnswerCache.created_at,
        )
        oldest_ids = (
            select(RagAnswerCache.id)
            .where(*conditions)
            .order_by(last_used_at.asc(), RagAnswerCache.id.asc())
            .limit(overflow_count)
        )
        result = self.db.execute(
            delete(RagAnswerCache).where(RagAnswerCache.id.in_(oldest_ids))
        )
        return max(result.rowcount or 0, 0)

    def get_stats(self, knowledge_base_id: int, now: datetime) -> dict[str, int]:
        statement = select(
            func.count(RagAnswerCache.id),
            func.coalesce(func.sum(RagAnswerCache.hit_count), 0),
            func.coalesce(
                func.sum(
                    RagAnswerCache.hit_count * RagAnswerCache.source_total_tokens
                ),
                0,
            ),
        ).where(
            RagAnswerCache.knowledge_base_id == knowledge_base_id,
            RagAnswerCache.expires_at > now,
        )
        entry_count, hit_count, estimated_tokens_saved = self.db.execute(statement).one()
        return {
            "entry_count": int(entry_count),
            "hit_count": int(hit_count),
            "estimated_chat_tokens_saved": int(estimated_tokens_saved),
        }
