from collections.abc import Iterable

from app.schemas.retrieval_evaluation import (
    RetrievalEvaluationCase,
    RetrievalEvaluationCaseResult,
    RetrievalEvaluationDataset,
    RetrievalEvaluationReport,
)
from app.services.semantic_search_service import RetrievedChunk, SemanticSearchService


class RetrievalEvaluationService:
    """使用人工标注题目，离线衡量知识库的检索质量。"""

    def __init__(self, search_service: SemanticSearchService) -> None:
        self.search_service = search_service

    def evaluate(
        self,
        knowledge_base_id: int,
        dataset: RetrievalEvaluationDataset,
    ) -> RetrievalEvaluationReport:
        case_results = [
            self._evaluate_case(knowledge_base_id, case) for case in dataset.cases
        ]
        total_cases = len(case_results)

        # Hit Rate 关注“是否找到”，MRR 还会奖励正确证据出现在更靠前的位置。
        return RetrievalEvaluationReport(
            dataset_name=dataset.name,
            knowledge_base_id=knowledge_base_id,
            total_cases=total_cases,
            hit_rate_at_k=self._average(float(result.hit) for result in case_results),
            mean_reciprocal_rank=self._average(
                result.reciprocal_rank for result in case_results
            ),
            mean_keyword_recall=self._average(
                result.keyword_recall for result in case_results
            ),
            average_retrieved_chunks=self._average(
                float(result.retrieved_count) for result in case_results
            ),
            cases=case_results,
        )

    def _evaluate_case(
        self,
        knowledge_base_id: int,
        case: RetrievalEvaluationCase,
    ) -> RetrievalEvaluationCaseResult:
        retrieved_chunks = self.search_service.search(
            knowledge_base_id=knowledge_base_id,
            query=case.question,
            top_k=case.top_k,
        )
        first_relevant_rank = self._first_relevant_rank(case, retrieved_chunks)
        keyword_recall = self._keyword_recall(case, retrieved_chunks)

        return RetrievalEvaluationCaseResult(
            case_id=case.case_id,
            question=case.question,
            hit=first_relevant_rank is not None,
            first_relevant_rank=first_relevant_rank,
            reciprocal_rank=(
                1 / first_relevant_rank if first_relevant_rank is not None else 0.0
            ),
            keyword_recall=keyword_recall,
            retrieved_count=len(retrieved_chunks),
            retrieved_filenames=[chunk.filename for chunk in retrieved_chunks],
        )

    def _first_relevant_rank(
        self,
        case: RetrievalEvaluationCase,
        chunks: list[RetrievedChunk],
    ) -> int | None:
        for rank, chunk in enumerate(chunks, start=1):
            if self._is_relevant(case, chunk):
                return rank
        return None

    def _is_relevant(
        self,
        case: RetrievalEvaluationCase,
        chunk: RetrievedChunk,
    ) -> bool:
        expected_filenames = {
            self._normalize(filename) for filename in case.expected_filenames
        }
        if self._normalize(chunk.filename) not in expected_filenames:
            return False
        if not case.expected_keywords:
            return True

        content = self._normalize(chunk.content)
        return any(
            self._normalize(keyword) in content for keyword in case.expected_keywords
        )

    def _keyword_recall(
        self,
        case: RetrievalEvaluationCase,
        chunks: list[RetrievedChunk],
    ) -> float:
        if not case.expected_keywords:
            return float(any(self._is_relevant(case, chunk) for chunk in chunks))

        expected_filenames = {
            self._normalize(filename) for filename in case.expected_filenames
        }
        relevant_source_text = " ".join(
            self._normalize(chunk.content)
            for chunk in chunks
            if self._normalize(chunk.filename) in expected_filenames
        )
        matched_keywords = sum(
            self._normalize(keyword) in relevant_source_text
            for keyword in case.expected_keywords
        )
        return matched_keywords / len(case.expected_keywords)

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split()).casefold()

    @staticmethod
    def _average(values: Iterable[float]) -> float:
        collected_values = list(values)
        return round(sum(collected_values) / len(collected_values), 4)
