from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.repositories.document_repository import DocumentRepository
from app.services.chat_completion_service import ChatCompletionResult, ChatCompletionService
from app.services.rag_prompt_service import PromptSource, RagPromptService


@dataclass(frozen=True)
class AgentToolResult:
    """文档型工具的统一输出，供 AgentChatService 保存和返回。"""

    answer: str
    citations: list[dict]
    source_chunk_count: int
    model_usage: ChatCompletionResult | None = None


class AgentToolService:
    """轻量 Agent 可调用的文档工具集合。"""

    def __init__(
        self,
        db: Session,
        chat_completion_service: ChatCompletionService | None = None,
    ) -> None:
        self.document_repository = DocumentRepository(db)
        self.chunk_repository = DocumentChunkRepository(db)
        self.chat_completion_service = chat_completion_service or ChatCompletionService()
        self.prompt_service = RagPromptService()

    def summarize_document(
        self,
        knowledge_base_id: int,
        document_id: int,
    ) -> AgentToolResult:
        document = self._get_required_document(knowledge_base_id, document_id)
        sources = self._load_sources([document])
        if not sources:
            return self._no_content_result("该文档还没有可供总结的文本，请先完成文档切分。")

        prompt = self.prompt_service.build_document_summary(document.filename, sources)
        completion = self.chat_completion_service.generate_completion(prompt)
        return self._build_result(completion, sources)

    def compare_documents(
        self,
        knowledge_base_id: int,
        document_ids: list[int],
    ) -> AgentToolResult:
        documents = [
            self._get_required_document(knowledge_base_id, document_id)
            for document_id in document_ids
        ]
        sources = self._load_sources(documents)
        if not sources:
            return self._no_content_result("指定文档还没有可供对比的文本，请先完成文档切分。")

        prompt = self.prompt_service.build_document_comparison(
            [document.filename for document in documents],
            sources,
        )
        completion = self.chat_completion_service.generate_completion(prompt)
        return self._build_result(completion, sources)

    def _get_required_document(self, knowledge_base_id: int, document_id: int) -> Document:
        document = self.document_repository.get_by_id(document_id)
        if document is None or document.knowledge_base_id != knowledge_base_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="目标文档不存在，或不属于当前知识库。",
            )
        return document

    def _load_sources(self, documents: list[Document]) -> list[PromptSource]:
        """读取指定文档的 Chunk，并控制总长度以保护模型上下文。"""
        sources: list[PromptSource] = []
        remaining_characters = settings.agent_tool_context_characters

        for document in documents:
            for chunk in self.chunk_repository.list_by_document(document.id):
                if remaining_characters <= 0:
                    return sources
                content = chunk.content[:remaining_characters]
                sources.append(
                    PromptSource(
                        reference_id=len(sources) + 1,
                        chunk_id=chunk.id,
                        document_id=document.id,
                        filename=document.filename,
                        chunk_index=chunk.chunk_index,
                        content=content,
                        distance=None,
                    )
                )
                remaining_characters -= len(content)

        return sources

    @staticmethod
    def _build_result(
        completion: ChatCompletionResult,
        sources: list[PromptSource],
    ) -> AgentToolResult:
        return AgentToolResult(
            answer=completion.answer,
            source_chunk_count=len(sources),
            model_usage=completion,
            citations=[
                {
                    "reference_id": source.reference_id,
                    "chunk_id": source.chunk_id,
                    "document_id": source.document_id,
                    "filename": source.filename,
                    "chunk_index": source.chunk_index,
                    "content": source.content,
                    "distance": source.distance,
                }
                for source in sources
            ],
        )

    @staticmethod
    def _no_content_result(answer: str) -> AgentToolResult:
        return AgentToolResult(
            answer=answer,
            citations=[],
            source_chunk_count=0,
            model_usage=None,
        )
