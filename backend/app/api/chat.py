from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.rag_cache import RagCacheClearRead, RagCacheStatsRead
from app.services.agent_chat_service import AgentChatService
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.rag_answer_cache_service import RagAnswerCacheService

router = APIRouter(prefix="/knowledge-bases", tags=["rag_chat"])


@router.post("/{knowledge_base_id}/chat", response_model=ChatResponse)
def chat_with_knowledge_base(
    knowledge_base_id: int,
    data: ChatRequest,
    db: Session = Depends(get_db),
):
    """基于指定知识库检索资料并生成带真实引用的回答。"""
    result = AgentChatService(db).ask(
        knowledge_base_id=knowledge_base_id,
        question=data.question,
        conversation_id=data.conversation_id,
        top_k=data.top_k,
    )
    return ChatResponse(**asdict(result))


@router.get("/{knowledge_base_id}/cache/stats", response_model=RagCacheStatsRead)
def get_rag_cache_stats(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
):
    """查看当前知识库的有效回答缓存与累计节省量。"""
    KnowledgeBaseService(db).get_required_knowledge_base(knowledge_base_id)
    return {
        "knowledge_base_id": knowledge_base_id,
        **RagAnswerCacheService(db).get_stats(knowledge_base_id),
    }


@router.delete("/{knowledge_base_id}/cache", response_model=RagCacheClearRead)
def clear_rag_answer_cache(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
):
    """手动清空知识库回答缓存，便于调试或配置变更后立即失效。"""
    KnowledgeBaseService(db).get_required_knowledge_base(knowledge_base_id)
    deleted_entry_count = RagAnswerCacheService(db).invalidate_knowledge_base(
        knowledge_base_id
    )
    return {
        "knowledge_base_id": knowledge_base_id,
        "deleted_entry_count": deleted_entry_count,
    }
