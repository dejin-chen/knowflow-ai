from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.document import DocumentRead
from app.schemas.knowledge_base import KnowledgeBaseCreate, KnowledgeBaseRead
from app.services.document_service import DocumentService
from app.services.knowledge_base_service import KnowledgeBaseService

router = APIRouter(prefix="/knowledge-bases", tags=["knowledge_bases"])


@router.post(
    "",
    response_model=KnowledgeBaseRead,
    status_code=status.HTTP_201_CREATED,
)
def create_knowledge_base(
    data: KnowledgeBaseCreate,
    db: Session = Depends(get_db),
):
    service = KnowledgeBaseService(db)
    return service.create_knowledge_base(data)


@router.get("", response_model=list[KnowledgeBaseRead])
def list_knowledge_bases(db: Session = Depends(get_db)):
    service = KnowledgeBaseService(db)
    return service.list_knowledge_bases()


@router.delete("/{knowledge_base_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_base(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
):
    service = KnowledgeBaseService(db)
    service.delete_knowledge_base(knowledge_base_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{knowledge_base_id}/documents",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    knowledge_base_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    service = DocumentService(db)
    return await service.upload_document(knowledge_base_id, file)


@router.get("/{knowledge_base_id}/documents", response_model=list[DocumentRead])
def list_documents(
    knowledge_base_id: int,
    db: Session = Depends(get_db),
):
    service = DocumentService(db)
    return service.list_documents(knowledge_base_id)
