from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.models
from app.db.base import Base
from app.schemas.feedback import AnswerFeedbackCreate, FeedbackType
from app.schemas.knowledge_base import KnowledgeBaseCreate
from app.services.agent_chat_service import AgentChatService
from app.services.answer_feedback_service import AnswerFeedbackService
from app.services.conversation_service import ConversationService
from app.services.knowledge_base_service import KnowledgeBaseService


def build_database():
    engine = create_engine("sqlite:///:memory:", future=True)
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    return testing_session()


def test_feedback_is_saved_once_and_returned_in_history() -> None:
    db = build_database()
    try:
        knowledge_base = KnowledgeBaseService(db).create_knowledge_base(
            KnowledgeBaseCreate(name="回答反馈测试库")
        )
        chat_result = AgentChatService(db).ask(
            knowledge_base_id=knowledge_base.id,
            question="请总结这份制度",
            conversation_id=None,
            top_k=3,
        )
        feedback_service = AnswerFeedbackService(db)
        payload = AnswerFeedbackCreate(feedback_type=FeedbackType.HELPFUL)

        first_submission = feedback_service.submit_feedback(
            chat_result.assistant_message_id,
            payload,
        )
        repeated_submission = feedback_service.submit_feedback(
            chat_result.assistant_message_id,
            payload,
        )
        history = ConversationService(db).list_messages(chat_result.conversation_id)

        assert first_submission.created is True
        assert repeated_submission.created is False
        assert history[1]["feedback"].feedback_type == FeedbackType.HELPFUL
    finally:
        db.close()
