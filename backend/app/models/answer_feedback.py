from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AnswerFeedback(Base):
    """一条助手回答的人工反馈。当前版本每条回答只允许一条反馈。"""

    __tablename__ = "answer_feedbacks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    assistant_message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    feedback_type: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
