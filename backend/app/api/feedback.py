from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.feedback import AnswerFeedbackCreate, AnswerFeedbackSubmitResponse
from app.services.answer_feedback_service import AnswerFeedbackService

router = APIRouter(prefix="/messages", tags=["answer_feedback"])


@router.post(
    "/{assistant_message_id}/feedback",
    response_model=AnswerFeedbackSubmitResponse,
)
def submit_answer_feedback(
    assistant_message_id: int,
    data: AnswerFeedbackCreate,
    db: Session = Depends(get_db),
):
    result = AnswerFeedbackService(db).submit_feedback(assistant_message_id, data)
    return AnswerFeedbackSubmitResponse(
        feedback=result.feedback,
        created=result.created,
    )
