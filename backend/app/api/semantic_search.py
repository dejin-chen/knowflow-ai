from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.semantic_search import RetrievedChunkRead, SemanticSearchRequest
from app.services.semantic_search_service import SemanticSearchService

router = APIRouter(prefix="/knowledge-bases", tags=["semantic_search"])


@router.post("/{knowledge_base_id}/search", response_model=list[RetrievedChunkRead])
def search_knowledge_base(
    knowledge_base_id: int,
    data: SemanticSearchRequest,
    db: Session = Depends(get_db),
):
    """按语义检索指定知识库，并返回可追溯的 Chunk 片段。"""
    results = SemanticSearchService(db).search(
        knowledge_base_id=knowledge_base_id,
        query=data.query,
        top_k=data.top_k,
    )
    return [RetrievedChunkRead(**result.__dict__) for result in results]
