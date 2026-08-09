import logging
import sys

from app.core.config import settings


def setup_logging() -> None:
    """配置统一日志格式。

    当前使用标准库 logging 输出统一格式；接入集中式可观测平台时，
    可在此扩展 JSON 日志、trace_id 和分布式链路字段。
    """
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
