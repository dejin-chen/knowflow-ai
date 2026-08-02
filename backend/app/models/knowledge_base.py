from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class KnowledgeBase(Base):
    """知识库表。

    一个知识库可以理解成一个资料集合，例如“公司制度库”或“产品手册库”。
    后续 RAG 检索时，用户会先选择知识库，再只在这个知识库范围内检索。
    """

    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    documents = relationship(
        "Document",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )
    conversations = relationship(
        "Conversation",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )
    answer_caches = relationship(
        "RagAnswerCache",
        back_populates="knowledge_base",
        cascade="all, delete-orphan",
    )
