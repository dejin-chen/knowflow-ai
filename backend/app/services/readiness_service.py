from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.services.vector_store_service import ChromaVectorStoreService


class ReadinessService:
    """验证业务请求依赖的本地数据库和向量库是否可用。"""

    def __init__(
        self,
        db: Session,
        vector_store: ChromaVectorStoreService | None = None,
    ) -> None:
        self.db = db
        self.vector_store = vector_store or ChromaVectorStoreService()

    def check(self) -> dict:
        try:
            self.db.execute(text("SELECT 1"))
        except SQLAlchemyError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="数据库就绪检查失败",
            ) from error

        self.vector_store.heartbeat()
        return {
            "status": "ready",
            "checks": {
                "database": "ok",
                "vector_store": "ok",
            },
        }
