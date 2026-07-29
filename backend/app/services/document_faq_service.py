import json

from fastapi import HTTPException, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.models.document_faq import DocumentFaq
from app.repositories.document_faq_repository import DocumentFaqRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.document_summary_repository import DocumentSummaryRepository
from app.schemas.document_faq import DocumentFaqDraft
from app.services.chat_completion_service import ChatCompletionService
from app.services.rag_prompt_service import PromptSource, RagPromptService


class DocumentFaqService:
    """从已保存摘要及其可追溯引用中生成结构化 FAQ。"""

    faq_count = 4

    def __init__(
        self,
        db: Session,
        chat_completion_service: ChatCompletionService | None = None,
    ) -> None:
        self.document_repository = DocumentRepository(db)
        self.summary_repository = DocumentSummaryRepository(db)
        self.faq_repository = DocumentFaqRepository(db)
        self.chat_completion_service = chat_completion_service or ChatCompletionService()
        self.prompt_service = RagPromptService()

    def list_faqs(self, document_id: int) -> list[DocumentFaq]:
        self._get_required_document(document_id)
        return self.faq_repository.list_by_document_id(document_id)

    def generate_faqs(self, document_id: int) -> list[DocumentFaq]:
        document = self._get_required_document(document_id)
        summary = self.summary_repository.get_by_document_id(document_id)
        if summary is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="请先生成文档摘要后再生成 FAQ。",
            )

        sources = [PromptSource(**citation) for citation in summary.citations]
        if not sources:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="文档摘要没有可用于 FAQ 的引用来源。",
            )

        prompt = self.prompt_service.build_document_faq(
            filename=document.filename,
            summary=summary.content,
            sources=sources,
            faq_count=self.faq_count,
        )
        completion = self.chat_completion_service.generate_completion(prompt)
        drafts = self._parse_and_validate_drafts(completion.answer, sources)
        return self.faq_repository.replace_by_document(
            document_id,
            [
                {
                    "question": draft.question,
                    "answer": draft.answer,
                    "citations": [
                        citation
                        for citation in summary.citations
                        if citation["reference_id"] in draft.reference_ids
                    ],
                }
                for draft in drafts
            ],
        )

    def _get_required_document(self, document_id: int):
        document = self.document_repository.get_by_id(document_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在。",
            )
        return document

    def _parse_and_validate_drafts(
        self,
        raw_answer: str,
        sources: list[PromptSource],
    ) -> list[DocumentFaqDraft]:
        normalized_answer = self._remove_code_fence(raw_answer)
        try:
            payload = json.loads(normalized_answer)
            drafts = TypeAdapter(list[DocumentFaqDraft]).validate_python(payload)
        except (json.JSONDecodeError, ValidationError) as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="FAQ 模型输出格式无效，请重新生成。",
            ) from error

        if len(drafts) != self.faq_count:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"FAQ 数量应为 {self.faq_count} 条，请重新生成。",
            )

        available_reference_ids = {source.reference_id for source in sources}
        for draft in drafts:
            if not set(draft.reference_ids).issubset(available_reference_ids):
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="FAQ 引用了不存在的来源编号，请重新生成。",
                )
        return drafts

    @staticmethod
    def _remove_code_fence(raw_answer: str) -> str:
        normalized_answer = raw_answer.strip()
        if normalized_answer.startswith("```") and normalized_answer.endswith("```"):
            lines = normalized_answer.splitlines()
            return "\n".join(lines[1:-1]).strip()
        return normalized_answer
