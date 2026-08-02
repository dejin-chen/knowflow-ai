from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.health import ReadinessResponse
from app.services.readiness_service import ReadinessService

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, str]:
    """健康检查接口，用于确认后端服务是否正常启动。"""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.app_env,
    }


@router.get("/health/ready", response_model=ReadinessResponse)
def readiness_check(db: Session = Depends(get_db)):
    """确认 SQLite 与 Chroma 可用；不依赖外部模型服务。"""
    return ReadinessService(db).check()
