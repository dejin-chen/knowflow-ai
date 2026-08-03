from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.models
from app.core.config import settings
from app.db.base import Base
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.vector_index import VectorIndex
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.document_vector_index_service import DocumentVectorIndexService
from app.services.embedding_service import EmbeddingService
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.semantic_search_service import SemanticSearchService
from app.services.vector_store_service import ChromaVectorStoreService, VectorSearchMatch


class FakeEmbeddingService:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[float(index + 1), 0.5] for index, _ in enumerate(texts)]


class FakeVectorStore:
    def __init__(self) -> None:
        self.received_chunks: list[DocumentChunk] = []
        self.received_embeddings: list[list[float]] = []
        self.deleted_ids: list[str] = []

    def upsert_chunks(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> list[str]:
        self.received_chunks = chunks
        self.received_embeddings = embeddings
        return [f"chunk-{chunk.id}" for chunk in chunks]

    def delete_by_ids(self, chroma_ids: list[str]) -> None:
        self.deleted_ids.extend(chroma_ids)


class FakeSearchVectorStore:
    def __init__(self, matches: list[VectorSearchMatch]) -> None:
        self.matches = matches
        self.requested_knowledge_base_id: int | None = None
        self.requested_top_k: int | None = None

    def search(
        self,
        query_embedding: list[float],
        knowledge_base_id: int,
        top_k: int,
    ) -> list[VectorSearchMatch]:
        self.requested_knowledge_base_id = knowledge_base_id
        self.requested_top_k = top_k
        assert query_embedding == [0.9, 0.1]
        return self.matches[:top_k]


def test_embedding_service_batches_texts() -> None:
    batches = EmbeddingService._iter_batches(["a", "b", "c", "d", "e"], batch_size=2)

    assert batches == [["a", "b"], ["c", "d"], ["e"]]


def test_index_document_creates_vector_mappings() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = testing_session()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="向量索引测试库")
        )
        document = Document(
            knowledge_base_id=knowledge_base.id,
            filename="制度.md",
            file_type="md",
            file_size=100,
            storage_path="/tmp/policy.md",
            status="chunked",
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        db.add_all(
            [
                DocumentChunk(
                    document_id=document.id,
                    knowledge_base_id=knowledge_base.id,
                    chunk_index=0,
                    content="病假需要提供证明材料。",
                    char_count=11,
                    start_offset=0,
                    end_offset=11,
                ),
                DocumentChunk(
                    document_id=document.id,
                    knowledge_base_id=knowledge_base.id,
                    chunk_index=1,
                    content="年假需要提前提交申请。",
                    char_count=11,
                    start_offset=12,
                    end_offset=23,
                ),
            ]
        )
        db.commit()

        fake_vector_store = FakeVectorStore()
        service = DocumentVectorIndexService(
            db,
            embedding_service=FakeEmbeddingService(),
            vector_store=fake_vector_store,
        )
        result = service.index_document(document.id)
        mappings = list(db.scalars(select(VectorIndex)).all())

        assert result.document_id == document.id
        assert result.indexed_chunk_count == 2
        assert result.status == "indexed"
        assert len(fake_vector_store.received_embeddings) == 2
        assert len(mappings) == 2
        assert document.status == "indexed"
    finally:
        db.close()


def test_chroma_store_persists_vector_record(tmp_path) -> None:
    original_persist_dir = settings.chroma_persist_dir
    original_collection_name = settings.chroma_collection_name
    settings.chroma_persist_dir = str(tmp_path / "chroma")
    settings.chroma_collection_name = f"test_chunks_{uuid4().hex}"

    try:
        chunk = SimpleNamespace(
            id=101,
            document_id=12,
            knowledge_base_id=3,
            chunk_index=0,
            content="员工请病假需要提供证明材料。",
        )
        store = ChromaVectorStoreService()
        chroma_ids = store.upsert_chunks([chunk], [[0.1, 0.2, 0.3]])
        record = store.collection.get(
            ids=chroma_ids,
            include=["documents", "metadatas"],
        )

        assert chroma_ids == ["chunk-101"]
        assert record["documents"] == [chunk.content]
        assert record["metadatas"][0]["knowledge_base_id"] == 3
        assert record["metadatas"][0]["chunk_id"] == 101
        matches = store.search(
            query_embedding=[0.1, 0.2, 0.3],
            knowledge_base_id=3,
            top_k=1,
        )
        assert matches[0].chunk_id == 101
        assert matches[0].document_id == 12

        store.delete_by_document(12)
        assert store.collection.get(ids=chroma_ids)["ids"] == []

        store.upsert_chunks([chunk], [[0.1, 0.2, 0.3]])
        store.delete_by_knowledge_base(3)
        assert store.collection.get(ids=chroma_ids)["ids"] == []
    finally:
        settings.chroma_persist_dir = original_persist_dir
        settings.chroma_collection_name = original_collection_name


def test_semantic_search_rehydrates_chunks_and_sources(monkeypatch) -> None:
    monkeypatch.setattr(settings, "retrieval_rerank_enabled", False)
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = testing_session()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="语义检索测试库")
        )
        document = Document(
            knowledge_base_id=knowledge_base.id,
            filename="员工手册.md",
            file_type="md",
            file_size=100,
            storage_path="/tmp/handbook.md",
            status="indexed",
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        chunks = [
            DocumentChunk(
                document_id=document.id,
                knowledge_base_id=knowledge_base.id,
                chunk_index=0,
                content="病假需要提供证明材料。",
                char_count=11,
                start_offset=0,
                end_offset=11,
            ),
            DocumentChunk(
                document_id=document.id,
                knowledge_base_id=knowledge_base.id,
                chunk_index=1,
                content="年假需要提前提交申请。",
                char_count=11,
                start_offset=12,
                end_offset=23,
            ),
        ]
        db.add_all(chunks)
        db.commit()
        for chunk in chunks:
            db.refresh(chunk)

        fake_vector_store = FakeSearchVectorStore(
            [
                VectorSearchMatch(
                    chroma_id=f"chunk-{chunks[1].id}",
                    chunk_id=chunks[1].id,
                    document_id=document.id,
                    knowledge_base_id=knowledge_base.id,
                    chunk_index=1,
                    distance=0.08,
                ),
                VectorSearchMatch(
                    chroma_id=f"chunk-{chunks[0].id}",
                    chunk_id=chunks[0].id,
                    document_id=document.id,
                    knowledge_base_id=knowledge_base.id,
                    chunk_index=0,
                    distance=0.19,
                ),
            ]
        )
        service = SemanticSearchService(
            db,
            embedding_service=SimpleNamespace(embed_texts=lambda _: [[0.9, 0.1]]),
            vector_store=fake_vector_store,
        )
        results = service.search(knowledge_base.id, "病假需要什么材料", top_k=2)

        assert fake_vector_store.requested_knowledge_base_id == knowledge_base.id
        assert [result.chunk_id for result in results] == [chunks[1].id, chunks[0].id]
        assert results[0].filename == "员工手册.md"
        assert results[0].distance == 0.08
    finally:
        db.close()


def test_semantic_search_overfetches_and_removes_duplicate_content(monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(settings, "retrieval_candidate_multiplier", 3)

    db = testing_session()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="检索去重测试库")
        )
        document = Document(
            knowledge_base_id=knowledge_base.id,
            filename="员工制度.md",
            file_type="md",
            file_size=100,
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
                start_offset=index * 20,
                end_offset=index * 20 + len(content),
            )
            for index, content in enumerate(
                ["病假需要提供证明。", "病假需要提供证明。", "年假需要提前申请。"]
            )
        ]
        db.add_all(chunks)
        db.commit()
        for chunk in chunks:
            db.refresh(chunk)

        fake_vector_store = FakeSearchVectorStore(
            [
                VectorSearchMatch(
                    chroma_id=f"chunk-{chunk.id}",
                    chunk_id=chunk.id,
                    document_id=document.id,
                    knowledge_base_id=knowledge_base.id,
                    chunk_index=chunk.chunk_index,
                    distance=0.1 + index * 0.01,
                )
                for index, chunk in enumerate(chunks)
            ]
        )
        service = SemanticSearchService(
            db,
            embedding_service=SimpleNamespace(embed_texts=lambda _: [[0.9, 0.1]]),
            vector_store=fake_vector_store,
        )

        results = service.search(knowledge_base.id, "请假制度", top_k=2)

        assert fake_vector_store.requested_top_k == 6
        assert [result.chunk_id for result in results] == [chunks[0].id, chunks[2].id]
    finally:
        db.close()


def test_index_document_compensates_chroma_when_database_write_fails() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    db = testing_session()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="索引补偿测试库")
        )
        document = Document(
            knowledge_base_id=knowledge_base.id,
            filename="制度.md",
            file_type="md",
            file_size=100,
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
            content="病假需要提供证明。",
            char_count=9,
            start_offset=0,
            end_offset=9,
        )
        db.add(chunk)
        db.commit()
        db.refresh(chunk)

        fake_vector_store = FakeVectorStore()
        service = DocumentVectorIndexService(
            db,
            embedding_service=FakeEmbeddingService(),
            vector_store=fake_vector_store,
        )

        def fail_database_write(*_args, **_kwargs):
            raise RuntimeError("模拟数据库写入失败")

        service.vector_index_repository.upsert_many = fail_database_write

        with pytest.raises(RuntimeError, match="模拟数据库写入失败"):
            service.index_document(document.id)

        assert fake_vector_store.deleted_ids == [f"chunk-{chunk.id}"]
        db.refresh(document)
        assert document.status == "chunked"
    finally:
        db.close()
