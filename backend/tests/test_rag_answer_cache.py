"""RAG answer cache lifecycle tests."""

from types import SimpleNamespace
from datetime import timedelta

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

import app.models
from app.core.config import settings
from app.db.base import Base
from app.models.message import Message
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.rag_answer_cache import RagAnswerCache
from app.models.retrieval_log import RetrievalLog
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.chat_completion_service import ChatCompletionResult
from app.services.document_chunk_service import DocumentChunkService
from app.services.document_vector_index_service import DocumentVectorIndexService
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.rag_answer_cache_service import RagAnswerCacheService
from app.services.rag_chat_service import RagChatService
from app.services.semantic_search_service import RetrievedChunk


class CountingSearchService:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks
        self.call_count = 0

    def search(self, knowledge_base_id: int, query: str, top_k: int):
        self.call_count += 1
        return self.chunks[:top_k]


class CountingChatService:
    def __init__(self) -> None:
        self.call_count = 0

    def generate_completion(self, prompt) -> ChatCompletionResult:
        self.call_count += 1
        return ChatCompletionResult(
            answer="病假需要医院证明。[1]",
            model_name="cache-test-model",
            prompt_tokens=12,
            completion_tokens=8,
            total_tokens=20,
        )


def build_database():
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def test_repeated_question_skips_embedding_search_and_chat_model(monkeypatch) -> None:
    monkeypatch.setattr(settings, "rag_answer_cache_enabled", True)
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="回答缓存测试库")
        )
        chunk = RetrievedChunk(
            chunk_id=101,
            document_id=12,
            knowledge_base_id=knowledge_base.id,
            filename="员工手册.md",
            chunk_index=2,
            content="员工申请病假时需要提供医院证明。",
            distance=0.12,
        )
        search_service = CountingSearchService([chunk])
        chat_service = CountingChatService()
        service = RagChatService(
            db,
            semantic_search_service=search_service,
            chat_completion_service=chat_service,
        )

        first_result = service.ask(
            knowledge_base.id,
            "病假需要什么材料？",
            conversation_id=None,
            top_k=3,
        )
        second_result = service.ask(
            knowledge_base.id,
            "  病假需要什么材料？  ",
            conversation_id=None,
            top_k=3,
        )

        cache = db.scalar(select(RagAnswerCache))
        stats = RagAnswerCacheService(db).get_stats(knowledge_base.id)
        assert first_result.cache_hit is False
        assert second_result.cache_hit is True
        assert second_result.answer == first_result.answer
        assert second_result.citations == first_result.citations
        assert search_service.call_count == 1
        assert chat_service.call_count == 1
        assert cache.hit_count == 1
        assert stats["hit_count"] == 1
        assert stats["estimated_chat_tokens_saved"] == 20
        assert len(list(db.scalars(select(Message)).all())) == 4
        assert len(list(db.scalars(select(RetrievalLog)).all())) == 2
    finally:
        db.close()


def test_cache_key_separates_different_top_k(monkeypatch) -> None:
    monkeypatch.setattr(settings, "rag_answer_cache_enabled", True)
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="缓存键测试库")
        )
        chunk = RetrievedChunk(
            chunk_id=1,
            document_id=1,
            knowledge_base_id=knowledge_base.id,
            filename="制度.md",
            chunk_index=0,
            content="制度正文",
            distance=0.1,
        )
        search_service = CountingSearchService([chunk])
        chat_service = CountingChatService()
        service = RagChatService(
            db,
            semantic_search_service=search_service,
            chat_completion_service=chat_service,
        )

        service.ask(knowledge_base.id, "制度是什么？", None, top_k=2)
        result = service.ask(knowledge_base.id, "制度是什么？", None, top_k=3)

        assert result.cache_hit is False
        assert search_service.call_count == 2
        assert chat_service.call_count == 2
        assert len(list(db.scalars(select(RagAnswerCache)).all())) == 2
    finally:
        db.close()


def test_expired_cache_runs_rag_again_and_refreshes_entry(monkeypatch) -> None:
    monkeypatch.setattr(settings, "rag_answer_cache_enabled", True)
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="缓存过期测试库")
        )
        chunk = RetrievedChunk(
            chunk_id=1,
            document_id=1,
            knowledge_base_id=knowledge_base.id,
            filename="制度.md",
            chunk_index=0,
            content="制度正文",
            distance=0.1,
        )
        search_service = CountingSearchService([chunk])
        chat_service = CountingChatService()
        service = RagChatService(
            db,
            semantic_search_service=search_service,
            chat_completion_service=chat_service,
        )
        service.ask(knowledge_base.id, "制度是什么？", None, top_k=3)
        cache = db.scalar(select(RagAnswerCache))
        cache.expires_at = RagAnswerCacheService._now() - timedelta(seconds=1)
        db.commit()

        result = service.ask(knowledge_base.id, "制度是什么？", None, top_k=3)

        assert result.cache_hit is False
        assert search_service.call_count == 2
        assert chat_service.call_count == 2
        assert len(list(db.scalars(select(RagAnswerCache)).all())) == 1
    finally:
        db.close()


class FakeVectorStore:
    def __init__(self) -> None:
        self.deleted_document_ids: list[int] = []

    def delete_by_document(self, document_id: int) -> None:
        self.deleted_document_ids.append(document_id)

    def upsert_chunks(self, chunks, embeddings) -> list[str]:
        return [f"chunk-{chunk.id}" for chunk in chunks]

    def delete_by_ids(self, chroma_ids: list[str]) -> None:
        pass


def seed_cache(
    cache_service: RagAnswerCacheService,
    knowledge_base_id: int,
    question: str = "旧问题",
) -> None:
    cache_service.store(
        knowledge_base_id=knowledge_base_id,
        question=question,
        top_k=3,
        answer="旧答案",
        citations=[],
        retrieved_chunks=[],
        retrieved_chunk_count=0,
        best_distance=None,
        insufficient_evidence=True,
        source_total_tokens=0,
    )


def test_per_knowledge_base_capacity_evicts_least_recently_used(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "rag_answer_cache_max_entries", 10)
    monkeypatch.setattr(settings, "rag_answer_cache_max_entries_per_kb", 2)
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="单库 LRU 测试库")
        )
        cache_service = RagAnswerCacheService(db)
        seed_cache(cache_service, knowledge_base.id, "问题一")
        seed_cache(cache_service, knowledge_base.id, "问题二")

        # 问题一刚被命中，问题三写入后应淘汰更久未使用的问题二。
        assert cache_service.get(knowledge_base.id, "问题一", 3) is not None
        seed_cache(cache_service, knowledge_base.id, "问题三")

        assert cache_service.get(knowledge_base.id, "问题一", 3) is not None
        assert cache_service.get(knowledge_base.id, "问题二", 3) is None
        assert cache_service.get(knowledge_base.id, "问题三", 3) is not None
        stats = cache_service.get_stats(knowledge_base.id)
        assert stats["entry_count"] == 2
        assert stats["max_entries_per_kb"] == 2
        assert stats["max_entries"] == 10
    finally:
        db.close()


def test_global_capacity_limits_entries_across_knowledge_bases(monkeypatch) -> None:
    monkeypatch.setattr(settings, "rag_answer_cache_max_entries", 3)
    monkeypatch.setattr(settings, "rag_answer_cache_max_entries_per_kb", 3)
    db = build_database()
    try:
        first_knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="全局容量测试库一")
        )
        second_knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="全局容量测试库二")
        )
        cache_service = RagAnswerCacheService(db)
        seed_cache(cache_service, first_knowledge_base.id, "最早的问题")
        seed_cache(cache_service, first_knowledge_base.id, "保留问题一")
        seed_cache(cache_service, second_knowledge_base.id, "保留问题二")
        seed_cache(cache_service, second_knowledge_base.id, "最新的问题")

        assert cache_service.get(
            first_knowledge_base.id,
            "最早的问题",
            3,
        ) is None
        assert cache_service.get(
            first_knowledge_base.id,
            "保留问题一",
            3,
        ) is not None
        assert cache_service.get(
            second_knowledge_base.id,
            "保留问题二",
            3,
        ) is not None
        assert cache_service.get(
            second_knowledge_base.id,
            "最新的问题",
            3,
        ) is not None
        assert db.scalar(select(func.count(RagAnswerCache.id))) == 3
    finally:
        db.close()


def test_reprocessing_document_invalidates_knowledge_base_cache(tmp_path) -> None:
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="重切分缓存失效测试库")
        )
        source_file = tmp_path / "policy.md"
        source_file.write_text("新的制度正文。" * 50, encoding="utf-8")
        document = Document(
            knowledge_base_id=knowledge_base.id,
            filename="policy.md",
            file_type="md",
            file_size=source_file.stat().st_size,
            storage_path=str(source_file),
            status="indexed",
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        seed_cache(RagAnswerCacheService(db), knowledge_base.id)

        DocumentChunkService(db, vector_store=FakeVectorStore()).process_document(
            document.id
        )

        assert db.scalar(select(RagAnswerCache)) is None
    finally:
        db.close()


def test_indexing_document_invalidates_knowledge_base_cache() -> None:
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="建索引缓存失效测试库")
        )
        document = Document(
            knowledge_base_id=knowledge_base.id,
            filename="policy.md",
            file_type="md",
            file_size=10,
            storage_path="/tmp/policy.md",
            status="chunked",
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        chunk = DocumentChunk(
            document_id=document.id,
            knowledge_base_id=knowledge_base.id,
            chunk_index=0,
            content="制度正文",
            char_count=4,
            start_offset=0,
            end_offset=4,
        )
        db.add(chunk)
        db.commit()
        seed_cache(RagAnswerCacheService(db), knowledge_base.id)

        DocumentVectorIndexService(
            db,
            embedding_service=SimpleNamespace(embed_texts=lambda _texts: [[0.1, 0.2]]),
            vector_store=FakeVectorStore(),
        ).index_document(document.id)

        assert db.scalar(select(RagAnswerCache)) is None
    finally:
        db.close()
