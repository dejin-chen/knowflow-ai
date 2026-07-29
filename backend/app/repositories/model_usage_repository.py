from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.model_usage_log import ModelUsageLog


class ModelUsageRepository:
    """模型调用用量日志的数据访问层。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        assistant_message_id: int,
        operation: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ) -> ModelUsageLog:
        usage_log = ModelUsageLog(
            assistant_message_id=assistant_message_id,
            operation=operation,
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )
        self.db.add(usage_log)
        self.db.commit()
        self.db.refresh(usage_log)
        return usage_log

    def get_by_assistant_message_ids(
        self,
        assistant_message_ids: list[int],
    ) -> dict[int, list[ModelUsageLog]]:
        if not assistant_message_ids:
            return {}
        statement = (
            select(ModelUsageLog)
            .where(ModelUsageLog.assistant_message_id.in_(assistant_message_ids))
            .order_by(ModelUsageLog.created_at, ModelUsageLog.id)
        )
        logs_by_message_id: dict[int, list[ModelUsageLog]] = {}
        for usage_log in self.db.scalars(statement):
            logs_by_message_id.setdefault(usage_log.assistant_message_id, []).append(
                usage_log
            )
        return logs_by_message_id
