from pydantic import BaseModel


class RagCacheStatsRead(BaseModel):
    knowledge_base_id: int
    enabled: bool
    ttl_seconds: int
    max_entries: int
    max_entries_per_kb: int
    entry_count: int
    hit_count: int
    estimated_chat_tokens_saved: int


class RagCacheClearRead(BaseModel):
    knowledge_base_id: int
    deleted_entry_count: int
