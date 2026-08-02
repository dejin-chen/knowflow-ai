from pydantic import BaseModel, Field, field_validator


class RetrievalEvaluationCase(BaseModel):
    """一条检索评估题目及其人工标注的预期证据。"""

    case_id: str = Field(min_length=1, max_length=100)
    question: str = Field(min_length=1, max_length=1000)
    expected_filenames: list[str] = Field(min_length=1)
    expected_keywords: list[str] = Field(default_factory=list)
    top_k: int = Field(default=3, ge=1, le=10)

    @field_validator("case_id", "question")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("字段不能为空")
        return normalized

    @field_validator("expected_filenames", "expected_keywords")
    @classmethod
    def normalize_expected_values(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(normalized) != len(values):
            raise ValueError("预期文件名和关键词不能包含空字符串")
        return normalized


class RetrievalEvaluationDataset(BaseModel):
    """可重复运行的检索评估数据集。"""

    name: str = Field(min_length=1, max_length=200)
    cases: list[RetrievalEvaluationCase] = Field(min_length=1)


class RetrievalEvaluationCaseResult(BaseModel):
    case_id: str
    question: str
    hit: bool
    first_relevant_rank: int | None
    reciprocal_rank: float
    keyword_recall: float
    retrieved_count: int
    retrieved_filenames: list[str]


class RetrievalEvaluationReport(BaseModel):
    dataset_name: str
    knowledge_base_id: int
    total_cases: int
    hit_rate_at_k: float
    mean_reciprocal_rank: float
    mean_keyword_recall: float
    average_retrieved_chunks: float
    cases: list[RetrievalEvaluationCaseResult]
