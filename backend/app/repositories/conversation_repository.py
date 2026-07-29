from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation


class ConversationRepository:
    """会话表的数据访问层。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, knowledge_base_id: int, title: str) -> Conversation:
        conversation = Conversation(knowledge_base_id=knowledge_base_id, title=title)
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def get_by_id(self, conversation_id: int) -> Conversation | None:
        return self.db.get(Conversation, conversation_id)

    def list_by_knowledge_base(self, knowledge_base_id: int) -> list[Conversation]:
        statement = (
            select(Conversation)
            .where(Conversation.knowledge_base_id == knowledge_base_id)
            .order_by(Conversation.updated_at.desc())
        )
        return list(self.db.scalars(statement).all())
