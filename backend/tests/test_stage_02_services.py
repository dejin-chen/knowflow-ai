import asyncio
from io import BytesIO
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import UploadFile

from app.core.config import settings
from app.db.base import Base
import app.models
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.document_service import DocumentService
from app.services.knowledge_base_service import KnowledgeBaseService


def test_create_knowledge_base_and_upload_document(tmp_path) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    TestingSessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    settings.upload_dir = str(tmp_path / "uploads")

    db = TestingSessionLocal()
    try:
        knowledge_base_service = KnowledgeBaseService(db)
        document_service = DocumentService(db)

        knowledge_base = knowledge_base_service.create_knowledge_base(
            KnowledgeBaseCreate(name="公司制度库", description="测试知识库")
        )

        upload_file = UploadFile(
            filename="员工手册.md",
            file=BytesIO("# 员工手册\n请按制度执行。".encode("utf-8")),
        )
        document = asyncio.run(
            document_service.upload_document(knowledge_base.id, upload_file)
        )

        documents = document_service.list_documents(knowledge_base.id)

        assert knowledge_base.name == "公司制度库"
        assert document.filename == "员工手册.md"
        assert document.file_type == "md"
        assert Path(document.storage_path).exists()
        assert len(documents) == 1
    finally:
        db.close()
