from dataclasses import asdict, dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.retrieval_log_repository import RetrievalLogRepository
from app.services.chat_completion_service import ChatCompletionResult, ChatCompletionService
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.rag_prompt_service import PromptSource, RagPromptService
from app.services.semantic_search_service import RetrievedChunk, SemanticSearchService


@dataclass(frozen=True)
class RagChatResult:
    conversation_id: int
    answer: str
    citations: list[dict]
    retrieved_chunk_count: int
    insufficient_evidence: bool
    assistant_message_id: int | None = None
    model_usage: ChatCompletionResult | None = None


class RagChatService:
    """协调检索、Prompt 构造、LLM 回答和问答日志持久化。"""

    insufficient_evidence_answer = "知识库中没有足够依据。"

    def __init__(
        self,
        db: Session,
        semantic_search_service: SemanticSearchService | None = None,
        chat_completion_service: ChatCompletionService | None = None,
    ) -> None:
        self.conversation_repository = ConversationRepository(db)
        self.message_repository = MessageRepository(db)
        self.retrieval_log_repository = RetrievalLogRepository(db)
        self.knowledge_base_service = KnowledgeBaseService(db)
        self.semantic_search_service = semantic_search_service or SemanticSearchService(db)
        self.chat_completion_service = chat_completion_service or ChatCompletionService()
        self.prompt_service = RagPromptService()

    def ask(
        self,
        knowledge_base_id: int,
        question: str,
        conversation_id: int | None,
        top_k: int | None,
    ) -> RagChatResult:
        self.knowledge_base_service.get_required_knowledge_base(knowledge_base_id)
        conversation = self._get_or_create_conversation(
            knowledge_base_id,
            conversation_id,
            question,
        )
        user_message = self.message_repository.create(
            conversation_id=conversation.id,
            role="user",
            content=question,
        )

        actual_top_k = top_k or settings.retrieval_top_k
        retrieved_chunks = self.semantic_search_service.search(
            knowledge_base_id=knowledge_base_id,
            query=question,
            top_k=actual_top_k,
        )
        best_distance = retrieved_chunks[0].distance if retrieved_chunks else None
        insufficient_evidence = (
            not retrieved_chunks
            or best_distance is not None
            and best_distance > settings.retrieval_distance_threshold
        )

        citations = self._build_citations(retrieved_chunks) if not insufficient_evidence else []
        model_usage = None
        if insufficient_evidence:
            answer = self.insufficient_evidence_answer
        else:
            sources = [
                PromptSource(**citation)
                for citation in citations
            ]
            prompt = self.prompt_service.build(question=question, sources=sources)
            model_usage = self.chat_completion_service.generate_completion(prompt)
            answer = model_usage.answer

        assistant_message = self.message_repository.create(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
            citations=citations,
        )
        self.retrieval_log_repository.create(
            conversation_id=conversation.id,
            user_message_id=user_message.id,
            assistant_message_id=assistant_message.id,
            knowledge_base_id=knowledge_base_id,
            query=question,
            top_k=actual_top_k,
            best_distance=best_distance,
            retrieved_chunks=[self._serialize_retrieved_chunk(chunk) for chunk in retrieved_chunks],
        )

        return RagChatResult(
            conversation_id=conversation.id,
            answer=answer,
            citations=citations,
            retrieved_chunk_count=len(retrieved_chunks),
            insufficient_evidence=insufficient_evidence,
            assistant_message_id=assistant_message.id,
            model_usage=model_usage,
        )

    def _get_or_create_conversation(
        self,
        knowledge_base_id: int,
        conversation_id: int | None,
        question: str,
    ):
        if conversation_id is None:
            return self.conversation_repository.create(
                knowledge_base_id=knowledge_base_id,
                title=question[:80],
            )

        conversation = self.conversation_repository.get_by_id(conversation_id)
        if conversation is None or conversation.knowledge_base_id != knowledge_base_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="会话不存在，或不属于当前知识库",
            )
        return conversation

    @staticmethod
    def _build_citations(chunks: list[RetrievedChunk]) -> list[dict]:
        return [
            {
                "reference_id": index,
                "chunk_id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "filename": chunk.filename,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content,
                "distance": chunk.distance,
            }
            for index, chunk in enumerate(chunks, start=1)
        ]

    @staticmethod
    def _serialize_retrieved_chunk(chunk: RetrievedChunk) -> dict:
        return asdict(chunk)
