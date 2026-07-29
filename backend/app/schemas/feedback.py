from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class FeedbackType(str, Enum):
    HELPFUL = "helpful"
    UNHELPFUL = "unhelpful"


class AnswerFeedbackCreate(BaseModel):
    feedback_type: FeedbackType
    comment: str | None = None


class AnswerFeedbackRead(BaseModel):
    id: int
    assistant_message_id: int
    feedback_type: FeedbackType
    comment: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnswerFeedbackSubmitResponse(BaseModel):
    feedback: AnswerFeedbackRead
    created: bool
