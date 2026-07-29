from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.vector_index import DocumentIndexRead
from app.services.document_vector_index_service import DocumentVectorIndexService

router = APIRouter(prefix="/documents", tags=["vector_indexes"])


@router.post(
    "/{document_id}/index",
    response_model=DocumentIndexRead,
    status_code=status.HTTP_201_CREATED,
)
def index_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    """为已经切分的文档生成 Embedding 并写入 Chroma。"""
    result = DocumentVectorIndexService(db).index_document(document_id)
    return DocumentIndexRead(**result.__dict__)
