"""Structured LLM rerank and fallback tests."""

from fastapi import HTTPException, status

from app.core.config import settings
from app.services.chat_completion_service import ChatCompletionResult
from app.services.llm_rerank_service import LlmRerankService
from app.services.semantic_search_service import RetrievedChunk


def make_chunk(chunk_id: int, content: str, distance: float) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=1,
        knowledge_base_id=1,
        filename="员工手册.md",
        chunk_index=chunk_id,
        content=content,
        distance=distance,
        vector_rank=chunk_id,
    )


class FakeCompletionService:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.received_prompt = None
        self.received_options = None

    def generate_completion(self, prompt, **options) -> ChatCompletionResult:
        self.received_prompt = prompt
        self.received_options = options
        return ChatCompletionResult(
            answer=self.answer,
            model_name="rerank-test-model",
            prompt_tokens=30,
            completion_tokens=5,
            total_tokens=35,
        )


class FailingCompletionService:
    def generate_completion(self, prompt, **options) -> ChatCompletionResult:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="测试模型不可用",
        )


def test_llm_reranker_uses_only_returned_chunk_id_order(monkeypatch) -> None:
    monkeypatch.setattr(settings, "retrieval_rerank_model", "cheap-rerank-model")
    chunks = [
        make_chunk(1, "普通考勤规则。", 0.1),
        make_chunk(2, "设备遗失后通知行政和信息安全部门。", 0.4),
        make_chunk(3, "费用报销应提供发票。", 0.2),
    ]
    completion_service = FakeCompletionService(
        '{"ranked_chunk_ids":[2,3,1]}'
    )

    result = LlmRerankService(
        completion_service=completion_service
    ).rerank_with_metadata("设备丢失通知谁？", chunks)

    assert [chunk.chunk_id for chunk in result.chunks] == [2, 3, 1]
    assert [chunk.rerank_rank for chunk in result.chunks] == [1, 2, 3]
    assert all(chunk.rerank_method == "llm" for chunk in result.chunks)
    assert result.model_usage.total_tokens == 35
    assert result.fallback_used is False
    assert completion_service.received_options == {
        "model_name": "cheap-rerank-model",
        "temperature": 0.0,
    }
    assert '"chunk_id": 2' in completion_service.received_prompt.user_message


def test_llm_reranker_accepts_json_markdown_fence() -> None:
    chunks = [
        make_chunk(1, "片段一", 0.1),
        make_chunk(2, "片段二", 0.2),
    ]
    completion_service = FakeCompletionService(
        '```json\n{"ranked_chunk_ids":[2,1]}\n```'
    )

    results = LlmRerankService(
        completion_service=completion_service
    ).rerank("问题", chunks)

    assert [chunk.chunk_id for chunk in results] == [2, 1]


def test_invalid_llm_order_falls_back_to_lexical_rerank(monkeypatch) -> None:
    monkeypatch.setattr(settings, "retrieval_rerank_lexical_weight", 1.0)
    chunks = [
        make_chunk(1, "普通考勤规则。", 0.1),
        make_chunk(2, "设备遗失后通知行政和信息安全部门。", 0.5),
    ]
    completion_service = FakeCompletionService(
        '{"ranked_chunk_ids":[2,999]}'
    )

    result = LlmRerankService(
        completion_service=completion_service
    ).rerank_with_metadata("设备遗失后通知哪些部门？", chunks)

    assert [chunk.chunk_id for chunk in result.chunks] == [2, 1]
    assert all(chunk.rerank_method == "lexical_fallback" for chunk in result.chunks)
    assert result.model_usage.total_tokens == 35
    assert result.fallback_used is True
    assert "未知候选编号" in result.fallback_reason


def test_partial_llm_order_appends_omitted_chunks_in_vector_order() -> None:
    chunks = [
        make_chunk(1, "片段一", 0.1),
        make_chunk(2, "片段二", 0.2),
        make_chunk(3, "片段三", 0.3),
    ]
    completion_service = FakeCompletionService(
        '{"ranked_chunk_ids":[3]}'
    )

    result = LlmRerankService(
        completion_service=completion_service
    ).rerank_with_metadata("问题", chunks)

    assert [chunk.chunk_id for chunk in result.chunks] == [3, 1, 2]
    assert result.fallback_used is False


def test_boolean_chunk_id_is_rejected_and_falls_back(monkeypatch) -> None:
    monkeypatch.setattr(settings, "retrieval_rerank_lexical_weight", 1.0)
    chunks = [
        make_chunk(1, "普通考勤规则。", 0.1),
        make_chunk(2, "病假需要诊断证明。", 0.4),
    ]
    completion_service = FakeCompletionService(
        '{"ranked_chunk_ids":[true,2]}'
    )

    result = LlmRerankService(
        completion_service=completion_service
    ).rerank_with_metadata("病假要什么证明？", chunks)

    assert result.fallback_used is True
    assert result.fallback_reason == "候选编号必须是整数"


def test_llm_outage_does_not_block_retrieval(monkeypatch) -> None:
    monkeypatch.setattr(settings, "retrieval_rerank_lexical_weight", 1.0)
    chunks = [
        make_chunk(1, "普通考勤规则。", 0.1),
        make_chunk(2, "病假需要诊断证明。", 0.4),
    ]

    result = LlmRerankService(
        completion_service=FailingCompletionService()
    ).rerank_with_metadata("病假要什么证明？", chunks)

    assert [chunk.chunk_id for chunk in result.chunks] == [2, 1]
    assert result.method == "lexical_fallback"
    assert result.fallback_used is True
    assert result.model_usage is None
