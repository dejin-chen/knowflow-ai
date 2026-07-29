from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.agent import AgentExecutionStep, AgentIntent
from app.schemas.feedback import AnswerFeedbackRead
from app.schemas.model_usage import ModelUsageRead


class ConversationRead(BaseModel):
    id: int
    knowledge_base_id: int
    title: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MessageRead(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    citations: list[dict[str, Any]]
    intent: AgentIntent | None = None
    execution_steps: list[AgentExecutionStep] = Field(default_factory=list)
    feedback: AnswerFeedbackRead | None = None
    model_usages: list[ModelUsageRead] = Field(default_factory=list)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
