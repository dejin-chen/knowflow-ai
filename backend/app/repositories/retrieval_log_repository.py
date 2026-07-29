from typing import Any

from sqlalchemy.orm import Session

from app.models.retrieval_log import RetrievalLog


class RetrievalLogRepository:
    """检索日志的数据访问层。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        conversation_id: int,
        user_message_id: int,
        assistant_message_id: int,
        knowledge_base_id: int,
        query: str,
        top_k: int,
        best_distance: float | None,
        retrieved_chunks: list[dict[str, Any]],
    ) -> RetrievalLog:
        retrieval_log = RetrievalLog(
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            knowledge_base_id=knowledge_base_id,
            query=query,
            top_k=top_k,
            best_distance=best_distance,
            retrieved_chunks=retrieved_chunks,
        )
        self.db.add(retrieval_log)
        self.db.commit()
        self.db.refresh(retrieval_log)
        return retrieval_log
