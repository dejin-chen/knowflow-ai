import logging
import re
from time import perf_counter
from uuid import uuid4

from fastapi import Request, Response


logger = logging.getLogger("app.request")
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def resolve_request_id(candidate: str | None) -> str:
    """只透传格式安全的请求 ID，异常值由服务端重新生成。"""
    normalized = (candidate or "").strip()
    if REQUEST_ID_PATTERN.fullmatch(normalized):
        return normalized
    return uuid4().hex


async def request_observability_middleware(request: Request, call_next) -> Response:
    request_id = resolve_request_id(request.headers.get("X-Request-ID"))
    request.state.request_id = request_id
    started_at = perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (perf_counter() - started_at) * 1000
        logger.exception(
            "request_failed request_id=%s method=%s path=%s duration_ms=%.2f",
            request_id,
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = (perf_counter() - started_at) * 1000
    response.headers["X-Request-ID"] = request_id
    logger.info(
        "request_completed request_id=%s method=%s path=%s status=%s duration_ms=%.2f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response
