from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.conversation import ConversationRead, MessageRead
from app.services.conversation_service import ConversationService

router = APIRouter(tags=["conversations"])


@router.get(
    "/knowledge-bases/{knowledge_base_id}/conversations",
    response_model=list[ConversationRead],
)
def list_conversations(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
):
    return ConversationService(db).list_conversations(knowledge_base_id)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageRead])
def list_conversation_messages(
    conversation_id: int,
    db: Session = Depends(get_db),
):
    return ConversationService(db).list_messages(conversation_id)
