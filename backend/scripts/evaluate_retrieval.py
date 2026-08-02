"""从命令行运行 KnowFlow AI 离线检索评估。"""

import argparse
import json
from pathlib import Path
import sys

from fastapi import HTTPException
from pydantic import ValidationError


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal  # noqa: E402
from app.schemas.retrieval_evaluation import RetrievalEvaluationDataset  # noqa: E402
from app.services.retrieval_evaluation_service import (  # noqa: E402
    RetrievalEvaluationService,
)
from app.services.semantic_search_service import SemanticSearchService  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="评估知识库语义检索质量")
    parser.add_argument("--knowledge-base-id", type=int, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--min-hit-rate",
        type=float,
        default=None,
        help="可选质量门槛，低于该命中率时返回非零退出码",
    )
    return parser.parse_args()


def load_dataset(path: Path) -> RetrievalEvaluationDataset:
    raw_data = json.loads(path.read_text(encoding="utf-8"))
    return RetrievalEvaluationDataset.model_validate(raw_data)


def main() -> int:
    args = parse_args()
    if args.min_hit_rate is not None and not 0 <= args.min_hit_rate <= 1:
        print("错误：--min-hit-rate 必须在 0 到 1 之间。", file=sys.stderr)
        return 2

    try:
        dataset = load_dataset(args.dataset)
        with SessionLocal() as db:
            report = RetrievalEvaluationService(
                SemanticSearchService(db)
            ).evaluate(args.knowledge_base_id, dataset)
    except (OSError, json.JSONDecodeError, ValidationError) as exc:
        print(f"评估集读取失败：{exc}", file=sys.stderr)
        return 2
    except HTTPException as exc:
        print(f"评估执行失败：{exc.detail}", file=sys.stderr)
        return 1

    print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
    if args.min_hit_rate is not None and report.hit_rate_at_k < args.min_hit_rate:
        print(
            f"检索命中率 {report.hit_rate_at_k:.4f} 低于门槛 "
            f"{args.min_hit_rate:.4f}。",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
