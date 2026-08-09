"""Agent execution history tests."""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.models
from app.db.base import Base
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.schemas.agent import AgentIntent
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.agent_chat_service import AgentChatService
from app.services.conversation_service import ConversationService
from app.services.knowledge_base_service import KnowledgeBaseService


def build_database():
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def test_clarification_run_and_steps_are_available_in_conversation_history() -> None:
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="Agent 执行记录测试库")
        )
        result = AgentChatService(db).ask(
            knowledge_base_id=knowledge_base.id,
            question="请总结这份制度",
            conversation_id=None,
            top_k=3,
        )

        agent_run = db.scalar(select(AgentRun))
        agent_steps = list(db.scalars(select(AgentStep).order_by(AgentStep.step_order)))
        history = ConversationService(db).list_messages(result.conversation_id)

        assert agent_run.intent == AgentIntent.CLARIFICATION.value
        assert [step.tool_name for step in agent_steps] == [
            "agent_router",
            "ask_clarifying_question",
        ]
        assert history[1]["intent"] == AgentIntent.CLARIFICATION.value
        assert history[1]["execution_steps"][1]["tool_name"] == "ask_clarifying_question"
    finally:
        db.close()
