from types import SimpleNamespace

from fastapi import HTTPException
import httpx
from openai import APITimeoutError
import pytest

from app.core.config import settings
from app.services import chat_completion_service, embedding_service
from app.services.chat_completion_service import ChatCompletionService
from app.services.embedding_service import EmbeddingService
from app.services.rag_prompt_service import RagPrompt


def timeout_error() -> APITimeoutError:
    return APITimeoutError(request=httpx.Request("POST", "https://model.test/v1"))


def test_embedding_timeout_returns_service_unavailable(monkeypatch) -> None:
    received_options: dict = {}

    def fake_openai(**kwargs):
        received_options.update(kwargs)
        return SimpleNamespace(
            embeddings=SimpleNamespace(
                create=lambda **_kwargs: (_ for _ in ()).throw(timeout_error())
            )
        )

    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "model_request_timeout_seconds", 12.0)
    monkeypatch.setattr(settings, "model_max_retries", 0)
    monkeypatch.setattr(embedding_service, "OpenAI", fake_openai)

    with pytest.raises(HTTPException) as exc_info:
        EmbeddingService().embed_texts(["测试文本"])

    assert exc_info.value.status_code == 503
    assert received_options["timeout"] == 12.0
    assert received_options["max_retries"] == 0


def test_chat_timeout_returns_service_unavailable(monkeypatch) -> None:
    received_options: dict = {}

    def fake_openai(**kwargs):
        received_options.update(kwargs)
        return SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **_kwargs: (_ for _ in ()).throw(timeout_error())
                )
            )
        )

    monkeypatch.setattr(settings, "chat_api_key", "test-key")
    monkeypatch.setattr(settings, "model_request_timeout_seconds", 15.0)
    monkeypatch.setattr(settings, "model_max_retries", 1)
    monkeypatch.setattr(chat_completion_service, "OpenAI", fake_openai)

    with pytest.raises(HTTPException) as exc_info:
        ChatCompletionService().generate_completion(
            RagPrompt(system_message="系统提示", user_message="用户问题")
        )

    assert exc_info.value.status_code == 503
    assert received_options["timeout"] == 15.0
    assert received_options["max_retries"] == 1
