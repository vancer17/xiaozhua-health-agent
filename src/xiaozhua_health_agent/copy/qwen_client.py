"""通义千问（DashScope OpenAI 兼容）异步 HTTP 客户端。

封装 ``openai.AsyncOpenAI``，供 ③-2 文案生成与其它 LLM 调用点使用。
IO 密集路径均为 ``async``；配置见 ``qwen_settings``。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final, Literal, TypeAlias

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from openai.types.chat import ChatCompletion
from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.copy.qwen_settings import (
    QwenClientSettings,
    QwenSettingsError,
    get_qwen_client_settings,
)

__all__ = [
    "AsyncQwenClient",
    "QwenApiError",
    "QwenChatCompletionRequest",
    "QwenChatCompletionResponse",
    "QwenChatMessage",
    "QwenChatRole",
    "QwenClientError",
    "QwenConfigurationError",
    "QwenResponseFormat",
    "QwenTimeoutError",
    "QwenTokenUsage",
    "create_default_qwen_client",
]

QwenChatRole: TypeAlias = Literal["system", "user", "assistant"]
"""OpenAI 兼容聊天消息角色。"""

QwenResponseFormat: TypeAlias = Literal["text", "json_object"]
"""聊天补全响应格式（``json_object`` 用于结构化文案 JSON）。"""

_DEFAULT_RESPONSE_FORMAT: Final[QwenResponseFormat] = "text"


class QwenClientError(Exception):
    """通义千问客户端调用链路基类异常。"""


class QwenConfigurationError(QwenClientError):
    """配置缺失或非法（如无 API Key）。"""


class QwenTimeoutError(QwenClientError):
    """请求在配置的超时时间内未完成。"""


class QwenApiError(QwenClientError):
    """远端 API 返回错误或连接失败。"""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: str | None = None,
    ) -> None:
        """构造 API 错误。

        :param message: 人类可读错误说明。
        :type message: str
        :param status_code: HTTP 状态码（若有）。
        :type status_code: int | None
        :param body: 响应体摘要（若有）。
        :type body: str | None
        """
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class QwenChatMessage(BaseModel):
    """单条聊天消息（OpenAI messages 数组元素）。

    :ivar role: 消息角色。
    :vartype role: QwenChatRole
    :ivar content: 文本内容。
    :vartype content: str
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: QwenChatRole = Field(description="OpenAI 兼容消息角色。")
    content: str = Field(min_length=1, description="消息正文。")

    def to_openai_dict(self) -> dict[str, str]:
        """转为 OpenAI SDK 接受的 ``messages`` 元素字典。

        :returns: 含 ``role`` 与 ``content`` 键的字典。
        :rtype: dict[str, str]
        """
        return {"role": self.role, "content": self.content}


class QwenChatCompletionRequest(BaseModel):
    """聊天补全请求参数（③-2 Prompt 组装后的调用入参）。

    :ivar messages: 有序消息列表（通常 system + user）。
    :vartype messages: tuple[QwenChatMessage, ...]
    :ivar model: 模型名；省略时由客户端默认配置填充。
    :vartype model: str | None
    :ivar temperature: 采样温度。
    :vartype temperature: float | None
    :ivar max_tokens: 最大生成 token。
    :vartype max_tokens: int | None
    :ivar response_format: 响应格式；``json_object`` 时要求 system/user 含 JSON 说明。
    :vartype response_format: QwenResponseFormat
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    messages: tuple[QwenChatMessage, ...] = Field(
        min_length=1,
        description="聊天消息序列。",
    )
    model: str | None = Field(
        default=None,
        description="覆盖客户端默认模型。",
    )
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="覆盖默认 temperature。",
    )
    max_tokens: int | None = Field(
        default=None,
        ge=1,
        description="覆盖默认 max_tokens。",
    )
    response_format: QwenResponseFormat = Field(
        default=_DEFAULT_RESPONSE_FORMAT,
        description="期望的响应格式。",
    )

    def to_openai_messages(self) -> list[dict[str, str]]:
        """展开为 OpenAI SDK ``messages`` 参数。

        :returns: 消息字典列表。
        :rtype: list[dict[str, str]]
        """
        return [message.to_openai_dict() for message in self.messages]


@dataclass(frozen=True, slots=True)
class QwenTokenUsage:
    """Token 用量摘要（来自 API usage 字段）。

    :ivar prompt_tokens: 输入 token 数。
    :vartype prompt_tokens: int
    :ivar completion_tokens: 输出 token 数。
    :vartype completion_tokens: int
    :ivar total_tokens: 合计 token 数。
    :vartype total_tokens: int
    """

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    @classmethod
    def from_openai_usage(cls, usage: object | None) -> QwenTokenUsage | None:
        """从 OpenAI ``Completion.usage`` 解析用量。

        :param usage: SDK 返回的 usage 对象或 ``None``。
        :type usage: object | None
        :returns: 解析成功时返回用量摘要；无 usage 时返回 ``None``。
        :rtype: QwenTokenUsage | None
        """
        if usage is None:
            return None
        prompt = getattr(usage, "prompt_tokens", None)
        completion = getattr(usage, "completion_tokens", None)
        total = getattr(usage, "total_tokens", None)
        if not all(isinstance(value, int) for value in (prompt, completion, total)):
            return None
        return cls(
            prompt_tokens=prompt,  # type: ignore[arg-type]
            completion_tokens=completion,  # type: ignore[arg-type]
            total_tokens=total,  # type: ignore[arg-type]
        )


@dataclass(frozen=True, slots=True)
class QwenChatCompletionResponse:
    """聊天补全成功响应（③-2 解析 JSON 前的原始文本层）。

    :ivar content: 助手回复正文（纯文本或 JSON 字符串）。
    :vartype content: str
    :ivar model: 实际使用的模型 id。
    :vartype model: str
    :ivar usage: Token 用量（可选）。
    :vartype usage: QwenTokenUsage | None
    :ivar finish_reason: 结束原因（如 ``stop``、``length``）。
    :vartype finish_reason: str | None
    :ivar raw: 原始 SDK ``ChatCompletion`` 对象（调试 / 审计）。
    :vartype raw: ChatCompletion
    """

    content: str
    model: str
    usage: QwenTokenUsage | None
    finish_reason: str | None
    raw: ChatCompletion


class AsyncQwenClient:
    """通义千问异步 OpenAI 兼容客户端。

    使用 ``openai.AsyncOpenAI`` 连接 DashScope；所有网络 IO 经 ``create_chat_completion`` 异步完成。

    :ivar settings: 客户端配置快照。
    :vartype settings: QwenClientSettings
    """

    def __init__(
        self,
        settings: QwenClientSettings,
        *,
        openai_client: AsyncOpenAI | None = None,
    ) -> None:
        """构造客户端（可注入 mock ``AsyncOpenAI`` 便于测试）。

        :param settings: 运行时配置（含 base_url、timeout、api_key）。
        :type settings: QwenClientSettings
        :param openai_client: 可选预构造 SDK 客户端；省略时按 ``settings`` 创建。
        :type openai_client: AsyncOpenAI | None
        :raises QwenConfigurationError: ``settings.api_key`` 未配置且未注入客户端时抛出。
        """
        self._settings = settings
        if openai_client is not None:
            self._client = openai_client
            return

        try:
            api_key = settings.require_api_key()
        except QwenSettingsError as exc:
            raise QwenConfigurationError(str(exc)) from exc
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.base_url,
            timeout=settings.timeout_sec,
            max_retries=settings.max_retries,
        )

    @property
    def settings(self) -> QwenClientSettings:
        """只读配置引用。

        :returns: 构造时传入的设置对象。
        :rtype: QwenClientSettings
        """
        return self._settings

    @classmethod
    def from_settings(
        cls,
        settings: QwenClientSettings | None = None,
    ) -> AsyncQwenClient:
        """从设置对象或进程默认环境构造客户端。

        :param settings: 显式配置；``None`` 时使用 ``get_qwen_client_settings()``。
        :type settings: QwenClientSettings | None
        :returns: 就绪的异步客户端实例。
        :rtype: AsyncQwenClient
        """
        resolved = settings if settings is not None else get_qwen_client_settings()
        return cls(resolved)

    async def create_chat_completion(
        self,
        request: QwenChatCompletionRequest,
    ) -> QwenChatCompletionResponse:
        """发起一次聊天补全（异步；受 ``settings.timeout_sec`` 约束）。

        :param request: 消息与生成参数。
        :type request: QwenChatCompletionRequest
        :returns: 助手回复正文及元数据。
        :rtype: QwenChatCompletionResponse
        :raises QwenTimeoutError: 请求超时时抛出。
        :raises QwenApiError: 连接失败或 HTTP 错误时抛出。
        :raises QwenClientError: 响应结构异常（无 choices）时抛出。
        """
        model = request.model if request.model is not None else self._settings.model
        temperature = (
            request.temperature
            if request.temperature is not None
            else self._settings.default_temperature
        )
        max_tokens = (
            request.max_tokens
            if request.max_tokens is not None
            else self._settings.default_max_tokens
        )

        create_kwargs: dict[str, Any] = {
            "model": model,
            "messages": request.to_openai_messages(),
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if request.response_format == "json_object":
            create_kwargs["response_format"] = {"type": "json_object"}

        try:
            completion: ChatCompletion = await self._client.chat.completions.create(
                **create_kwargs,
            )
        except APITimeoutError as exc:
            msg = f"通义千问请求超时（>{self._settings.timeout_sec}s）。"
            raise QwenTimeoutError(msg) from exc
        except APIConnectionError as exc:
            msg = f"通义千问连接失败：{exc}"
            raise QwenApiError(msg) from exc
        except APIStatusError as exc:
            body_text = _safe_response_body(exc)
            msg = f"通义千问 API 错误（HTTP {exc.status_code}）：{exc.message}"
            raise QwenApiError(
                msg,
                status_code=exc.status_code,
                body=body_text,
            ) from exc

        return _parse_chat_completion(completion)

    async def aclose(self) -> None:
        """关闭底层 HTTP 连接池（应用 shutdown 时调用）。

        :returns: ``None``
        :rtype: None
        """
        await self._client.close()


def create_default_qwen_client() -> AsyncQwenClient:
    """使用进程默认环境配置构造 ``AsyncQwenClient``。

    :returns: 异步客户端实例。
    :rtype: AsyncQwenClient
    :raises QwenConfigurationError: 未配置 ``QWEN_API_KEY`` 时抛出。
    """
    return AsyncQwenClient.from_settings()


def _parse_chat_completion(completion: ChatCompletion) -> QwenChatCompletionResponse:
    """将 SDK ``ChatCompletion`` 转为领域响应对象。

    :param completion: OpenAI SDK 原始响应。
    :type completion: ChatCompletion
    :returns: 提取正文与用量的响应摘要。
    :rtype: QwenChatCompletionResponse
    :raises QwenClientError: ``choices`` 为空或正文缺失时抛出。
    """
    if not completion.choices:
        msg = "通义千问响应缺少 choices。"
        raise QwenClientError(msg)

    first_choice = completion.choices[0]
    message_content = first_choice.message.content
    if message_content is None or not str(message_content).strip():
        msg = "通义千问响应正文为空。"
        raise QwenClientError(msg)

    usage = QwenTokenUsage.from_openai_usage(completion.usage)
    model_name = completion.model if completion.model else "unknown"

    return QwenChatCompletionResponse(
        content=str(message_content),
        model=model_name,
        usage=usage,
        finish_reason=first_choice.finish_reason,
        raw=completion,
    )


def _safe_response_body(error: APIStatusError) -> str | None:
    """从 ``APIStatusError`` 安全提取响应体文本（用于日志，避免过长）。

    :param error: OpenAI SDK 状态错误。
    :type error: APIStatusError
    :returns: 截断后的响应体字符串；不可读时返回 ``None``。
    :rtype: str | None
    """
    try:
        body = error.response.text
    except (AttributeError, TypeError):
        return None
    if not body:
        return None
    stripped = body.strip()
    if len(stripped) > 500:
        return stripped[:500] + "…"
    return stripped
