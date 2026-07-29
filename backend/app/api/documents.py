from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.document_chunk import DocumentChunkProcessRead, DocumentChunkRead
from app.services.document_chunk_service import DocumentChunkService
from app.schemas.document_summary import DocumentSummaryRead
from app.services.document_summary_service import DocumentSummaryService
from app.schemas.document_faq import DocumentFaqRead
from app.services.document_faq_service import DocumentFaqService

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post(
    "/{document_id}/chunks",
    response_model=DocumentChunkProcessRead,
    status_code=status.HTTP_201_CREATED,
)
def process_document_chunks(
    document_id: int,
    db: Session = Depends(get_db),
):
    """解析并切分指定文档；重复调用会替换旧的切分结果。"""
    service = DocumentChunkService(db)
    chunks = service.process_document(document_id)
    return DocumentChunkProcessRead(
        document_id=document_id,
        status="chunked",
        chunk_count=len(chunks),
    )


@router.get("/{document_id}/chunks", response_model=list[DocumentChunkRead])
def list_document_chunks(
    document_id: int,
    db: Session = Depends(get_db),
):
    service = DocumentChunkService(db)
    return service.list_chunks(document_id)


@router.get("/{document_id}/summary", response_model=DocumentSummaryRead)
def get_document_summary(
    document_id: int,
    db: Session = Depends(get_db),
):
    return DocumentSummaryService(db).get_summary(document_id)


@router.post("/{document_id}/summary", response_model=DocumentSummaryRead)
def generate_document_summary(
    document_id: int,
    db: Session = Depends(get_db),
):
    return DocumentSummaryService(db).generate_summary(document_id)


@router.get("/{document_id}/faqs", response_model=list[DocumentFaqRead])
def list_document_faqs(
    document_id: int,
    db: Session = Depends(get_db),
):
    return DocumentFaqService(db).list_faqs(document_id)


@router.post("/{document_id}/faqs", response_model=list[DocumentFaqRead])
def generate_document_faqs(
    document_id: int,
    db: Session = Depends(get_db),
):
    return DocumentFaqService(db).generate_faqs(document_id)
