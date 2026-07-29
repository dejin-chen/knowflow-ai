from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.agent_run_repository import AgentRunRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.document_repository import DocumentRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.model_usage_repository import ModelUsageRepository
from app.schemas.agent import AgentExecutionStep, AgentIntent, AvailableDocument
from app.services.agent_router_service import AgentRouterService
from app.services.agent_tool_service import AgentToolResult, AgentToolService
from app.services.chat_completion_service import ChatCompletionResult
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.rag_chat_service import RagChatResult, RagChatService


@dataclass(frozen=True)
class AgentChatResult:
    """聊天接口输出：回答、引用、执行过程和模型用量。"""

    conversation_id: int
    assistant_message_id: int | None
    answer: str
    citations: list[dict]
    retrieved_chunk_count: int
    insufficient_evidence: bool
    intent: AgentIntent
    execution_steps: list[AgentExecutionStep]
    model_usages: list[dict]


class AgentChatService:
    """协调 Router 与工具，并持久化执行步骤和模型用量。"""

    def __init__(
        self,
        db: Session,
        router_service: AgentRouterService | None = None,
        rag_chat_service: RagChatService | None = None,
        agent_tool_service: AgentToolService | None = None,
    ) -> None:
        self.knowledge_base_service = KnowledgeBaseService(db)
        self.document_repository = DocumentRepository(db)
        self.conversation_repository = ConversationRepository(db)
        self.message_repository = MessageRepository(db)
        self.agent_run_repository = AgentRunRepository(db)
        self.model_usage_repository = ModelUsageRepository(db)
        self.router_service = router_service or AgentRouterService()
        self.rag_chat_service = rag_chat_service or RagChatService(db)
        self.agent_tool_service = agent_tool_service or AgentToolService(db)

    def ask(
        self,
        knowledge_base_id: int,
        question: str,
        conversation_id: int | None,
        top_k: int | None,
    ) -> AgentChatResult:
        documents = self.document_repository.list_by_knowledge_base(knowledge_base_id)
        available_documents = [
            AvailableDocument(id=document.id, filename=document.filename)
            for document in documents
        ]
        decision = self.router_service.route(question, available_documents)
        routing_step = AgentExecutionStep(
            step_order=1,
            name="识别问题类型",
            tool_name="agent_router",
            status="completed",
            detail=f"识别为 {decision.intent.value}，将调用 {decision.tool_name}。",
        )

        if decision.intent == AgentIntent.KNOWLEDGE_QA:
            rag_result = self.rag_chat_service.ask(
                knowledge_base_id=knowledge_base_id,
                question=question,
                conversation_id=conversation_id,
                top_k=top_k,
            )
            model_usages = self._record_model_usage(
                rag_result.assistant_message_id,
                AgentIntent.KNOWLEDGE_QA,
                rag_result.model_usage,
            )
            result = self._build_knowledge_qa_result(
                rag_result,
                routing_step,
                model_usages,
            )
            self._record_execution(
                knowledge_base_id,
                result,
                rag_result.assistant_message_id,
            )
            return result

        if decision.intent == AgentIntent.DOCUMENT_SUMMARY:
            tool_result = self.agent_tool_service.summarize_document(
                knowledge_base_id,
                decision.document_ids[0],
            )
            return self._complete_document_tool(
                knowledge_base_id=knowledge_base_id,
                question=question,
                conversation_id=conversation_id,
                tool_result=tool_result,
                intent=AgentIntent.DOCUMENT_SUMMARY,
                tool_name="summarize_document",
                step_name="总结指定文档",
                routing_step=routing_step,
            )

        if decision.intent == AgentIntent.DOCUMENT_COMPARISON:
            tool_result = self.agent_tool_service.compare_documents(
                knowledge_base_id,
                decision.document_ids,
            )
            return self._complete_document_tool(
                knowledge_base_id=knowledge_base_id,
                question=question,
                conversation_id=conversation_id,
                tool_result=tool_result,
                intent=AgentIntent.DOCUMENT_COMPARISON,
                tool_name="compare_documents",
                step_name="对比指定文档",
                routing_step=routing_step,
            )

        return self._ask_clarifying_question(
            knowledge_base_id=knowledge_base_id,
            question=question,
            conversation_id=conversation_id,
            answer=decision.message or "请补充更多信息。",
            routing_step=routing_step,
        )

    @staticmethod
    def _build_knowledge_qa_result(
        rag_result: RagChatResult,
        routing_step: AgentExecutionStep,
        model_usages: list[dict],
    ) -> AgentChatResult:
        tool_step = AgentExecutionStep(
            step_order=2,
            name="检索知识库并生成回答",
            tool_name="search_knowledge_base",
            status="completed",
            detail=f"返回 {rag_result.retrieved_chunk_count} 个检索片段。",
        )
        return AgentChatResult(
            conversation_id=rag_result.conversation_id,
            assistant_message_id=rag_result.assistant_message_id,
            answer=rag_result.answer,
            citations=rag_result.citations,
            retrieved_chunk_count=rag_result.retrieved_chunk_count,
            insufficient_evidence=rag_result.insufficient_evidence,
            intent=AgentIntent.KNOWLEDGE_QA,
            execution_steps=[routing_step, tool_step],
            model_usages=model_usages,
        )

    def _complete_document_tool(
        self,
        knowledge_base_id: int,
        question: str,
        conversation_id: int | None,
        tool_result: AgentToolResult,
        intent: AgentIntent,
        tool_name: str,
        step_name: str,
        routing_step: AgentExecutionStep,
    ) -> AgentChatResult:
        self.knowledge_base_service.get_required_knowledge_base(knowledge_base_id)
        conversation = self._get_or_create_conversation(
            knowledge_base_id,
            conversation_id,
            question,
        )
        self.message_repository.create(
            conversation_id=conversation.id,
            role="user",
            content=question,
        )
        assistant_message = self.message_repository.create(
            conversation_id=conversation.id,
            role="assistant",
            content=tool_result.answer,
            citations=tool_result.citations,
        )
        tool_step = AgentExecutionStep(
            step_order=2,
            name=step_name,
            tool_name=tool_name,
            status="completed",
            detail=f"使用 {tool_result.source_chunk_count} 个文档片段。",
        )
        model_usages = self._record_model_usage(
            assistant_message.id,
            intent,
            tool_result.model_usage,
        )
        result = AgentChatResult(
            conversation_id=conversation.id,
            assistant_message_id=assistant_message.id,
            answer=tool_result.answer,
            citations=tool_result.citations,
            retrieved_chunk_count=tool_result.source_chunk_count,
            insufficient_evidence=False,
            intent=intent,
            execution_steps=[routing_step, tool_step],
            model_usages=model_usages,
        )
        self._record_execution(knowledge_base_id, result, assistant_message.id)
        return result

    def _ask_clarifying_question(
        self,
        knowledge_base_id: int,
        question: str,
        conversation_id: int | None,
        answer: str,
        routing_step: AgentExecutionStep,
    ) -> AgentChatResult:
        self.knowledge_base_service.get_required_knowledge_base(knowledge_base_id)
        conversation = self._get_or_create_conversation(
            knowledge_base_id,
            conversation_id,
            question,
        )
        self.message_repository.create(
            conversation_id=conversation.id,
            role="user",
            content=question,
        )
        assistant_message = self.message_repository.create(
            conversation_id=conversation.id,
            role="assistant",
            content=answer,
        )
        tool_step = AgentExecutionStep(
            step_order=2,
            name="请求补充信息",
            tool_name="ask_clarifying_question",
            status="completed",
            detail="目标文档不明确，暂不执行检索或生成。",
        )
        result = AgentChatResult(
            conversation_id=conversation.id,
            assistant_message_id=assistant_message.id,
            answer=answer,
            citations=[],
            retrieved_chunk_count=0,
            insufficient_evidence=False,
            intent=AgentIntent.CLARIFICATION,
            execution_steps=[routing_step, tool_step],
            model_usages=[],
        )
        self._record_execution(knowledge_base_id, result, assistant_message.id)
        return result

    def _record_model_usage(
        self,
        assistant_message_id: int | None,
        intent: AgentIntent,
        completion: ChatCompletionResult | None,
    ) -> list[dict]:
        """仅在真实模型调用后记录用量，避免把规则分支误计为模型成本。"""
        if assistant_message_id is None or completion is None:
            return []
        usage_log = self.model_usage_repository.create(
            assistant_message_id=assistant_message_id,
            operation=intent.value,
            model_name=completion.model_name,
            prompt_tokens=completion.prompt_tokens,
            completion_tokens=completion.completion_tokens,
            total_tokens=completion.total_tokens,
        )
        return [self._serialize_model_usage(usage_log)]

    @staticmethod
    def _serialize_model_usage(usage_log) -> dict:
        return {
            "id": usage_log.id,
            "assistant_message_id": usage_log.assistant_message_id,
            "operation": usage_log.operation,
            "model_name": usage_log.model_name,
            "prompt_tokens": usage_log.prompt_tokens,
            "completion_tokens": usage_log.completion_tokens,
            "total_tokens": usage_log.total_tokens,
            "created_at": usage_log.created_at,
        }

    def _record_execution(
        self,
        knowledge_base_id: int,
        result: AgentChatResult,
        assistant_message_id: int | None,
    ) -> None:
        if assistant_message_id is None:
            return
        self.agent_run_repository.create(
            conversation_id=result.conversation_id,
            knowledge_base_id=knowledge_base_id,
            assistant_message_id=assistant_message_id,
            intent=result.intent.value,
            steps=result.execution_steps,
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
                detail="会话不存在，或不属于当前知识库。",
            )
        return conversation
