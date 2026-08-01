from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.repositories.document_repository import DocumentRepository
from app.repositories.document_summary_repository import DocumentSummaryRepository
from app.repositories.document_faq_repository import DocumentFaqRepository
from app.services.knowledge_base_service import KnowledgeBaseService


class DocumentService:
    """文档业务层。

    第二阶段只保存原始文件和元信息，不做内容解析。
    这样第三阶段可以专注于“从 storage_path 读取文件并切 Chunk”。
    """

    allowed_extensions = {".txt", ".md", ".markdown"}

    def __init__(self, db: Session) -> None:
        self.repository = DocumentRepository(db)
        self.summary_repository = DocumentSummaryRepository(db)
        self.faq_repository = DocumentFaqRepository(db)
        self.knowledge_base_service = KnowledgeBaseService(db)

    async def upload_document(
        self,
        knowledge_base_id: int,
        file: UploadFile,
    ) -> Document:
        self.knowledge_base_service.get_required_knowledge_base(knowledge_base_id)

        original_filename = Path(file.filename or "").name
        file_extension = Path(original_filename).suffix.lower()
        if file_extension not in self.allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="当前仅支持 TXT、Markdown 文档",
            )

        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="上传文档不能为空",
            )

        upload_root = Path(settings.upload_dir)
        knowledge_base_dir = upload_root / str(knowledge_base_id)
        knowledge_base_dir.mkdir(parents=True, exist_ok=True)

        # 文件名来自用户上传内容，不能直接信任。
        # 这里用 uuid 生成服务器内部文件名，避免重名覆盖和路径穿越问题。
        stored_filename = f"{uuid4().hex}{file_extension}"
        storage_path = knowledge_base_dir / stored_filename
        storage_path.write_bytes(file_bytes)

        return self.repository.create(
            knowledge_base_id=knowledge_base_id,
            filename=original_filename,
            file_type=file_extension.lstrip("."),
            file_size=len(file_bytes),
            storage_path=str(storage_path),
        )

    def list_documents(self, knowledge_base_id: int) -> list[dict]:
        self.knowledge_base_service.get_required_knowledge_base(knowledge_base_id)
        documents = self.repository.list_by_knowledge_base(knowledge_base_id)
        summaries_by_document_id = self.summary_repository.get_by_document_ids(
            [document.id for document in documents]
        )
        faqs_by_document_id = self.faq_repository.list_by_document_ids(
            [document.id for document in documents]
        )
        return [
            {
                "id": document.id,
                "knowledge_base_id": document.knowledge_base_id,
                "filename": document.filename,
                "file_type": document.file_type,
                "file_size": document.file_size,
                "status": document.status,
                "created_at": document.created_at,
                "summary": summaries_by_document_id.get(document.id),
                "faqs": faqs_by_document_id.get(document.id, []),
            }
            for document in documents
        ]
