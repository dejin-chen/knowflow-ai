from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models
from app.core.config import settings
from app.db.base import Base
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.bm25_retrieval_service import (
    Bm25RetrievalService,
    Bm25SearchMatch,
)
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.retrieval_tokenizer import RetrievalTokenizer
from app.services.rrf_fusion_service import RrfFusionService
from app.services.semantic_search_service import SemanticSearchService
from app.services.vector_store_service import VectorSearchMatch


class FakeEmbeddingService:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _text in texts]


class FakeVectorStore:
    def __init__(self, matches: list[VectorSearchMatch]) -> None:
        self.matches = matches

    def search(
        self,
        query_embedding: list[float],
        knowledge_base_id: int,
        top_k: int,
    ) -> list[VectorSearchMatch]:
        return self.matches[:top_k]


def build_database():
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def add_document_with_chunks(db, knowledge_base_id: int, contents: list[str]):
    document = Document(
        knowledge_base_id=knowledge_base_id,
        filename="运维手册.md",
        file_type="md",
        file_size=100,
        storage_path="/tmp/ops.md",
        status="indexed",
    )
    db.add(document)
    db.flush()
    chunks = [
        DocumentChunk(
            document_id=document.id,
            knowledge_base_id=knowledge_base_id,
            chunk_index=index,
            content=content,
            char_count=len(content),
            start_offset=0,
            end_offset=len(content),
        )
        for index, content in enumerate(contents)
    ]
    db.add_all(chunks)
    db.commit()
    for chunk in chunks:
        db.refresh(chunk)
    return chunks


def test_retrieval_tokenizer_handles_chinese_and_exact_codes() -> None:
    tokens = RetrievalTokenizer.tokenize("设备遗失后处理 VPN-403，金额 20,000 元")

    assert "设备" in tokens
    assert "遗失" in tokens
    assert "vpn" in tokens
    assert "403" in tokens
    assert "20000" in tokens


def test_bm25_promotes_exact_error_code(monkeypatch) -> None:
    monkeypatch.setattr(settings, "retrieval_bm25_min_score", 0.0)
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="BM25 测试库")
        )
        chunks = add_document_with_chunks(
            db,
            knowledge_base.id,
            [
                "普通网络连接问题请重启设备。",
                "出现 VPN-403 错误码时，应重新申请访问权限。",
                "员工病假需要提交医疗证明。",
            ],
        )

        matches = Bm25RetrievalService(db).search(
            knowledge_base.id,
            "VPN-403 怎么处理？",
            top_k=3,
        )

        assert matches[0].chunk_id == chunks[1].id
        assert matches[0].score > 0
        assert matches[0].rank == 1
    finally:
        db.close()


def test_rrf_rewards_candidates_found_by_both_retrievers(monkeypatch) -> None:
    monkeypatch.setattr(settings, "retrieval_rrf_k", 60)
    monkeypatch.setattr(settings, "retrieval_rrf_vector_weight", 1.0)
    monkeypatch.setattr(settings, "retrieval_rrf_bm25_weight", 1.0)

    results = RrfFusionService().fuse(
        vector_chunk_ids=[1, 2],
        bm25_matches=[
            Bm25SearchMatch(chunk_id=2, score=3.0, rank=1),
            Bm25SearchMatch(chunk_id=3, score=2.0, rank=2),
        ],
        limit=3,
    )

    assert [result.chunk_id for result in results] == [2, 1, 3]
    assert results[0].vector_rank == 2
    assert results[0].bm25_rank == 1
    assert results[0].score > results[1].score


def test_hybrid_retrieval_keeps_bm25_only_candidate(monkeypatch) -> None:
    monkeypatch.setattr(settings, "retrieval_hybrid_enabled", True)
    monkeypatch.setattr(settings, "retrieval_bm25_min_score", 0.0)
    monkeypatch.setattr(settings, "retrieval_bm25_top_k", 3)
    monkeypatch.setattr(settings, "retrieval_rerank_max_candidates", 3)
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="混合召回测试库")
        )
        chunks = add_document_with_chunks(
            db,
            knowledge_base.id,
            [
                "普通网络连接问题请联系 IT 服务台。",
                "员工病假需要提交医疗证明。",
                "VPN-403 表示访问权限已经过期。",
            ],
        )
        vector_match = VectorSearchMatch(
            chroma_id=f"chunk-{chunks[0].id}",
            chunk_id=chunks[0].id,
            document_id=chunks[0].document_id,
            knowledge_base_id=knowledge_base.id,
            chunk_index=chunks[0].chunk_index,
            distance=0.1,
        )
        service = SemanticSearchService(
            db,
            embedding_service=FakeEmbeddingService(),
            vector_store=FakeVectorStore([vector_match]),
        )

        candidates = service.retrieve_candidates(
            knowledge_base.id,
            "VPN-403 是什么意思？",
            top_k=3,
        )
        bm25_only_chunk = next(
            chunk for chunk in candidates if chunk.chunk_id == chunks[2].id
        )

        assert bm25_only_chunk.vector_rank is None
        assert bm25_only_chunk.bm25_rank == 1
        assert bm25_only_chunk.distance is None
        assert bm25_only_chunk.fusion_rank is not None
    finally:
        db.close()
