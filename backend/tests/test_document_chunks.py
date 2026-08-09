"""Document parsing and chunk persistence tests."""

import asyncio
from io import BytesIO

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import UploadFile

import app.models
from app.core.config import settings
from app.db.base import Base
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.document_chunk_service import DocumentChunkService
from app.services.document_service import DocumentService
from app.services.knowledge_base_service import KnowledgeBaseService


class FakeVectorStore:
    def __init__(self) -> None:
        self.deleted_document_ids: list[int] = []

    def delete_by_document(self, document_id: int) -> None:
        self.deleted_document_ids.append(document_id)


def test_process_document_into_chunks(tmp_path) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    settings.upload_dir = str(tmp_path / "uploads")
    settings.chunk_size = 30
    settings.chunk_overlap = 8

    db = testing_session()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="员工手册库")
        )
        upload_file = UploadFile(
            filename="员工手册.md",
            file=BytesIO(
                "# 请假制度\n员工请假需要提前提交申请。\n\n病假需要提供证明材料。".encode("utf-8")
            ),
        )
        document = asyncio.run(
            DocumentService(db).upload_document(knowledge_base.id, upload_file)
        )

        vector_store = FakeVectorStore()
        chunk_service = DocumentChunkService(db, vector_store=vector_store)
        chunks = chunk_service.process_document(document.id)
        stored_chunks = chunk_service.list_chunks(document.id)

        assert len(chunks) >= 2
        assert len(stored_chunks) == len(chunks)
        assert stored_chunks[0].document_id == document.id
        assert stored_chunks[0].knowledge_base_id == knowledge_base.id
        assert document.status == "chunked"
        assert vector_store.deleted_document_ids == [document.id]
    finally:
        db.close()
