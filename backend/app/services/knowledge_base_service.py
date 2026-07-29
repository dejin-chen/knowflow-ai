from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.knowledge_base import KnowledgeBase
from app.repositories.knowledge_base_repository import KnowledgeBaseRepository
from app.schemas.knowledge_base import KnowledgeBaseCreate


class KnowledgeBaseService:
    """知识库业务层。

    Service 负责业务规则：例如创建前清理名称、删除前确认资源存在。
    API 层不直接操作数据库，是为了让业务逻辑可以被接口、脚本、测试复用。
    """

    def __init__(self, db: Session) -> None:
        self.repository = KnowledgeBaseRepository(db)

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
        self.repository.delete(knowledge_base)
