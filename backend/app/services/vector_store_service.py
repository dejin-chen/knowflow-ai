import chromadb
from dataclasses import dataclass
from fastapi import HTTPException, status

from app.core.config import settings
from app.models.document_chunk import DocumentChunk


@dataclass(frozen=True)
class VectorSearchMatch:
    """Chroma 返回的向量命中信息。"""

    chroma_id: str
    chunk_id: int
    document_id: int
    knowledge_base_id: int
    chunk_index: int
    distance: float


class ChromaVectorStoreService:
    """封装 Chroma 的持久化向量存储操作。"""

    def __init__(self) -> None:
        self.client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_chunks(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
    ) -> list[str]:
        if len(chunks) != len(embeddings):
            raise ValueError("Chunk 数量与 Embedding 数量不一致")

        chroma_ids = [f"chunk-{chunk.id}" for chunk in chunks]
        metadatas = [
            {
                # metadata 不参与相似度计算，而是为知识库过滤与引用溯源提供定位信息。
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "knowledge_base_id": chunk.knowledge_base_id,
                "chunk_index": chunk.chunk_index,
            }
            for chunk in chunks
        ]

        try:
            self.collection.upsert(
                ids=chroma_ids,
                embeddings=embeddings,
                documents=[chunk.content for chunk in chunks],
                metadatas=metadatas,
            )
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Chroma 向量库写入失败",
            ) from error

        return chroma_ids

    def search(
        self,
        query_embedding: list[float],
        knowledge_base_id: int,
        top_k: int,
    ) -> list[VectorSearchMatch]:
        """在指定知识库范围内查询距离最近的向量记录。"""
        try:
            result = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k,
                where={"knowledge_base_id": knowledge_base_id},
                include=["metadatas", "distances", "documents"],
            )
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Chroma 向量库检索失败",
            ) from error

        ids = result["ids"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]
        return [
            VectorSearchMatch(
                chroma_id=chroma_id,
                chunk_id=int(metadata["chunk_id"]),
                document_id=int(metadata["document_id"]),
                knowledge_base_id=int(metadata["knowledge_base_id"]),
                chunk_index=int(metadata["chunk_index"]),
                # cosine distance 越小，语义通常越接近；在接口中原样返回，避免伪造分数含义。
                distance=float(distance),
            )
            for chroma_id, metadata, distance in zip(
                ids,
                metadatas,
                distances,
                strict=True,
            )
        ]
