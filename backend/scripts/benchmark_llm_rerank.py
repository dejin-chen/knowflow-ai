"""在同一批向量候选上比较原始排序与 LLM Rerank。"""

import argparse
import json
from pathlib import Path
from statistics import mean
import sys
from time import sleep

from fastapi import HTTPException
from pydantic import ValidationError


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.schemas.retrieval_evaluation import (  # noqa: E402
    RetrievalEvaluationDataset,
)
from app.services.llm_rerank_service import LlmRerankService  # noqa: E402
from app.services.retrieval_evaluation_service import (  # noqa: E402
    RetrievalEvaluationService,
)
from app.services.semantic_search_service import SemanticSearchService  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="比较纯向量排序与 LLM Rerank 的检索质量、Token 和延迟",
    )
    parser.add_argument("--knowledge-base-id", type=int, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep-ms", type=int, default=0)
    return parser.parse_args()


def load_dataset(path: Path) -> RetrievalEvaluationDataset:
    raw_data = json.loads(path.read_text(encoding="utf-8"))
    return RetrievalEvaluationDataset.model_validate(raw_data)


def summarize(case_results: list[dict], prefix: str) -> dict:
    total = len(case_results)
    return {
        "hit_rate_at_k": round(
            sum(result[f"{prefix}_hit"] for result in case_results) / total,
            4,
        ),
        "mean_reciprocal_rank": round(
            sum(result[f"{prefix}_reciprocal_rank"] for result in case_results)
            / total,
            4,
        ),
        "mean_keyword_recall": round(
            sum(result[f"{prefix}_keyword_recall"] for result in case_results)
            / total,
            4,
        ),
    }


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int((len(ordered) - 1) * percentile_value), len(ordered) - 1)
    return round(ordered[index], 2)


def relative_change(before: float, after: float) -> float | None:
    if before == 0:
        return None
    return round((after - before) / before, 4)


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        print("错误：--limit 必须大于等于 1。", file=sys.stderr)
        return 2
    if args.sleep_ms < 0:
        print("错误：--sleep-ms 不能小于 0。", file=sys.stderr)
        return 2
    try:
        dataset = load_dataset(args.dataset)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        print(f"评估集读取失败：{error}", file=sys.stderr)
        return 2

    cases = dataset.cases[: args.limit] if args.limit else dataset.cases
    case_results: list[dict] = []
    latencies: list[float] = []
    token_totals: list[int] = []
    fallback_count = 0

    with SessionLocal() as db:
        search_service = SemanticSearchService(db)
        evaluation_service = RetrievalEvaluationService(search_service)
        rerank_service = LlmRerankService()
        search_service.knowledge_base_service.get_required_knowledge_base(
            args.knowledge_base_id
        )
        # 离线评测批量生成问题向量，避免 100 道题产生 100 次独立网络请求。
        query_embeddings = search_service.embedding_service.embed_texts(
            [case.question for case in cases]
        )

        for index, (case, query_embedding) in enumerate(
            zip(cases, query_embeddings, strict=True),
            start=1,
        ):
            candidates = search_service.retrieve_candidates_by_embedding(
                args.knowledge_base_id,
                query_embedding,
                case.top_k,
                validate_knowledge_base=False,
            )
            baseline_chunks = candidates[: case.top_k]
            rerank_execution = rerank_service.rerank_with_metadata(
                case.question,
                candidates,
            )
            reranked_chunks = rerank_execution.chunks[: case.top_k]
            baseline_result = evaluation_service.evaluate_chunks(
                case,
                baseline_chunks,
            )
            rerank_result = evaluation_service.evaluate_chunks(
                case,
                reranked_chunks,
            )
            candidate_result = evaluation_service.evaluate_chunks(case, candidates)

            usage = rerank_execution.model_usage
            if usage is not None:
                token_totals.append(usage.total_tokens)
            latencies.append(rerank_execution.latency_ms)
            fallback_count += int(rerank_execution.fallback_used)
            case_results.append(
                {
                    "case_id": case.case_id,
                    "question": case.question,
                    "candidate_hit": candidate_result.hit,
                    "baseline_hit": baseline_result.hit,
                    "baseline_rank": baseline_result.first_relevant_rank,
                    "baseline_reciprocal_rank": baseline_result.reciprocal_rank,
                    "baseline_keyword_recall": baseline_result.keyword_recall,
                    "rerank_hit": rerank_result.hit,
                    "rerank_rank": rerank_result.first_relevant_rank,
                    "rerank_reciprocal_rank": rerank_result.reciprocal_rank,
                    "rerank_keyword_recall": rerank_result.keyword_recall,
                    "rerank_method": rerank_execution.method,
                    "rerank_latency_ms": rerank_execution.latency_ms,
                    "rerank_total_tokens": usage.total_tokens if usage else 0,
                    "fallback_reason": rerank_execution.fallback_reason,
                }
            )
            print(
                f"[{index}/{len(cases)}] {case.case_id}: "
                f"vector={baseline_result.first_relevant_rank}, "
                f"llm={rerank_result.first_relevant_rank}, "
                f"method={rerank_execution.method}"
            )
            if args.sleep_ms > 0:
                sleep(args.sleep_ms / 1000)

    baseline_summary = summarize(case_results, "baseline")
    rerank_summary = summarize(case_results, "rerank")
    report = {
        "report_name": "KnowFlow LLM Rerank 独立测试集对比报告",
        "dataset_name": dataset.name,
        "knowledge_base_id": args.knowledge_base_id,
        "total_cases": len(case_results),
        "config": {
            "embedding_model": settings.embedding_model,
            "rerank_model": settings.retrieval_rerank_model
            or settings.chat_model,
            "candidate_multiplier": settings.retrieval_candidate_multiplier,
            "max_candidates": settings.retrieval_rerank_max_candidates,
            "max_chunk_characters": (
                settings.retrieval_rerank_max_chunk_characters
            ),
        },
        "candidate_hit_rate": round(
            sum(result["candidate_hit"] for result in case_results)
            / len(case_results),
            4,
        ),
        "vector_baseline": baseline_summary,
        "llm_rerank": rerank_summary,
        "change": {
            "hit_rate_percentage_points": round(
                (rerank_summary["hit_rate_at_k"] - baseline_summary["hit_rate_at_k"])
                * 100,
                2,
            ),
            "hit_rate_relative": relative_change(
                baseline_summary["hit_rate_at_k"],
                rerank_summary["hit_rate_at_k"],
            ),
            "mrr_relative": relative_change(
                baseline_summary["mean_reciprocal_rank"],
                rerank_summary["mean_reciprocal_rank"],
            ),
            "keyword_recall_relative": relative_change(
                baseline_summary["mean_keyword_recall"],
                rerank_summary["mean_keyword_recall"],
            ),
        },
        "cost_and_latency": {
            "llm_call_count": len(token_totals),
            "fallback_count": fallback_count,
            "total_rerank_tokens": sum(token_totals),
            "average_rerank_tokens": (
                round(mean(token_totals), 2) if token_totals else 0.0
            ),
            "average_rerank_latency_ms": round(mean(latencies), 2),
            "p95_rerank_latency_ms": percentile(latencies, 0.95),
        },
        "cases": case_results,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    serialized_report = json.dumps(report, ensure_ascii=False, indent=2)
    args.output.write_text(serialized_report + "\n", encoding="utf-8")
    print(serialized_report)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except HTTPException as error:
        print(f"评测执行失败：{error.detail}", file=sys.stderr)
        raise SystemExit(1) from error
