import asyncio
import sqlite3
from io import BytesIO
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import UploadFile

import app.models
from app.core.config import settings
from app.db.base import Base
from app.db.session import _enable_sqlite_foreign_keys
from app.models.document_faq import DocumentFaq
from app.models.document_summary import DocumentSummary
from app.models.knowledge_base import KnowledgeBase
from app.models.vector_index import VectorIndex
from app.schemas.document import DocumentRead
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.document_chunk_service import DocumentChunkService
from app.services.document_service import DocumentService
from app.services.knowledge_base_service import KnowledgeBaseService


class FakeLifecycleVectorStore:
    def __init__(self) -> None:
        self.deleted_document_ids: list[int] = []
        self.deleted_knowledge_base_ids: list[int] = []

    def delete_by_document(self, document_id: int) -> None:
        self.deleted_document_ids.append(document_id)

    def delete_by_knowledge_base(self, knowledge_base_id: int) -> None:
        self.deleted_knowledge_base_ids.append(knowledge_base_id)


def test_sqlite_foreign_key_enforcement_is_enabled() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        _enable_sqlite_foreign_keys(connection, None)
        enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        assert enabled == 1
    finally:
        connection.close()


def test_reprocessing_document_invalidates_old_derived_data(tmp_path, monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "chunk_size", 30)
    monkeypatch.setattr(settings, "chunk_overlap", 5)

    db = testing_session()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="生命周期测试库")
        )
        upload_file = UploadFile(
            filename="员工制度.md",
            file=BytesIO("病假需要提供证明。\n年假需要提前申请。".encode("utf-8")),
        )
        document = asyncio.run(
            DocumentService(db).upload_document(knowledge_base.id, upload_file)
        )
        vector_store = FakeLifecycleVectorStore()
        chunk_service = DocumentChunkService(db, vector_store=vector_store)
        old_chunks = chunk_service.process_document(document.id)

        db.add_all(
            [
                VectorIndex(chunk_id=chunk.id, chroma_id=f"chunk-{chunk.id}")
                for chunk in old_chunks
            ]
        )
        db.add(
            DocumentSummary(
                document_id=document.id,
                content="旧摘要",
                citations=[],
            )
        )
        db.add(
            DocumentFaq(
                document_id=document.id,
                question="旧问题",
                answer="旧回答",
                citations=[],
                sort_order=1,
            )
        )
        document.status = "indexed"
        db.commit()

        Path(document.storage_path).write_text(
            "新的制度正文，不应继续使用旧摘要和旧向量。",
            encoding="utf-8",
        )
        new_chunks = chunk_service.process_document(document.id)
        db.expire_all()

        assert vector_store.deleted_document_ids == [document.id, document.id]
        assert [chunk.content for chunk in new_chunks] == [
            "新的制度正文，不应继续使用旧摘要和旧向量。"
        ]
        assert db.scalar(select(func.count()).select_from(VectorIndex)) == 0
        assert db.scalar(
            select(func.count()).select_from(DocumentSummary)
        ) == 0
        assert db.scalar(select(func.count()).select_from(DocumentFaq)) == 0
        assert document.status == "chunked"
    finally:
        db.close()


def test_delete_knowledge_base_cleans_vectors_files_and_hides_storage_path(
    tmp_path,
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

    db = testing_session()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="删除清理测试库")
        )
        document = asyncio.run(
            DocumentService(db).upload_document(
                knowledge_base.id,
                UploadFile(
                    filename="制度.md",
                    file=BytesIO("测试正文".encode("utf-8")),
                ),
            )
        )
        stored_path = Path(document.storage_path)
        response_payload = DocumentRead.model_validate(document).model_dump()
        vector_store = FakeLifecycleVectorStore()

        KnowledgeBaseService(db, vector_store=vector_store).delete_knowledge_base(
            knowledge_base.id
        )

        assert "storage_path" not in response_payload
        assert vector_store.deleted_knowledge_base_ids == [knowledge_base.id]
        assert db.get(KnowledgeBase, knowledge_base.id) is None
        assert not stored_path.exists()
    finally:
        db.close()
