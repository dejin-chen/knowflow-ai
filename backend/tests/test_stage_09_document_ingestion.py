import asyncio
from io import BytesIO

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.datastructures import UploadFile

import app.models
import app.services.document_parser_service as parser_module
from app.core.config import settings
from app.db.base import Base
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.document_parser_service import DocumentParserService
from app.services.document_service import DocumentService
from app.services.knowledge_base_service import KnowledgeBaseService


def test_streaming_upload_rejects_oversized_file_and_removes_partial_file(
    tmp_path,
    monkeypatch,
) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    monkeypatch.setattr(settings, "upload_read_chunk_size", 256 * 1024)

    db = testing_session()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="上传限制测试库")
        )
        upload_file = UploadFile(
            filename="large.md",
            file=BytesIO(b"a" * (1024 * 1024 + 1)),
        )

        with pytest.raises(HTTPException) as error:
            asyncio.run(
                DocumentService(db).upload_document(knowledge_base.id, upload_file)
            )

        assert error.value.status_code == 413
        assert list((tmp_path / "uploads").rglob("*.md")) == []
    finally:
        db.close()


def test_upload_accepts_pdf_and_sanitizes_windows_filename(tmp_path, monkeypatch) -> None:
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))

    db = testing_session()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="PDF 上传测试库")
        )
        document = asyncio.run(
            DocumentService(db).upload_document(
                knowledge_base.id,
                UploadFile(
                    filename=r"C:\fakepath\员工制度.pdf",
                    file=BytesIO(b"%PDF-test"),
                ),
            )
        )

        assert document.filename == "员工制度.pdf"
        assert document.file_type == "pdf"
        assert document.file_size == len(b"%PDF-test")
    finally:
        db.close()


def test_pdf_parser_preserves_page_markers(tmp_path, monkeypatch) -> None:
    class FakePage:
        def __init__(self, text: str | None) -> None:
            self.text = text

        def extract_text(self) -> str | None:
            return self.text

    class FakeReader:
        pages = [FakePage("第一页制度正文"), FakePage("第二页报销正文")]

    monkeypatch.setattr(parser_module, "PdfReader", lambda _path: FakeReader())
    pdf_path = tmp_path / "policy.pdf"
    pdf_path.write_bytes(b"%PDF-test")

    content = DocumentParserService().parse(str(pdf_path), "pdf")

    assert "## 第 1 页" in content
    assert "第一页制度正文" in content
    assert "## 第 2 页" in content


def test_pdf_parser_rejects_scanned_pdf_without_text(tmp_path, monkeypatch) -> None:
    class EmptyPage:
        def extract_text(self) -> None:
            return None

    class FakeReader:
        pages = [EmptyPage()]

    monkeypatch.setattr(parser_module, "PdfReader", lambda _path: FakeReader())
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-test")

    with pytest.raises(HTTPException, match="扫描件暂不支持 OCR") as error:
        DocumentParserService().parse(str(pdf_path), "pdf")

    assert error.value.status_code == 400
