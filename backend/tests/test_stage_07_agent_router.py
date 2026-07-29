from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.models
from app.db.base import Base
from app.models.message import Message
from app.schemas.agent import AgentIntent, AvailableDocument
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.agent_router_service import AgentRouterService
from app.services.agent_chat_service import AgentChatService
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.rag_chat_service import RagChatResult


def build_documents() -> list[AvailableDocument]:
    return [
        AvailableDocument(id=1, filename="员工手册.md"),
        AvailableDocument(id=2, filename="报销制度.md"),
    ]


def test_router_routes_regular_question_to_knowledge_base_search() -> None:
    decision = AgentRouterService().route(
        question="连续病假超过三天需要什么材料？",
        available_documents=build_documents(),
    )

    assert decision.intent == AgentIntent.KNOWLEDGE_QA
    assert decision.tool_name == "search_knowledge_base"
    assert decision.document_ids == []


def test_router_routes_named_document_summary() -> None:
    decision = AgentRouterService().route(
        question="请总结员工手册",
        available_documents=build_documents(),
    )

    assert decision.intent == AgentIntent.DOCUMENT_SUMMARY
    assert decision.tool_name == "summarize_document"
    assert decision.document_ids == [1]


def test_router_asks_for_clarification_when_summary_target_is_missing() -> None:
    decision = AgentRouterService().route(
        question="请总结这份制度",
        available_documents=build_documents(),
    )

    assert decision.intent == AgentIntent.CLARIFICATION
    assert decision.tool_name == "ask_clarifying_question"
    assert decision.message == "请说明要总结哪一份文档。"


def test_router_routes_comparison_only_after_two_documents_are_matched() -> None:
    decision = AgentRouterService().route(
        question="比较员工手册和报销制度的差异",
        available_documents=build_documents(),
    )

    assert decision.intent == AgentIntent.DOCUMENT_COMPARISON
    assert decision.tool_name == "compare_documents"
    assert decision.document_ids == [1, 2]


class FakeRagChatService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def ask(self, **kwargs) -> RagChatResult:
        self.calls.append(kwargs)
        return RagChatResult(
            conversation_id=9,
            answer="病假需要医院证明材料。[1]",
            citations=[],
            retrieved_chunk_count=1,
            insufficient_evidence=False,
        )


def build_database():
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def test_agent_chat_reuses_rag_service_for_knowledge_qa() -> None:
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="Agent 问答测试库")
        )
        fake_rag_service = FakeRagChatService()
        result = AgentChatService(
            db,
            rag_chat_service=fake_rag_service,
        ).ask(
            knowledge_base_id=knowledge_base.id,
            question="病假需要什么材料？",
            conversation_id=None,
            top_k=3,
        )

        assert result.intent == AgentIntent.KNOWLEDGE_QA
        assert result.answer.endswith("[1]")
        assert [step.tool_name for step in result.execution_steps] == [
            "agent_router",
            "search_knowledge_base",
        ]
        assert fake_rag_service.calls[0]["knowledge_base_id"] == knowledge_base.id
    finally:
        db.close()


def test_agent_chat_persists_clarifying_question() -> None:
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="Agent 追问测试库")
        )
        result = AgentChatService(db).ask(
            knowledge_base_id=knowledge_base.id,
            question="请总结这份制度",
            conversation_id=None,
            top_k=3,
        )

        messages = list(db.scalars(select(Message).order_by(Message.id)).all())
        assert result.intent == AgentIntent.CLARIFICATION
        assert result.answer == "请说明要总结哪一份文档。"
        assert [message.role for message in messages] == ["user", "assistant"]
        assert result.execution_steps[1].tool_name == "ask_clarifying_question"
    finally:
        db.close()
