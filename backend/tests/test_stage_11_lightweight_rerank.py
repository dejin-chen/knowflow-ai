from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models
from app.core.config import settings
from app.db.base import Base
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.lightweight_rerank_service import LightweightRerankService
from app.services.semantic_search_service import RetrievedChunk, SemanticSearchService
from app.services.vector_store_service import VectorSearchMatch


def make_chunk(
    chunk_id: int,
    content: str,
    distance: float,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=1,
        knowledge_base_id=1,
        filename="员工手册.md",
        chunk_index=chunk_id,
        content=content,
        distance=distance,
    )


def test_reranker_promotes_candidate_with_strong_lexical_evidence(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "retrieval_rerank_lexical_weight", 0.5)
    chunks = [
        make_chunk(1, "员工需要遵守日常考勤制度。", 0.20),
        make_chunk(
            2,
            "公司设备遗失或被盗时，必须立即通知行政和信息安全部门。",
            0.50,
        ),
    ]

    results = LightweightRerankService().rerank(
        "公司设备遗失或被盗以后必须通知哪些部门？",
        chunks,
    )

    assert [chunk.chunk_id for chunk in results] == [2, 1]
    assert results[0].rerank_score > results[1].rerank_score


def test_reranker_preserves_vector_order_without_lexical_signal(monkeypatch) -> None:
    monkeypatch.setattr(settings, "retrieval_rerank_lexical_weight", 0.5)
    chunks = [
        make_chunk(1, "alpha beta", 0.10),
        make_chunk(2, "gamma delta", 0.30),
    ]

    results = LightweightRerankService().rerank("完全不同的问题", chunks)

    assert [chunk.chunk_id for chunk in results] == [1, 2]


class FakeEmbeddingService:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]


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


class TrackingReranker:
    def __init__(self) -> None:
        self.call_count = 0

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        self.call_count += 1
        return list(reversed(chunks))


def test_semantic_search_respects_rerank_switch(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = testing_session()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="Rerank 开关测试库")
        )
        document = Document(
            knowledge_base_id=knowledge_base.id,
            filename="制度.md",
            file_type="md",
            file_size=20,
            storage_path="/tmp/policy.md",
            status="indexed",
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        chunks = [
            DocumentChunk(
                document_id=document.id,
                knowledge_base_id=knowledge_base.id,
                chunk_index=index,
                content=content,
                char_count=len(content),
                start_offset=0,
                end_offset=len(content),
            )
            for index, content in enumerate(("片段一", "片段二"))
        ]
        db.add_all(chunks)
        db.commit()
        for chunk in chunks:
            db.refresh(chunk)
        matches = [
            VectorSearchMatch(
                chroma_id=f"chunk-{chunk.id}",
                chunk_id=chunk.id,
                document_id=document.id,
                knowledge_base_id=knowledge_base.id,
                chunk_index=chunk.chunk_index,
                distance=0.1 + index * 0.1,
            )
            for index, chunk in enumerate(chunks)
        ]
        reranker = TrackingReranker()
        service = SemanticSearchService(
            db,
            embedding_service=FakeEmbeddingService(),
            vector_store=FakeVectorStore(matches),
            rerank_service=reranker,
        )

        monkeypatch.setattr(settings, "retrieval_rerank_enabled", False)
        vector_results = service.search(knowledge_base.id, "问题", top_k=2)
        monkeypatch.setattr(settings, "retrieval_rerank_enabled", True)
        reranked_results = service.search(knowledge_base.id, "问题", top_k=2)

        assert [chunk.chunk_id for chunk in vector_results] == [
            chunks[0].id,
            chunks[1].id,
        ]
        assert [chunk.chunk_id for chunk in reranked_results] == [
            chunks[1].id,
            chunks[0].id,
        ]
        assert reranker.call_count == 1
    finally:
        db.close()
