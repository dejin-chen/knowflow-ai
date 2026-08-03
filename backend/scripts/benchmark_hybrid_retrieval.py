"""比较纯向量候选、BM25 + RRF 候选，以及可选的 LLM Rerank 结果。"""

import argparse
import json
from pathlib import Path
from statistics import mean
import sys

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
        description="比较纯向量召回与 BM25 + RRF 混合召回",
    )
    parser.add_argument("--knowledge-base-id", type=int, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--with-llm-rerank",
        action="store_true",
        help="对混合候选继续执行真实 LLM Rerank，会产生模型费用",
    )
    parser.add_argument(
        "--baseline-report",
        type=Path,
        default=None,
        help="可选：读取上一轮向量 + LLM 报告，计算端到端变化",
    )
    return parser.parse_args()


def load_dataset(path: Path) -> RetrievalEvaluationDataset:
    return RetrievalEvaluationDataset.model_validate(
        json.loads(path.read_text(encoding="utf-8"))
    )


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


def hit_rate(case_results: list[dict], key: str) -> float:
    return round(sum(result[key] for result in case_results) / len(case_results), 4)


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(int((len(ordered) - 1) * percentile_value), len(ordered) - 1)
    return round(ordered[index], 2)


def load_baseline_report(path: Path | None) -> dict | None:
    if path is None:
        return None
    raw_report = json.loads(path.read_text(encoding="utf-8"))
    return {
        "source": str(path),
        "total_cases": raw_report.get("total_cases"),
        "candidate_hit_rate": raw_report.get("candidate_hit_rate"),
        "llm_rerank": raw_report.get("llm_rerank"),
    }


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit < 1:
        print("错误：--limit 必须大于等于 1。", file=sys.stderr)
        return 2

    try:
        dataset = load_dataset(args.dataset)
        baseline_report = load_baseline_report(args.baseline_report)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        print(f"评估输入读取失败：{error}", file=sys.stderr)
        return 2

    cases = dataset.cases[: args.limit] if args.limit else dataset.cases
    case_results: list[dict] = []
    rerank_tokens: list[int] = []
    rerank_latencies: list[float] = []
    fallback_count = 0

    with SessionLocal() as db:
        search_service = SemanticSearchService(db)
        evaluation_service = RetrievalEvaluationService(search_service)
        rerank_service = LlmRerankService()
        search_service.knowledge_base_service.get_required_knowledge_base(
            args.knowledge_base_id
        )
        query_embeddings = search_service.embedding_service.embed_texts(
            [case.question for case in cases]
        )

        for index, (case, query_embedding) in enumerate(
            zip(cases, query_embeddings, strict=True),
            start=1,
        ):
            vector_candidates = search_service.retrieve_candidates_by_embedding(
                args.knowledge_base_id,
                query_embedding,
                case.top_k,
                validate_knowledge_base=False,
            )
            hybrid_candidates = (
                search_service.retrieve_hybrid_candidates_by_embedding(
                    args.knowledge_base_id,
                    case.question,
                    query_embedding,
                    case.top_k,
                    validate_knowledge_base=False,
                )
            )
            vector_top_k = evaluation_service.evaluate_chunks(
                case,
                vector_candidates[: case.top_k],
            )
            hybrid_top_k = evaluation_service.evaluate_chunks(
                case,
                hybrid_candidates[: case.top_k],
            )
            vector_candidate_result = evaluation_service.evaluate_chunks(
                case,
                vector_candidates,
            )
            hybrid_candidate_result = evaluation_service.evaluate_chunks(
                case,
                hybrid_candidates,
            )

            case_result = {
                "case_id": case.case_id,
                "question": case.question,
                "vector_candidate_hit": vector_candidate_result.hit,
                "hybrid_candidate_hit": hybrid_candidate_result.hit,
                "vector_hit": vector_top_k.hit,
                "vector_rank": vector_top_k.first_relevant_rank,
                "vector_reciprocal_rank": vector_top_k.reciprocal_rank,
                "vector_keyword_recall": vector_top_k.keyword_recall,
                "hybrid_hit": hybrid_top_k.hit,
                "hybrid_rank": hybrid_top_k.first_relevant_rank,
                "hybrid_reciprocal_rank": hybrid_top_k.reciprocal_rank,
                "hybrid_keyword_recall": hybrid_top_k.keyword_recall,
            }

            if args.with_llm_rerank:
                execution = rerank_service.rerank_with_metadata(
                    case.question,
                    hybrid_candidates,
                )
                llm_result = evaluation_service.evaluate_chunks(
                    case,
                    execution.chunks[: case.top_k],
                )
                usage = execution.model_usage
                if usage is not None:
                    rerank_tokens.append(usage.total_tokens)
                rerank_latencies.append(execution.latency_ms)
                fallback_count += int(execution.fallback_used)
                case_result.update(
                    {
                        "hybrid_llm_hit": llm_result.hit,
                        "hybrid_llm_rank": llm_result.first_relevant_rank,
                        "hybrid_llm_reciprocal_rank": llm_result.reciprocal_rank,
                        "hybrid_llm_keyword_recall": llm_result.keyword_recall,
                        "rerank_method": execution.method,
                        "rerank_total_tokens": usage.total_tokens if usage else 0,
                        "rerank_latency_ms": execution.latency_ms,
                    }
                )

            case_results.append(case_result)
            print(
                f"[{index}/{len(cases)}] {case.case_id}: "
                f"vector_candidate={vector_candidate_result.hit}, "
                f"hybrid_candidate={hybrid_candidate_result.hit}, "
                f"rrf_rank={hybrid_top_k.first_relevant_rank}"
            )

    vector_summary = summarize(case_results, "vector")
    hybrid_summary = summarize(case_results, "hybrid")
    vector_candidate_hit_rate = hit_rate(case_results, "vector_candidate_hit")
    hybrid_candidate_hit_rate = hit_rate(case_results, "hybrid_candidate_hit")
    report = {
        "report_name": "KnowFlow BM25 + RRF 混合召回对比报告",
        "dataset_name": dataset.name,
        "knowledge_base_id": args.knowledge_base_id,
        "total_cases": len(case_results),
        "config": {
            "embedding_model": settings.embedding_model,
            "bm25_top_k": settings.retrieval_bm25_top_k,
            "bm25_min_score": settings.retrieval_bm25_min_score,
            "rrf_k": settings.retrieval_rrf_k,
            "rrf_vector_weight": settings.retrieval_rrf_vector_weight,
            "rrf_bm25_weight": settings.retrieval_rrf_bm25_weight,
            "final_candidate_limit": settings.retrieval_rerank_max_candidates,
        },
        "vector_only": {
            "candidate_hit_rate": vector_candidate_hit_rate,
            **vector_summary,
        },
        "hybrid_rrf": {
            "candidate_hit_rate": hybrid_candidate_hit_rate,
            **hybrid_summary,
        },
        "retrieval_change": {
            "candidate_hit_rate_percentage_points": round(
                (hybrid_candidate_hit_rate - vector_candidate_hit_rate) * 100,
                2,
            ),
            "top_k_hit_rate_percentage_points": round(
                (
                    hybrid_summary["hit_rate_at_k"]
                    - vector_summary["hit_rate_at_k"]
                )
                * 100,
                2,
            ),
        },
        "previous_vector_llm_baseline": baseline_report,
        "cases": case_results,
    }

    if args.with_llm_rerank:
        llm_summary = summarize(case_results, "hybrid_llm")
        report["hybrid_llm_rerank"] = llm_summary
        report["llm_cost_and_latency"] = {
            "call_count": len(rerank_tokens),
            "fallback_count": fallback_count,
            "total_tokens": sum(rerank_tokens),
            "average_tokens": (
                round(mean(rerank_tokens), 2) if rerank_tokens else 0.0
            ),
            "average_latency_ms": round(mean(rerank_latencies), 2),
            "p95_latency_ms": percentile(rerank_latencies, 0.95),
        }
        if baseline_report and baseline_report.get("llm_rerank"):
            previous_llm = baseline_report["llm_rerank"]
            report["end_to_end_change"] = {
                "hit_rate_percentage_points": round(
                    (
                        llm_summary["hit_rate_at_k"]
                        - previous_llm["hit_rate_at_k"]
                    )
                    * 100,
                    2,
                ),
                "mrr_change": round(
                    llm_summary["mean_reciprocal_rank"]
                    - previous_llm["mean_reciprocal_rank"],
                    4,
                ),
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
        print(f"评估执行失败：{error.detail}", file=sys.stderr)
        raise SystemExit(1) from error
