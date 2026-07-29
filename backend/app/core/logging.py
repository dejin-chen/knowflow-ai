import logging
import sys

from app.core.config import settings


def setup_logging() -> None:
    """配置统一日志格式。

    第一阶段先使用标准库 logging。后续如果要接入可观测性平台，
    可以在这里扩展 JSON 日志、trace_id 或请求链路信息。
    """
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
