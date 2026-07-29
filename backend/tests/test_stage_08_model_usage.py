from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.models
from app.db.base import Base
from app.models.model_usage_log import ModelUsageLog
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.agent_chat_service import AgentChatService
from app.services.chat_completion_service import ChatCompletionResult
from app.services.conversation_service import ConversationService
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.rag_chat_service import RagChatService
from app.services.semantic_search_service import RetrievedChunk


class FakeSemanticSearchService:
    def search(self, knowledge_base_id: int, query: str, top_k: int):
        return [
            RetrievedChunk(
                chunk_id=1,
                document_id=2,
                knowledge_base_id=knowledge_base_id,
                filename="员工手册.md",
                chunk_index=0,
                content="病假需要医院证明材料。",
                distance=0.1,
            )
        ]


class FakeChatCompletionService:
    def generate_completion(self, prompt) -> ChatCompletionResult:
        return ChatCompletionResult(
            answer="病假需要医院证明材料。[1]",
            model_name="test-model",
            prompt_tokens=100,
            completion_tokens=20,
            total_tokens=120,
        )


def build_database():
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def test_rag_model_usage_is_persisted_and_returned_in_history() -> None:
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="Token 用量测试库")
        )
        rag_service = RagChatService(
            db,
            semantic_search_service=FakeSemanticSearchService(),
            chat_completion_service=FakeChatCompletionService(),
        )

        result = AgentChatService(db, rag_chat_service=rag_service).ask(
            knowledge_base_id=knowledge_base.id,
            question="病假需要什么材料？",
            conversation_id=None,
            top_k=3,
        )

        usage_log = db.scalar(select(ModelUsageLog))
        history = ConversationService(db).list_messages(result.conversation_id)

        assert result.model_usages[0]["total_tokens"] == 120
        assert usage_log.operation == "knowledge_qa"
        assert usage_log.prompt_tokens == 100
        assert history[1]["model_usages"][0]["completion_tokens"] == 20
    finally:
        db.close()


def test_clarification_does_not_create_model_usage() -> None:
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="无模型调用测试库")
        )
        result = AgentChatService(db).ask(
            knowledge_base_id=knowledge_base.id,
            question="请总结这份制度",
            conversation_id=None,
            top_k=3,
        )

        assert result.model_usages == []
        assert db.scalar(select(ModelUsageLog)) is None
    finally:
        db.close()
