from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings


connect_args = {}
if settings.database_url.startswith("sqlite"):
    # SQLite 默认限制连接只能在创建它的线程中使用。
    # FastAPI 在测试和请求处理时可能跨线程访问，所以开发阶段需要关闭这个限制。
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    future=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖函数：为每个请求提供一个数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
