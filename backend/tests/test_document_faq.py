"""Document FAQ generation tests."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models
from app.db.base import Base
from app.models.document import Document
from app.models.document_summary import DocumentSummary
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.chat_completion_service import ChatCompletionResult
from app.services.document_faq_service import DocumentFaqService
from app.services.knowledge_base_service import KnowledgeBaseService


class FakeChatCompletionService:
    def generate_completion(self, prompt) -> ChatCompletionResult:
        return ChatCompletionResult(
            answer=(
                '[{"question":"病假需要什么材料？","answer":"需要医院证明。",'
                '"reference_ids":[1]},'
                '{"question":"年假如何申请？","answer":"需要提前申请。",'
                '"reference_ids":[1]},'
                '{"question":"报销何时提交？","answer":"应在规定期限内提交。",'
                '"reference_ids":[1]},'
                '{"question":"采购如何审批？","answer":"按采购金额审批。",'
                '"reference_ids":[1]}]'
            ),
            model_name="test-model",
            prompt_tokens=80,
            completion_tokens=60,
            total_tokens=140,
        )


def build_database():
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def test_document_faqs_are_generated_from_summary_citations_and_replaced() -> None:
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="FAQ 测试库")
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
            DocumentSummary(
                document_id=document.id,
                content="包含病假、年假、报销和采购制度。",
                citations=[
                    {
                        "reference_id": 1,
                        "chunk_id": 1,
                        "document_id": document.id,
                        "filename": document.filename,
                        "chunk_index": 0,
                        "content": "制度原文片段。",
                        "distance": None,
                    }
                ],
            )
        )
        db.commit()

        service = DocumentFaqService(
            db,
            chat_completion_service=FakeChatCompletionService(),
        )
        first_faqs = service.generate_faqs(document.id)
        second_faqs = service.generate_faqs(document.id)

        assert len(first_faqs) == 4
        assert len(second_faqs) == 4
        assert service.list_faqs(document.id)[0].citations[0]["reference_id"] == 1
    finally:
        db.close()
