from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.agent_chat_service import AgentChatService

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
