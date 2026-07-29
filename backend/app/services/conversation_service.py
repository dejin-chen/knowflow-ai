from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message
from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.answer_feedback_repository import AnswerFeedbackRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.model_usage_repository import ModelUsageRepository
from app.services.knowledge_base_service import KnowledgeBaseService


class ConversationService:
    """读取已持久化的会话和消息，为前端历史记录展示提供数据。"""

    def __init__(self, db: Session) -> None:
        self.knowledge_base_service = KnowledgeBaseService(db)
        self.conversation_repository = ConversationRepository(db)
        self.message_repository = MessageRepository(db)
        self.agent_run_repository = AgentRunRepository(db)
        self.feedback_repository = AnswerFeedbackRepository(db)
        self.model_usage_repository = ModelUsageRepository(db)

    def list_conversations(self, knowledge_base_id: int) -> list[Conversation]:
        self.knowledge_base_service.get_required_knowledge_base(knowledge_base_id)
        return self.conversation_repository.list_by_knowledge_base(knowledge_base_id)

    def list_messages(self, conversation_id: int) -> list[dict]:
        if self.conversation_repository.get_by_id(conversation_id) is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在",
            )
        messages = self.message_repository.list_by_conversation(conversation_id)
        assistant_message_ids = [
            message.id for message in messages if message.role == "assistant"
        ]
        agent_runs_by_message_id = self.agent_run_repository.get_by_assistant_message_ids(
            assistant_message_ids
        )
        feedbacks_by_message_id = self.feedback_repository.get_by_assistant_message_ids(
            assistant_message_ids
        )
        model_usages_by_message_id = self.model_usage_repository.get_by_assistant_message_ids(
            assistant_message_ids
        )
        return [
            self._serialize_message(
                message,
                agent_runs_by_message_id.get(message.id),
                feedbacks_by_message_id.get(message.id),
                model_usages_by_message_id.get(message.id, []),
            )
            for message in messages
        ]

    @staticmethod
    def _serialize_message(message: Message, agent_run, feedback, model_usages) -> dict:
        return {
            "id": message.id,
            "conversation_id": message.conversation_id,
            "role": message.role,
            "content": message.content,
            "citations": message.citations,
            "intent": agent_run.intent if agent_run else None,
            "execution_steps": [
                {
                    "step_order": step.step_order,
                    "name": step.name,
                    "tool_name": step.tool_name,
                    "status": step.status,
                    "detail": step.detail,
                }
                for step in agent_run.steps
            ]
            if agent_run
            else [],
            "feedback": feedback,
            "model_usages": [
                {
                    "id": usage.id,
                    "assistant_message_id": usage.assistant_message_id,
                    "operation": usage.operation,
                    "model_name": usage.model_name,
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                    "total_tokens": usage.total_tokens,
                    "created_at": usage.created_at,
                }
                for usage in model_usages
            ],
            "created_at": message.created_at,
        }
