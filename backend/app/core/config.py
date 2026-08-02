from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """项目统一配置。

    所有可能随环境变化的值都放在这里，后续切换模型、数据库或部署环境时，
    不需要到业务代码里到处修改。
    """

    app_name: str = "KnowFlow AI"
    app_env: str = "development"
    app_version: str = "0.1.0"
    api_prefix: str = "/api"
    log_level: str = "INFO"

    database_url: str = "sqlite:///./knowflow.db"
    upload_dir: str = "./uploads"
    max_upload_size_mb: int = Field(default=10, ge=1, le=100)
    upload_read_chunk_size: int = Field(default=1024 * 1024, ge=1024)
    chunk_size: int = 500
    chunk_overlap: int = 80

    openai_api_key: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices("OPENAI_API_KEY", "EMBED_API_KEY"),
    )
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices("OPENAI_BASE_URL", "EMBED_BASE_URL"),
    )
    chat_api_key: str | None = Field(
        default=None,
        repr=False,
        validation_alias=AliasChoices(
            "CHAT_API_KEY",
            "DEEPSEEK_API_KEY",
            "OPENAI_API_KEY",
        ),
    )
    chat_base_url: str = Field(
        default="https://api.openai.com/v1",
        validation_alias=AliasChoices(
            "CHAT_BASE_URL",
            "DEEPSEEK_BASE_URL",
            "OPENAI_BASE_URL",
        ),
    )
    chat_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("CHAT_MODEL", "DEEPSEEK_MODEL"),
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        validation_alias=AliasChoices("EMBEDDING_MODEL", "EMBED_MODEL_NAME"),
    )

    chroma_persist_dir: str = "./chroma_db"
    chroma_collection_name: str = "knowflow_chunks"
    embedding_batch_size: int = 32
    model_request_timeout_seconds: float = Field(default=30.0, ge=5.0, le=120.0)
    model_max_retries: int = Field(default=1, ge=0, le=5)
    retrieval_top_k: int = 3
    retrieval_candidate_multiplier: int = Field(default=3, ge=1, le=10)
    retrieval_distance_threshold: float = 0.6
    rag_answer_cache_enabled: bool = True
    rag_answer_cache_ttl_seconds: int = Field(default=3600, ge=60, le=604800)
    rag_answer_cache_version: str = Field(default="v1", min_length=1, max_length=50)
    rag_answer_cache_max_entries: int = Field(default=2000, ge=1, le=100000)
    rag_answer_cache_max_entries_per_kb: int = Field(
        default=500,
        ge=1,
        le=10000,
    )
    agent_tool_context_characters: int = 10000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """缓存配置对象，避免每次请求都重复读取环境变量。"""
    return Settings()


settings = get_settings()
