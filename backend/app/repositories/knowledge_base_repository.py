from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge_base import KnowledgeBase


class KnowledgeBaseRepository:
    """知识库数据访问层。

    Repository 只关心数据库怎么读写，不处理 HTTP，也不处理文件保存。
    这样以后换数据库或补充复杂查询时，业务层不用大改。
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, name: str, description: str | None) -> KnowledgeBase:
        knowledge_base = KnowledgeBase(name=name, description=description)
        self.db.add(knowledge_base)
        self.db.commit()
        self.db.refresh(knowledge_base)
        return knowledge_base

    def list_all(self) -> list[KnowledgeBase]:
        statement = select(KnowledgeBase).order_by(KnowledgeBase.created_at.desc())
        return list(self.db.scalars(statement).all())

    def get_by_id(self, knowledge_base_id: int) -> KnowledgeBase | None:
        return self.db.get(KnowledgeBase, knowledge_base_id)

    def delete(self, knowledge_base: KnowledgeBase) -> None:
        self.db.delete(knowledge_base)
        self.db.commit()
