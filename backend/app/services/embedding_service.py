from fastapi import HTTPException, status
from openai import APIConnectionError, APIError, APITimeoutError, OpenAI

from app.core.config import settings


class EmbeddingService:
    """OpenAI 兼容 Embedding 服务。

    Embedding 会把文本转换成高维数字向量。相似语义的文本在向量空间中距离更近，
    Chroma 正是利用这一点完成语义检索。
    """

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not settings.openai_api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="未配置 Embedding API Key",
            )

        client = OpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
            timeout=settings.model_request_timeout_seconds,
            max_retries=settings.model_max_retries,
        )
        embeddings: list[list[float]] = []

        try:
            # 批量请求可减少网络往返，也便于后续控制 API 并发和费用。
            for text_batch in self._iter_batches(texts, settings.embedding_batch_size):
                response = client.embeddings.create(
                    model=settings.embedding_model,
                    input=text_batch,
                    encoding_format="float",
                )
                embeddings.extend(item.embedding for item in response.data)
        except (APITimeoutError, APIConnectionError) as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Embedding 服务暂时不可用，请稍后重试",
            ) from error
        except APIError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="Embedding 服务调用失败",
            ) from error

        return embeddings

    @staticmethod
    def _iter_batches(texts: list[str], batch_size: int) -> list[list[str]]:
        """使用基础切片实现批处理，保持对 Python 3.10+ 的兼容。"""
        return [texts[index : index + batch_size] for index in range(0, len(texts), batch_size)]
