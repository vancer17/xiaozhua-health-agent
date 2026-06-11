"""WP4 ③-2 通义千问异步客户端测试。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import APITimeoutError
from pydantic import SecretStr

from xiaozhua_health_agent.copy import (
    AsyncQwenClient,
    QwenChatCompletionRequest,
    QwenChatMessage,
    QwenClientSettings,
    QwenConfigurationError,
    QwenTimeoutError,
)


@pytest.fixture
def qwen_settings() -> QwenClientSettings:
    """带测试 API Key 的客户端配置。"""
    return QwenClientSettings(
        api_key=SecretStr("test-key"),
        base_url="https://example.com/v1",
        model="qwen-plus",
        timeout_sec=5.0,
        max_retries=0,
    )


@pytest.fixture
def mock_openai_client() -> MagicMock:
    """可注入的 AsyncOpenAI 替身。"""
    client = MagicMock()
    client.chat = MagicMock()
    client.chat.completions = MagicMock()
    client.chat.completions.create = AsyncMock()
    client.close = AsyncMock()
    return client


def test_async_qwen_client_requires_api_key() -> None:
    """未配置 API Key 时构造客户端应失败。"""
    settings = QwenClientSettings(api_key=None)
    with pytest.raises(QwenConfigurationError, match="QWEN_API_KEY"):
        AsyncQwenClient(settings)


@pytest.mark.asyncio
async def test_create_chat_completion_success(
    qwen_settings: QwenClientSettings,
    mock_openai_client: MagicMock,
) -> None:
    """成功解析助手正文与 usage。"""
    mock_openai_client.chat.completions.create.return_value = SimpleNamespace(
        id="chat-1",
        model="qwen-plus",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content='{"title":"测试"}'),
                finish_reason="stop",
            ),
        ],
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=20,
            total_tokens=30,
        ),
    )
    client = AsyncQwenClient(qwen_settings, openai_client=mock_openai_client)
    request = QwenChatCompletionRequest(
        messages=(
            QwenChatMessage(role="system", content="你是助手。"),
            QwenChatMessage(role="user", content="你好。"),
        ),
        response_format="json_object",
    )

    response = await client.create_chat_completion(request)

    assert response.content == '{"title":"测试"}'
    assert response.model == "qwen-plus"
    assert response.usage is not None
    assert response.usage.total_tokens == 30
    assert response.finish_reason == "stop"

    call_kwargs: dict[str, Any] = (
        mock_openai_client.chat.completions.create.await_args.kwargs
    )
    assert call_kwargs["model"] == "qwen-plus"
    assert call_kwargs["response_format"] == {"type": "json_object"}
    assert len(call_kwargs["messages"]) == 2


@pytest.mark.asyncio
async def test_create_chat_completion_timeout(
    qwen_settings: QwenClientSettings,
    mock_openai_client: MagicMock,
) -> None:
    """APITimeoutError 应映射为 QwenTimeoutError。"""
    mock_request = MagicMock()
    mock_openai_client.chat.completions.create.side_effect = APITimeoutError(
        request=mock_request,
    )
    client = AsyncQwenClient(qwen_settings, openai_client=mock_openai_client)
    request = QwenChatCompletionRequest(
        messages=(QwenChatMessage(role="user", content="ping"),),
    )

    with pytest.raises(QwenTimeoutError, match="超时"):
        await client.create_chat_completion(request)


@pytest.mark.asyncio
async def test_aclose_delegates_to_sdk(
    qwen_settings: QwenClientSettings,
    mock_openai_client: MagicMock,
) -> None:
    """aclose 应关闭底层 SDK 客户端。"""
    client = AsyncQwenClient(qwen_settings, openai_client=mock_openai_client)
    await client.aclose()
    mock_openai_client.close.assert_awaited_once()
