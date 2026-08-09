from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.documents import router as document_router
from app.api.feedback import router as feedback_router
from app.api.chat import router as chat_router
from app.api.conversations import router as conversation_router
from app.api.knowledge_bases import router as knowledge_base_router
from app.api.semantic_search import router as semantic_search_router
from app.api.vector_indexes import router as vector_index_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.request_observability import request_observability_middleware
from app.db.base import Base
from app.db.session import engine
from app import models

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """初始化数据表、日志配置并管理应用生命周期。"""
    setup_logging()
    Base.metadata.create_all(bind=engine)
    logger.info("%s started", settings.app_name)
    yield
    logger.info("%s stopped", settings.app_name)


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例，方便测试复用。"""
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.middleware("http")(request_observability_middleware)
    app.include_router(health_router, prefix=settings.api_prefix)
    app.include_router(knowledge_base_router, prefix=settings.api_prefix)
    app.include_router(document_router, prefix=settings.api_prefix)
    app.include_router(vector_index_router, prefix=settings.api_prefix)
    app.include_router(semantic_search_router, prefix=settings.api_prefix)
    app.include_router(chat_router, prefix=settings.api_prefix)
    app.include_router(conversation_router, prefix=settings.api_prefix)
    app.include_router(feedback_router, prefix=settings.api_prefix)
    return app


app = create_app()
