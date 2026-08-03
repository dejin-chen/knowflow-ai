from dataclasses import dataclass

from fastapi import HTTPException, status
from openai import APIConnectionError, APIError, APITimeoutError, OpenAI

from app.core.config import settings
from app.services.rag_prompt_service import RagPrompt


@dataclass(frozen=True)
class ChatCompletionResult:
    """一次真实聊天模型调用的文本结果与服务端返回的 Token 统计。"""

    answer: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionService:
    """调用 OpenAI 兼容聊天模型，并保留可观测性所需的用量数据。"""

    def generate_completion(
        self,
        prompt: RagPrompt,
        *,
        model_name: str | None = None,
        temperature: float = 0.1,
    ) -> ChatCompletionResult:
        if not settings.chat_api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="未配置聊天模型 API Key。",
            )

        client = OpenAI(
            api_key=settings.chat_api_key,
            base_url=settings.chat_base_url,
            timeout=settings.model_request_timeout_seconds,
            max_retries=settings.model_max_retries,
        )
        try:
            response = client.chat.completions.create(
                model=model_name or settings.chat_model,
                temperature=temperature,
                messages=[
                    {"role": "system", "content": prompt.system_message},
                    {"role": "user", "content": prompt.user_message},
                ],
            )
        except (APITimeoutError, APIConnectionError) as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="聊天模型服务暂时不可用，请稍后重试。",
            ) from error
        except APIError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="聊天模型调用失败。",
            ) from error

        answer = response.choices[0].message.content
        if not answer or not answer.strip():
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="聊天模型未返回有效回答。",
            )

        usage = response.usage
        return ChatCompletionResult(
            answer=answer.strip(),
            model_name=response.model or model_name or settings.chat_model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage, "total_tokens", 0) or 0,
        )
