from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.models
from app.db.base import Base
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.retrieval_log import RetrievalLog
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.conversation_service import ConversationService
from app.services.chat_completion_service import ChatCompletionResult
from app.services.rag_chat_service import RagChatService
from app.services.semantic_search_service import RetrievedChunk


class FakeSemanticSearchService:
    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self.chunks = chunks
        self.calls: list[tuple[int, str, int]] = []

    def search(self, knowledge_base_id: int, query: str, top_k: int) -> list[RetrievedChunk]:
        self.calls.append((knowledge_base_id, query, top_k))
        return self.chunks[:top_k]


class FakeChatCompletionService:
    def __init__(self) -> None:
        self.last_prompt = None

    def generate_completion(self, prompt) -> ChatCompletionResult:
        self.last_prompt = prompt
        return ChatCompletionResult(
            answer="申请病假需要提供医院出具的证明材料。[1]",
            model_name="test-model",
            prompt_tokens=12,
            completion_tokens=8,
            total_tokens=20,
        )


class FailingChatCompletionService:
    def generate_completion(self, prompt) -> ChatCompletionResult:
        raise AssertionError("资料不足时不应调用聊天模型")


def build_database():
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def test_rag_chat_generates_answer_and_persists_audit_data() -> None:
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="RAG 问答测试库")
        )
        retrieved_chunk = RetrievedChunk(
            chunk_id=101,
            document_id=12,
            knowledge_base_id=knowledge_base.id,
            filename="员工手册.md",
            chunk_index=2,
            content="员工申请病假时，需要提供医院出具的证明材料。",
            distance=0.12,
        )
        fake_search = FakeSemanticSearchService([retrieved_chunk])
        fake_chat = FakeChatCompletionService()
        service = RagChatService(
            db,
            semantic_search_service=fake_search,
            chat_completion_service=fake_chat,
        )

        result = service.ask(
            knowledge_base_id=knowledge_base.id,
            question="病假需要什么材料？",
            conversation_id=None,
            top_k=3,
        )

        conversation = db.scalar(select(Conversation))
        messages = list(db.scalars(select(Message).order_by(Message.id)).all())
        retrieval_log = db.scalar(select(RetrievalLog))

        assert result.insufficient_evidence is False
        assert result.answer.endswith("[1]")
        assert result.citations[0]["chunk_id"] == 101
        assert fake_search.calls == [(knowledge_base.id, "病假需要什么材料？", 3)]
        assert "参考资料 [1]" in fake_chat.last_prompt.user_message
        assert conversation.knowledge_base_id == knowledge_base.id
        assert [message.role for message in messages] == ["user", "assistant"]
        assert messages[1].citations[0]["filename"] == "员工手册.md"
        assert retrieval_log.best_distance == 0.12
        assert retrieval_log.retrieved_chunks[0]["chunk_id"] == 101

        conversation_service = ConversationService(db)
        assert conversation_service.list_conversations(knowledge_base.id)[0].id == conversation.id
        assert len(conversation_service.list_messages(conversation.id)) == 2
    finally:
        db.close()


def test_rag_chat_returns_insufficient_evidence_without_calling_llm() -> None:
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="资料不足测试库")
        )
        service = RagChatService(
            db,
            semantic_search_service=FakeSemanticSearchService([]),
            chat_completion_service=FailingChatCompletionService(),
        )

        result = service.ask(
            knowledge_base_id=knowledge_base.id,
            question="公司总部在哪里？",
            conversation_id=None,
            top_k=3,
        )

        assert result.answer == "知识库中没有足够依据。"
        assert result.insufficient_evidence is True
        assert result.citations == []
        assert db.scalar(select(RetrievalLog)).best_distance is None
    finally:
        db.close()


def test_rag_chat_uses_minimum_vector_distance_after_rerank() -> None:
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="Rerank 证据阈值测试库")
        )
        reranked_chunks = [
            RetrievedChunk(
                chunk_id=1,
                document_id=1,
                knowledge_base_id=knowledge_base.id,
                filename="制度.md",
                chunk_index=1,
                content="词法证据更明确的片段。",
                distance=0.7,
                rerank_score=0.8,
            ),
            RetrievedChunk(
                chunk_id=2,
                document_id=1,
                knowledge_base_id=knowledge_base.id,
                filename="制度.md",
                chunk_index=2,
                content="向量距离最近的片段。",
                distance=0.2,
                rerank_score=0.6,
            ),
        ]
        fake_chat = FakeChatCompletionService()
        service = RagChatService(
            db,
            semantic_search_service=FakeSemanticSearchService(reranked_chunks),
            chat_completion_service=fake_chat,
        )

        result = service.ask(
            knowledge_base_id=knowledge_base.id,
            question="制度内容是什么？",
            conversation_id=None,
            top_k=2,
        )

        assert result.insufficient_evidence is False
        assert fake_chat.last_prompt is not None
        assert db.scalar(select(RetrievalLog)).best_distance == 0.2
    finally:
        db.close()
