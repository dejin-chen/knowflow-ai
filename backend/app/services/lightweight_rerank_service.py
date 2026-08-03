from __future__ import annotations

from dataclasses import replace
import re
from typing import TYPE_CHECKING

from app.core.config import settings


if TYPE_CHECKING:
    from app.services.semantic_search_service import RetrievedChunk


class LightweightRerankService:
    """使用轻量词法覆盖率重新排列向量召回候选，不产生额外模型调用。"""

    token_pattern = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        query_features = self._extract_features(query)
        scored_chunks: list[tuple[float, int, RetrievedChunk]] = []

        for original_rank, chunk in enumerate(chunks):
            lexical_score = self._lexical_recall(
                query_features,
                self._extract_features(chunk.content),
            )
            # cosine distance 越小越好，先转换成 0~1 的语义分数再与词法分数融合。
            semantic_score = min(max(1.0 - chunk.distance, 0.0), 1.0)
            lexical_weight = settings.retrieval_rerank_lexical_weight
            rerank_score = (
                (1.0 - lexical_weight) * semantic_score
                + lexical_weight * lexical_score
            )
            scored_chunks.append(
                (
                    rerank_score,
                    original_rank,
                    replace(chunk, rerank_score=round(rerank_score, 6)),
                )
            )

        # 分数相同时保持原始向量排序，避免无词法信号时发生无意义抖动。
        scored_chunks.sort(key=lambda item: (-item[0], item[1]))
        return [item[2] for item in scored_chunks]

    @classmethod
    def _extract_features(cls, text: str) -> set[str]:
        features: set[str] = set()
        for token in cls.token_pattern.findall(text.casefold()):
            if cls._is_chinese(token[0]):
                if len(token) == 1:
                    features.add(token)
                else:
                    features.update(
                        token[index : index + 2]
                        for index in range(len(token) - 1)
                    )
            else:
                features.add(token)
        return features

    @staticmethod
    def _lexical_recall(
        query_features: set[str],
        content_features: set[str],
    ) -> float:
        if not query_features:
            return 0.0
        return len(query_features & content_features) / len(query_features)

    @staticmethod
    def _is_chinese(character: str) -> bool:
        return "\u4e00" <= character <= "\u9fff"
