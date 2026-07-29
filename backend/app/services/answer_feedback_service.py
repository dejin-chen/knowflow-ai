from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.answer_feedback import AnswerFeedback
from app.repositories.answer_feedback_repository import AnswerFeedbackRepository
from app.repositories.message_repository import MessageRepository
from app.schemas.feedback import AnswerFeedbackCreate


@dataclass(frozen=True)
class FeedbackSubmissionResult:
    feedback: AnswerFeedback
    created: bool


class AnswerFeedbackService:
    """提交反馈前校验回答消息，避免给用户问题或不存在的消息写反馈。"""

    def __init__(self, db: Session) -> None:
        self.message_repository = MessageRepository(db)
        self.feedback_repository = AnswerFeedbackRepository(db)

    def submit_feedback(
        self,
        assistant_message_id: int,
        data: AnswerFeedbackCreate,
    ) -> FeedbackSubmissionResult:
        message = self.message_repository.get_by_id(assistant_message_id)
        if message is None or message.role != "assistant":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="助手回答不存在。",
            )

        existing_feedback = self.feedback_repository.get_by_assistant_message_id(
            assistant_message_id
        )
        if existing_feedback is not None:
            return FeedbackSubmissionResult(feedback=existing_feedback, created=False)

        feedback = self.feedback_repository.create(
            assistant_message_id=assistant_message_id,
            feedback_type=data.feedback_type.value,
            comment=data.comment,
        )
        return FeedbackSubmissionResult(feedback=feedback, created=True)
