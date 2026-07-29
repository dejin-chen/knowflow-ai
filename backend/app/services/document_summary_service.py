from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.document_summary import DocumentSummary
from app.repositories.document_repository import DocumentRepository
from app.repositories.document_summary_repository import DocumentSummaryRepository
from app.services.agent_tool_service import AgentToolService


class DocumentSummaryService:
    """生成并保存文档级摘要，和聊天中的临时总结职责分离。"""

    def __init__(
        self,
        db: Session,
        agent_tool_service: AgentToolService | None = None,
    ) -> None:
        self.document_repository = DocumentRepository(db)
        self.summary_repository = DocumentSummaryRepository(db)
        self.agent_tool_service = agent_tool_service or AgentToolService(db)

    def get_summary(self, document_id: int) -> DocumentSummary:
        summary = self.summary_repository.get_by_document_id(document_id)
        if summary is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="该文档尚未生成摘要。",
            )
        return summary

    def generate_summary(self, document_id: int) -> DocumentSummary:
        document = self.document_repository.get_by_id(document_id)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="文档不存在。",
            )
        if document.status not in {"chunked", "indexed"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="请先完成文档切分后再生成摘要。",
            )

        tool_result = self.agent_tool_service.summarize_document(
            knowledge_base_id=document.knowledge_base_id,
            document_id=document.id,
        )
        if tool_result.model_usage is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="文档没有可供总结的文本。",
            )

        usage = tool_result.model_usage
        return self.summary_repository.upsert(
            document_id=document.id,
            content=tool_result.answer,
            citations=tool_result.citations,
            model_name=usage.model_name,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
        )
