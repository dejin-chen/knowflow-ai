from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ModelUsageRead(BaseModel):
    id: int
    assistant_message_id: int
    operation: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
