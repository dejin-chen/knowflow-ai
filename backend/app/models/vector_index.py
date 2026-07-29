from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class VectorIndex(Base):
    """Chunk 与 Chroma 向量记录之间的映射。

    向量数组由 Chroma 保存；SQLite 只保存可追踪的业务映射和索引状态。
    这样即使以后切换向量库，也不需要改变 document_chunks 的主数据结构。
    """

    __tablename__ = "vector_indexes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    chroma_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="indexed", nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    chunk = relationship("DocumentChunk", back_populates="vector_index")
