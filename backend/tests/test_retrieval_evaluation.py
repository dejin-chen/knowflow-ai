"""Retrieval evaluation metric tests."""

from app.schemas.retrieval_evaluation import RetrievalEvaluationDataset
from app.services.retrieval_evaluation_service import RetrievalEvaluationService
from app.services.semantic_search_service import RetrievedChunk


def make_chunk(filename: str, content: str, chunk_id: int) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=1,
        knowledge_base_id=7,
        filename=filename,
        chunk_index=chunk_id,
        content=content,
        distance=0.1,
    )


class FakeSearchService:
    def __init__(self, results_by_question: dict[str, list[RetrievedChunk]]) -> None:
        self.results_by_question = results_by_question
        self.calls: list[tuple[int, str, int]] = []

    def search(
        self, knowledge_base_id: int, query: str, top_k: int
    ) -> list[RetrievedChunk]:
        self.calls.append((knowledge_base_id, query, top_k))
        return self.results_by_question[query][:top_k]


def test_evaluation_calculates_hit_rate_mrr_and_keyword_recall() -> None:
    dataset = RetrievalEvaluationDataset.model_validate(
        {
            "name": "测试集",
            "cases": [
                {
                    "case_id": "case-1",
                    "question": "病假材料",
                    "expected_filenames": ["员工手册.md"],
                    "expected_keywords": ["证明原件", "电子材料"],
                    "top_k": 3,
                },
                {
                    "case_id": "case-2",
                    "question": "采购审批",
                    "expected_filenames": ["采购制度.md"],
                    "expected_keywords": ["采购委员会"],
                    "top_k": 2,
                },
            ],
        }
    )
    fake_search = FakeSearchService(
        {
            "病假材料": [
                make_chunk("其他制度.md", "无关内容", 1),
                make_chunk("员工手册.md", "提交证明原件", 2),
                make_chunk("员工手册.md", "电子材料也可以", 3),
            ],
            "采购审批": [make_chunk("采购制度.md", "由财务审批", 4)],
        }
    )

    report = RetrievalEvaluationService(fake_search).evaluate(7, dataset)

    assert report.hit_rate_at_k == 0.5
    assert report.mean_reciprocal_rank == 0.25
    assert report.mean_keyword_recall == 0.5
    assert report.average_retrieved_chunks == 2.0
    assert report.cases[0].first_relevant_rank == 2
    assert report.cases[0].keyword_recall == 1.0
    assert fake_search.calls == [(7, "病假材料", 3), (7, "采购审批", 2)]


def test_evaluation_accepts_expected_source_without_keywords() -> None:
    dataset = RetrievalEvaluationDataset.model_validate(
        {
            "name": "仅来源标注",
            "cases": [
                {
                    "case_id": "case-1",
                    "question": "制度是什么",
                    "expected_filenames": ["制度.md"],
                }
            ],
        }
    )
    fake_search = FakeSearchService(
        {"制度是什么": [make_chunk("制度.md", "任意正文", 1)]}
    )

    report = RetrievalEvaluationService(fake_search).evaluate(7, dataset)

    assert report.hit_rate_at_k == 1.0
    assert report.mean_reciprocal_rank == 1.0
    assert report.mean_keyword_recall == 1.0
