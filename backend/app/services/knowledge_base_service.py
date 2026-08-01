import logging
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.models.knowledge_base import KnowledgeBase
from app.repositories.document_repository import DocumentRepository
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.vector_store_service import ChromaVectorStoreService


logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """知识库业务层。

    Service 负责业务规则：例如创建前清理名称、删除前确认资源存在。
    API 层不直接操作数据库，是为了让业务逻辑可以被接口、脚本、测试复用。
    """

    def __init__(
        self,
        db: Session,
        vector_store: ChromaVectorStoreService | None = None,
    ) -> None:
        self.repository = KnowledgeBaseRepository(db)
        self.document_repository = DocumentRepository(db)
        self.vector_store = vector_store

    def create_knowledge_base(self, data: KnowledgeBaseCreate) -> KnowledgeBase:
        name = data.name.strip()
        if not name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="知识库名称不能为空",
            )
        return self.repository.create(name=name, description=data.description)

    def list_knowledge_bases(self) -> list[KnowledgeBase]:
        return self.repository.list_all()

    def get_required_knowledge_base(self, knowledge_base_id: int) -> KnowledgeBase:
        knowledge_base = self.repository.get_by_id(knowledge_base_id)
        if knowledge_base is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="知识库不存在",
            )
        return knowledge_base

    def delete_knowledge_base(self, knowledge_base_id: int) -> None:
        knowledge_base = self.get_required_knowledge_base(knowledge_base_id)
        documents = self.document_repository.list_by_knowledge_base(knowledge_base_id)

        # Chroma 不属于关系型事务，先确认向量清理成功，再删除 SQLite 主数据。
        vector_store = self.vector_store or ChromaVectorStoreService()
        vector_store.delete_by_knowledge_base(knowledge_base_id)
        self.repository.delete(knowledge_base)
        self._delete_stored_files(documents)

    @staticmethod
    def _delete_stored_files(documents: list[Document]) -> None:
        upload_root = Path(settings.upload_dir).resolve()
        candidate_directories: set[Path] = set()

        for document in documents:
            stored_path = Path(document.storage_path).resolve()
            if not stored_path.is_relative_to(upload_root):
                logger.warning("跳过上传目录之外的文件清理: %s", stored_path)
                continue
            try:
                stored_path.unlink(missing_ok=True)
                candidate_directories.add(stored_path.parent)
            except OSError:
                # 数据库已经删除，文件清理失败只记录日志，避免接口返回不可重试的半失败状态。
                logger.exception("知识库已删除，但原始文件清理失败: %s", stored_path)

        for directory in candidate_directories:
            if directory == upload_root:
                continue
            try:
                directory.rmdir()
            except OSError:
                pass
