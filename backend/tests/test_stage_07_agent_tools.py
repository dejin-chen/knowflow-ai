from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.models
from app.db.base import Base
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.message import Message
from app.schemas.agent import AgentIntent
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.agent_chat_service import AgentChatService
from app.services.agent_tool_service import AgentToolResult, AgentToolService
from app.services.chat_completion_service import ChatCompletionResult
from app.services.knowledge_base_service import KnowledgeBaseService


class FakeChatCompletionService:
    def __init__(self) -> None:
        self.prompts = []

    def generate_completion(self, prompt) -> ChatCompletionResult:
        self.prompts.append(prompt)
        return ChatCompletionResult(
            answer="这是基于文档片段生成的结果。[1]",
            model_name="test-model",
            prompt_tokens=15,
            completion_tokens=10,
            total_tokens=25,
        )


def build_database():
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def add_document_with_chunk(db, knowledge_base_id: int, document_id: int, filename: str) -> None:
    db.add(
        Document(
            id=document_id,
            knowledge_base_id=knowledge_base_id,
            filename=filename,
            file_type="md",
            file_size=100,
            storage_path=f"/tmp/{filename}",
            status="indexed",
        )
    )
    db.add(
        DocumentChunk(
            document_id=document_id,
            knowledge_base_id=knowledge_base_id,
            chunk_index=0,
            content=f"{filename} 的测试内容。",
            char_count=10,
            start_offset=0,
            end_offset=10,
        )
    )
    db.commit()


def test_document_tools_build_prompts_from_sqlite_chunks() -> None:
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="Agent 文档工具测试库")
        )
        add_document_with_chunk(db, knowledge_base.id, 11, "员工手册.md")
        add_document_with_chunk(db, knowledge_base.id, 12, "报销制度.md")
        fake_chat = FakeChatCompletionService()
        service = AgentToolService(db, chat_completion_service=fake_chat)

        summary_result = service.summarize_document(knowledge_base.id, 11)
        comparison_result = service.compare_documents(knowledge_base.id, [11, 12])

        assert summary_result.source_chunk_count == 1
        assert summary_result.citations[0]["distance"] is None
        assert "请总结文档《员工手册.md》" in fake_chat.prompts[0].user_message
        assert comparison_result.source_chunk_count == 2
        assert "请比较以下文档：员工手册.md、报销制度.md" in fake_chat.prompts[1].user_message
    finally:
        db.close()


class FakeAgentToolService:
    def summarize_document(self, knowledge_base_id: int, document_id: int) -> AgentToolResult:
        return AgentToolResult(answer="员工手册摘要。[1]", citations=[], source_chunk_count=1)


def test_agent_chat_executes_summary_tool_and_persists_messages() -> None:
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="Agent 总结编排测试库")
        )
        add_document_with_chunk(db, knowledge_base.id, 21, "员工手册.md")

        result = AgentChatService(
            db,
            agent_tool_service=FakeAgentToolService(),
        ).ask(
            knowledge_base_id=knowledge_base.id,
            question="请总结员工手册",
            conversation_id=None,
            top_k=3,
        )

        messages = list(db.scalars(select(Message).order_by(Message.id)).all())
        assert result.intent == AgentIntent.DOCUMENT_SUMMARY
        assert result.execution_steps[1].tool_name == "summarize_document"
        assert [message.role for message in messages] == ["user", "assistant"]
    finally:
        db.close()
