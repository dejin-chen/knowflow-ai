from dataclasses import dataclass

from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from app.core.config import settings
from app.repositories.document_chunk_repository import DocumentChunkRepository
from app.services.retrieval_tokenizer import RetrievalTokenizer


@dataclass(frozen=True)
class Bm25SearchMatch:
    chunk_id: int
    score: float
    rank: int


class Bm25RetrievalService:
    """从 SQLite Chunk 主数据构建临时 BM25 语料并执行关键词召回。"""

    def __init__(self, db: Session) -> None:
        self.chunk_repository = DocumentChunkRepository(db)

    def search(
        self,
        knowledge_base_id: int,
        query: str,
        top_k: int | None = None,
    ) -> list[Bm25SearchMatch]:
        rows = self.chunk_repository.list_with_document_by_knowledge_base(
            knowledge_base_id
        )
        query_tokens = RetrievalTokenizer.tokenize(query)
        if not rows or not query_tokens:
            return []

        corpus_tokens = [
            RetrievalTokenizer.tokenize(chunk.content)
            for chunk, _document in rows
        ]
        if not any(corpus_tokens):
            return []

        scores = BM25Okapi(corpus_tokens).get_scores(query_tokens)
        min_score = settings.retrieval_bm25_min_score
        scored_rows = [
            (float(score), position, chunk.id)
            for position, ((chunk, _document), score) in enumerate(
                zip(rows, scores, strict=True)
            )
            if float(score) > min_score
        ]
        scored_rows.sort(key=lambda item: (-item[0], item[1]))
        actual_top_k = top_k or settings.retrieval_bm25_top_k
        return [
            Bm25SearchMatch(
                chunk_id=chunk_id,
                score=round(score, 6),
                rank=rank,
            )
            for rank, (score, _position, chunk_id) in enumerate(
                scored_rows[:actual_top_k],
                start=1,
            )
        ]
