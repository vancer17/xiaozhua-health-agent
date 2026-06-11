"""``/intelligent`` 占位响应构建服务（方案 A · 不调用分诊管道）。"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from xiaozhua_health_agent.eval import ValidationResult, validate_input
from xiaozhua_health_agent.intelligent.placeholder_types import (
    INTELLIGENT_PLACEHOLDER_SCHEMA_VERSION,
    INTELLIGENT_PLACEHOLDER_TEMPLATE_VERSION,
    IntelligentChatMessage,
    IntelligentMessageRole,
    IntelligentPlaceholderMeta,
    IntelligentPlaceholderResponse,
)
from xiaozhua_health_agent.intelligent.static_templates import (
    DEFAULT_SUGGESTED_PROMPTS,
    PLACEHOLDER_SYSTEM_NOTICE,
    build_placeholder_messages,
)
from xiaozhua_health_agent.schemas import AgentInput

__all__ = [
    "IntelligentPlaceholderBuildContext",
    "IntelligentPlaceholderRequestContext",
    "build_intelligent_placeholder_response",
    "build_intelligent_placeholder_response_async",
    "resolve_session_id",
    "serialize_intelligent_placeholder_response",
    "validate_intelligent_request",
    "validate_intelligent_request_async",
]

_SESSION_HEADER_CANDIDATES: tuple[str, ...] = (
    "x-session-id",
    "x-sessionid",
)


@dataclass(frozen=True, slots=True)
class IntelligentPlaceholderRequestContext:
    """占位接口单次请求上下文（路由层组装）。

    :ivar session_id_header: 来自 HTTP 头的会话标识；可为 ``None``。
    :vartype session_id_header: str | None
    :ivar user_message: 可选用户本轮输入（占位仅回显，不参与医学推理）。
    :vartype user_message: str | None
    """

    session_id_header: str | None = None
    user_message: str | None = None


@dataclass(frozen=True, slots=True)
class IntelligentPlaceholderBuildContext:
    """构建占位响应所需的已校验入参上下文。

    :ivar parsed_input: 通过 input_schema 校验的 Agent 入参。
    :vartype parsed_input: AgentInput
    :ivar request_context: HTTP 层附加上下文。
    :vartype request_context: IntelligentPlaceholderRequestContext
    """

    parsed_input: AgentInput
    request_context: IntelligentPlaceholderRequestContext


def resolve_session_id(session_id_header: str | None) -> str:
    """解析或生成会话标识。

    :param session_id_header: 请求头中的 ``X-Session-Id`` 等；空白视为缺失。
    :type session_id_header: str | None
    :returns: 非空会话 id 字符串。
    :rtype: str
    """
    if session_id_header is not None:
        stripped = session_id_header.strip()
        if stripped:
            return stripped
    return str(uuid.uuid4())


def validate_intelligent_request(
    body: AgentInput | Mapping[str, Any],
) -> ValidationResult[AgentInput]:
    """校验 intelligent 入参是否符合 ``input_schema.v1``（同步）。

    与 ``POST /health`` 使用同一契约，便于 App mock adapter 复用组装逻辑；
    **不** 调用分诊管道。

    :param body: 原始 JSON 字典或 ``AgentInput``。
    :type body: AgentInput | collections.abc.Mapping[str, Any]
    :returns: 校验结果。
    :rtype: ValidationResult[AgentInput]
    """
    return validate_input(body)


async def validate_intelligent_request_async(
    body: AgentInput | Mapping[str, Any],
) -> ValidationResult[AgentInput]:
    """校验 intelligent 入参（异步，CPU 密集委托线程池）。

    :param body: 原始 JSON 字典或 ``AgentInput``。
    :type body: AgentInput | collections.abc.Mapping[str, Any]
    :returns: 校验结果。
    :rtype: ValidationResult[AgentInput]
    """

    def _validate_in_thread() -> ValidationResult[AgentInput]:
        """在线程池中执行契约校验（闭包）。

        :returns: 校验结果。
        :rtype: ValidationResult[AgentInput]
        """
        return validate_intelligent_request(body)

    return await asyncio.to_thread(_validate_in_thread)


def build_intelligent_placeholder_response(
    context: IntelligentPlaceholderBuildContext,
) -> IntelligentPlaceholderResponse:
    """构建方案 A 纯静态占位响应（同步）。

    :param context: 已校验入参与 HTTP 上下文。
    :type context: IntelligentPlaceholderBuildContext
    :returns: 完整占位响应 DTO。
    :rtype: IntelligentPlaceholderResponse
    """
    parsed = context.parsed_input
    request_ctx = context.request_context
    session_id = resolve_session_id(request_ctx.session_id_header)
    generated_at = _utc_now_iso()

    greeting, guidance = build_placeholder_messages(pet_name=parsed.pet.name)
    messages = _build_message_list(
        greeting=greeting,
        guidance=guidance,
        user_message=request_ctx.user_message,
        generated_at=generated_at,
    )

    meta = IntelligentPlaceholderMeta(
        schemaVersion=INTELLIGENT_PLACEHOLDER_SCHEMA_VERSION,
        templateVersion=INTELLIGENT_PLACEHOLDER_TEMPLATE_VERSION,
        generatedAt=generated_at,
    )

    return IntelligentPlaceholderResponse(
        sessionId=session_id,
        turnIndex=1,
        messages=messages,
        suggestedPrompts=list(DEFAULT_SUGGESTED_PROMPTS),
        triage=None,
        triageStatus="not_run",
        caseId=parsed.case_id,
        petId=parsed.pet.pet_id,
        petName=parsed.pet.name,
        meta=meta,
    )


async def build_intelligent_placeholder_response_async(
    context: IntelligentPlaceholderBuildContext,
) -> IntelligentPlaceholderResponse:
    """构建方案 A 纯静态占位响应（异步）。

    将同步组装委托 ``asyncio.to_thread``，避免阻塞事件循环。

    :param context: 已校验入参与 HTTP 上下文。
    :type context: IntelligentPlaceholderBuildContext
    :returns: 完整占位响应 DTO。
    :rtype: IntelligentPlaceholderResponse
    """

    def _build_in_thread() -> IntelligentPlaceholderResponse:
        """在线程池中构建占位响应（闭包）。

        :returns: 占位响应 DTO。
        :rtype: IntelligentPlaceholderResponse
        """
        return build_intelligent_placeholder_response(context)

    return await asyncio.to_thread(_build_in_thread)


def serialize_intelligent_placeholder_response(
    response: IntelligentPlaceholderResponse,
) -> dict[str, Any]:
    """将占位响应序列化为 camelCase JSON 兼容字典。

    :param response: 占位响应 DTO。
    :type response: IntelligentPlaceholderResponse
    :returns: 可 JSON 编码的顶层字典。
    :rtype: dict[str, Any]
    """
    return response.model_dump(by_alias=True, mode="json")


def _utc_now_iso() -> str:
    """返回当前 UTC 时刻的 ISO-8601 字符串。

    :returns: ISO-8601 时间戳。
    :rtype: str
    """
    return datetime.now(UTC).isoformat()


def _build_message_list(
    *,
    greeting: str,
    guidance: str,
    user_message: str | None,
    generated_at: str,
) -> list[IntelligentChatMessage]:
    """组装占位对话消息列表（内部辅助）。

    :param greeting: 助手欢迎语。
    :type greeting: str
    :param guidance: 助手安全引导语。
    :type guidance: str
    :param user_message: 可选用户输入；非空时追加 ``assistant`` 回显占位。
    :type user_message: str | None
    :param generated_at: 消息时间戳。
    :type generated_at: str
    :returns: 至少包含 system + assistant 的消息列表。
    :rtype: list[IntelligentChatMessage]
    """
    messages: list[IntelligentChatMessage] = [
        IntelligentChatMessage(
            role=IntelligentMessageRole.SYSTEM.value,
            content=PLACEHOLDER_SYSTEM_NOTICE,
            timestamp=generated_at,
        ),
        IntelligentChatMessage(
            role=IntelligentMessageRole.ASSISTANT.value,
            content=greeting,
            timestamp=generated_at,
        ),
        IntelligentChatMessage(
            role=IntelligentMessageRole.ASSISTANT.value,
            content=guidance,
            timestamp=generated_at,
        ),
    ]

    echo = _normalize_user_message(user_message)
    if echo is not None:
        messages.append(
            IntelligentChatMessage(
                role=IntelligentMessageRole.ASSISTANT.value,
                content=(
                    f"（占位回显）已收到你的描述：「{echo}」。"
                    "当前对话模式不会分析症状，请使用健康分诊获取结构化建议。"
                ),
                timestamp=generated_at,
            ),
        )

    return messages


def _normalize_user_message(user_message: str | None) -> str | None:
    """规范化可选用户消息（内部辅助）。

    :param user_message: 原始用户输入。
    :type user_message: str | None
    :returns: 去空白后的非空字符串，或 ``None``。
    :rtype: str | None
    """
    if user_message is None:
        return None
    stripped = user_message.strip()
    if not stripped:
        return None
    return stripped
