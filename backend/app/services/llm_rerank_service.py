from __future__ import annotations

from dataclasses import dataclass, replace
import json
import logging
from time import perf_counter
from typing import TYPE_CHECKING

from fastapi import HTTPException

from app.core.config import settings
from app.services.chat_completion_service import ChatCompletionResult, ChatCompletionService
from app.services.lightweight_rerank_service import LightweightRerankService
from app.services.rag_prompt_service import RagPrompt


if TYPE_CHECKING:
    from app.services.semantic_search_service import RetrievedChunk


logger = logging.getLogger(__name__)


class InvalidRerankResponseError(ValueError):
    """聊天模型没有按约定返回完整、合法的候选编号排序。"""


@dataclass(frozen=True)
class RerankExecutionResult:
    chunks: list[RetrievedChunk]
    model_usage: ChatCompletionResult | None
    method: str
    fallback_used: bool
    fallback_reason: str | None
    latency_ms: float


class LlmRerankService:
    """让聊天模型只对已召回候选排序，不允许生成新 Chunk。"""

    prompt_version = "v1"
    system_message = """你是企业知识库检索排序器。请判断每个候选片段与用户问题的相关性，按相关性从高到低排列。
你只能使用输入中已有的 chunk_id，不得新增或重复编号。优先列出最相关的编号；可以省略低相关编号，系统会按原顺序追加。只输出 JSON 对象，格式为：
{"ranked_chunk_ids":[整数编号1,整数编号2]}"""

    def __init__(
        self,
        completion_service: ChatCompletionService | None = None,
        fallback_service: LightweightRerankService | None = None,
    ) -> None:
        self.completion_service = completion_service or ChatCompletionService()
        self.fallback_service = fallback_service or LightweightRerankService()

    def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedChunk]:
        return self.rerank_with_metadata(query, chunks).chunks

    def rerank_with_metadata(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> RerankExecutionResult:
        if not chunks:
            return RerankExecutionResult(
                chunks=[],
                model_usage=None,
                method="llm",
                fallback_used=False,
                fallback_reason=None,
                latency_ms=0.0,
            )

        started_at = perf_counter()
        completion: ChatCompletionResult | None = None
        try:
            completion = self.completion_service.generate_completion(
                self._build_prompt(query, chunks),
                model_name=settings.retrieval_rerank_model or settings.chat_model,
                temperature=0.0,
            )
            ranked_chunk_ids = self._parse_ranked_chunk_ids(
                completion.answer,
                chunks,
            )
            chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
            ranked_chunks = [
                replace(
                    chunks_by_id[chunk_id],
                    rerank_score=None,
                    rerank_rank=rank,
                    rerank_method="llm",
                )
                for rank, chunk_id in enumerate(ranked_chunk_ids, start=1)
            ]
            return RerankExecutionResult(
                chunks=ranked_chunks,
                model_usage=completion,
                method="llm",
                fallback_used=False,
                fallback_reason=None,
                latency_ms=round((perf_counter() - started_at) * 1000, 2),
            )
        except (HTTPException, InvalidRerankResponseError) as error:
            reason = (
                str(error.detail)
                if isinstance(error, HTTPException)
                else str(error)
            )
            logger.warning("LLM Rerank 失败，降级为词法排序：%s", reason)
            fallback_chunks = [
                replace(chunk, rerank_method="lexical_fallback")
                for chunk in self.fallback_service.rerank(query, chunks)
            ]
            return RerankExecutionResult(
                chunks=fallback_chunks,
                # JSON 解析失败也已经产生模型费用，只有调用本身失败时才没有用量。
                model_usage=completion,
                method="lexical_fallback",
                fallback_used=True,
                fallback_reason=reason,
                latency_ms=round((perf_counter() - started_at) * 1000, 2),
            )

    def _build_prompt(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> RagPrompt:
        candidates = [
            {
                "chunk_id": chunk.chunk_id,
                "filename": chunk.filename,
                "chunk_index": chunk.chunk_index,
                "content": chunk.content[
                    : settings.retrieval_rerank_max_chunk_characters
                ],
            }
            for chunk in chunks
        ]
        return RagPrompt(
            system_message=self.system_message,
            user_message=(
                f"用户问题：{query}\n\n"
                "候选片段：\n"
                f"{json.dumps(candidates, ensure_ascii=False)}"
            ),
        )

    @classmethod
    def _parse_ranked_chunk_ids(
        cls,
        raw_answer: str,
        chunks: list[RetrievedChunk],
    ) -> list[int]:
        normalized_answer = cls._strip_markdown_fence(raw_answer)
        try:
            payload = json.loads(normalized_answer)
        except json.JSONDecodeError as error:
            raise InvalidRerankResponseError("返回内容不是合法 JSON") from error

        ranked_ids = payload.get("ranked_chunk_ids") if isinstance(payload, dict) else None
        if not isinstance(ranked_ids, list):
            raise InvalidRerankResponseError("缺少 ranked_chunk_ids 数组")

        normalized_ids: list[int] = []
        for chunk_id in ranked_ids:
            if isinstance(chunk_id, bool):
                raise InvalidRerankResponseError("候选编号必须是整数")
            if isinstance(chunk_id, int):
                normalized_ids.append(chunk_id)
                continue
            if isinstance(chunk_id, str) and chunk_id.strip().lstrip("-").isdigit():
                normalized_ids.append(int(chunk_id))
                continue
            raise InvalidRerankResponseError("候选编号必须是整数")

        expected_ids = [chunk.chunk_id for chunk in chunks]
        if len(normalized_ids) != len(set(normalized_ids)):
            raise InvalidRerankResponseError("排序结果包含重复候选编号")
        if not normalized_ids:
            raise InvalidRerankResponseError("排序结果没有包含任何候选编号")
        unknown_ids = set(normalized_ids) - set(expected_ids)
        if unknown_ids:
            raise InvalidRerankResponseError("排序结果包含未知候选编号")

        # LLM 可以只返回最相关的一部分；未提及候选继续沿用稳定的向量顺序。
        return normalized_ids + [
            chunk_id for chunk_id in expected_ids if chunk_id not in normalized_ids
        ]

    @staticmethod
    def _strip_markdown_fence(answer: str) -> str:
        stripped = answer.strip()
        if not stripped.startswith("```"):
            return stripped
        lines = stripped.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            return "\n".join(lines[1:-1]).strip()
        return stripped
