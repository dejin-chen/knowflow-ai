from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.message import Message


class MessageRepository:
    """会话消息的数据访问层。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        conversation_id: int,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> Message:
        message = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            citations=citations or [],
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def list_by_conversation(self, conversation_id: int) -> list[Message]:
        statement = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at, Message.id)
        )
        return list(self.db.scalars(statement).all())

    def get_by_id(self, message_id: int) -> Message | None:
        return self.db.get(Message, message_id)
