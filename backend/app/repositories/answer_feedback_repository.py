from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.answer_feedback import AnswerFeedback


class AnswerFeedbackRepository:
    """回答反馈的数据访问层。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_assistant_message_id(self, assistant_message_id: int) -> AnswerFeedback | None:
        statement = select(AnswerFeedback).where(
            AnswerFeedback.assistant_message_id == assistant_message_id
        )
        return self.db.scalar(statement)

    def get_by_assistant_message_ids(
        self,
        assistant_message_ids: list[int],
    ) -> dict[int, AnswerFeedback]:
        if not assistant_message_ids:
            return {}
        statement = select(AnswerFeedback).where(
            AnswerFeedback.assistant_message_id.in_(assistant_message_ids)
        )
        feedbacks = self.db.scalars(statement).all()
        return {
            feedback.assistant_message_id: feedback
            for feedback in feedbacks
        }

    def create(
        self,
        assistant_message_id: int,
        feedback_type: str,
        comment: str | None,
    ) -> AnswerFeedback:
        feedback = AnswerFeedback(
            assistant_message_id=assistant_message_id,
            feedback_type=feedback_type,
            comment=comment,
        )
        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)
        return feedback
