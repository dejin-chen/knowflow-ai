from dataclasses import dataclass

from app.core.config import settings
from app.services.bm25_retrieval_service import Bm25SearchMatch


@dataclass(frozen=True)
class RrfFusionMatch:
    chunk_id: int
    score: float
    rank: int
    vector_rank: int | None
    bm25_rank: int | None
    bm25_score: float | None


class RrfFusionService:
    """只根据两路排名执行加权 RRF，避免直接混合不同量纲的分数。"""

    def fuse(
        self,
        vector_chunk_ids: list[int],
        bm25_matches: list[Bm25SearchMatch],
        limit: int,
    ) -> list[RrfFusionMatch]:
        candidates: dict[int, dict[str, float | int | None]] = {}

        for rank, chunk_id in enumerate(vector_chunk_ids, start=1):
            candidate = candidates.setdefault(
                chunk_id,
                self._empty_candidate(chunk_id),
            )
            candidate["vector_rank"] = rank
            candidate["score"] = float(candidate["score"]) + (
                settings.retrieval_rrf_vector_weight
                / (settings.retrieval_rrf_k + rank)
            )

        for match in bm25_matches:
            candidate = candidates.setdefault(
                match.chunk_id,
                self._empty_candidate(match.chunk_id),
            )
            candidate["bm25_rank"] = match.rank
            candidate["bm25_score"] = match.score
            candidate["score"] = float(candidate["score"]) + (
                settings.retrieval_rrf_bm25_weight
                / (settings.retrieval_rrf_k + match.rank)
            )

        ordered = sorted(
            candidates.values(),
            key=lambda item: (
                -float(item["score"]),
                min(
                    int(item["vector_rank"] or 10**9),
                    int(item["bm25_rank"] or 10**9),
                ),
                int(item["chunk_id"]),
            ),
        )
        return [
            RrfFusionMatch(
                chunk_id=int(candidate["chunk_id"]),
                score=round(float(candidate["score"]), 8),
                rank=rank,
                vector_rank=(
                    int(candidate["vector_rank"])
                    if candidate["vector_rank"] is not None
                    else None
                ),
                bm25_rank=(
                    int(candidate["bm25_rank"])
                    if candidate["bm25_rank"] is not None
                    else None
                ),
                bm25_score=(
                    float(candidate["bm25_score"])
                    if candidate["bm25_score"] is not None
                    else None
                ),
            )
            for rank, candidate in enumerate(ordered[:limit], start=1)
        ]

    @staticmethod
    def _empty_candidate(chunk_id: int) -> dict[str, float | int | None]:
        return {
            "chunk_id": chunk_id,
            "score": 0.0,
            "vector_rank": None,
            "bm25_rank": None,
            "bm25_score": None,
        }
