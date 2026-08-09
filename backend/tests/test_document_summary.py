"""Document summary tests."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models
from app.db.base import Base
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.agent_tool_service import AgentToolResult
from app.services.chat_completion_service import ChatCompletionResult
from app.services.document_summary_service import DocumentSummaryService
from app.services.knowledge_base_service import KnowledgeBaseService


class FakeAgentToolService:
    def __init__(self) -> None:
        self.calls = 0

    def summarize_document(self, knowledge_base_id: int, document_id: int) -> AgentToolResult:
        self.calls += 1
        return AgentToolResult(
            answer="员工手册摘要。[1]",
            citations=[{"reference_id": 1, "chunk_id": 1}],
            source_chunk_count=1,
            model_usage=ChatCompletionResult(
                answer="员工手册摘要。[1]",
                model_name="test-model",
                prompt_tokens=50,
                completion_tokens=10,
                total_tokens=60,
            ),
        )


def build_database():
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def test_document_summary_is_created_then_replaced_for_same_document() -> None:
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="文档摘要测试库")
        )
        document = Document(
            knowledge_base_id=knowledge_base.id,
            filename="员工手册.md",
            file_type="md",
            file_size=100,
            storage_path="/tmp/employee.md",
            status="indexed",
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        db.add(
            DocumentChunk(
                document_id=document.id,
                knowledge_base_id=knowledge_base.id,
                chunk_index=0,
                content="员工手册测试内容。",
                char_count=10,
                start_offset=0,
                end_offset=10,
            )
        )
        db.commit()

        fake_tool = FakeAgentToolService()
        service = DocumentSummaryService(db, agent_tool_service=fake_tool)
        first_summary = service.generate_summary(document.id)
        second_summary = service.generate_summary(document.id)

        assert first_summary.id == second_summary.id
        assert second_summary.total_tokens == 60
        assert fake_tool.calls == 2
        assert service.get_summary(document.id).content == "员工手册摘要。[1]"
    finally:
        db.close()
