from pydantic import BaseModel, Field, field_validator

from app.schemas.agent import AgentExecutionStep, AgentIntent
from app.schemas.model_usage import ModelUsageRead


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None
    top_k: int | None = Field(default=None, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        normalized_value = value.strip()
        if not normalized_value:
            raise ValueError("问题不能为空")
        return normalized_value


class ChatCitationRead(BaseModel):
    reference_id: int
    chunk_id: int
    document_id: int
    filename: str
    chunk_index: int
    content: str
    distance: float | None


class ChatResponse(BaseModel):
    conversation_id: int
    assistant_message_id: int | None
    answer: str
    citations: list[ChatCitationRead]
    retrieved_chunk_count: int
    insufficient_evidence: bool
    cache_hit: bool
    intent: AgentIntent
    execution_steps: list[AgentExecutionStep]
    model_usages: list[ModelUsageRead]
