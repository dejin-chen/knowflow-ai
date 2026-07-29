from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.vector_index import VectorIndex


class VectorIndexRepository:
    """向量索引映射表的数据访问层。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_many(self, mappings: list[tuple[int, str]]) -> list[VectorIndex]:
        """写入 Chunk 与 Chroma ID 的映射，重复索引时更新已有记录。"""
        if not mappings:
            return []

        chunk_ids = [chunk_id for chunk_id, _ in mappings]
        statement = select(VectorIndex).where(VectorIndex.chunk_id.in_(chunk_ids))
        existing_by_chunk_id = {
            record.chunk_id: record for record in self.db.scalars(statement).all()
        }

        records: list[VectorIndex] = []
        for chunk_id, chroma_id in mappings:
            record = existing_by_chunk_id.get(chunk_id)
            if record is None:
                record = VectorIndex(chunk_id=chunk_id, chroma_id=chroma_id)
                self.db.add(record)
            else:
                record.chroma_id = chroma_id
                record.status = "indexed"
                record.indexed_at = datetime.now(timezone.utc)
                record.last_error = None
            records.append(record)

        self.db.commit()
        for record in records:
            self.db.refresh(record)
        return records
