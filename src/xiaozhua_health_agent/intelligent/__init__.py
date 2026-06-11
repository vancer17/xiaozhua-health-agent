"""``/intelligent`` 对话入口 — 公开 API 门面（V1 方案 A 占位）。

包外代码应只从本模块导入：

.. code-block:: python

    from xiaozhua_health_agent.intelligent import (
        IntelligentPlaceholderResponse,
        build_intelligent_placeholder_response_async,
    )

本包 **不** 调用 ``pipeline`` / ``triage`` 分诊管道；仅提供静态模板占位响应。
跨包引用请使用 ``eval``、``schemas`` 等包的 ``__init__`` 门面。
"""

from __future__ import annotations

from xiaozhua_health_agent.intelligent.placeholder_service import (
    IntelligentPlaceholderBuildContext,
    IntelligentPlaceholderRequestContext,
    build_intelligent_placeholder_response,
    build_intelligent_placeholder_response_async,
    resolve_session_id,
    serialize_intelligent_placeholder_response,
    validate_intelligent_request,
    validate_intelligent_request_async,
)
from xiaozhua_health_agent.intelligent.placeholder_types import (
    INTELLIGENT_PLACEHOLDER_SCHEMA_VERSION,
    INTELLIGENT_PLACEHOLDER_TEMPLATE_VERSION,
    IntelligentChatMessage,
    IntelligentMessageRole,
    IntelligentPlaceholderMeta,
    IntelligentPlaceholderMode,
    IntelligentPlaceholderResponse,
    IntelligentTriageStatus,
)
from xiaozhua_health_agent.intelligent.static_templates import (
    DEFAULT_SUGGESTED_PROMPTS,
    PLACEHOLDER_ASSISTANT_GREETING,
    PLACEHOLDER_ASSISTANT_GUIDANCE,
    PLACEHOLDER_SYSTEM_NOTICE,
    build_placeholder_messages,
)

__all__ = [
    "DEFAULT_SUGGESTED_PROMPTS",
    "INTELLIGENT_PLACEHOLDER_SCHEMA_VERSION",
    "INTELLIGENT_PLACEHOLDER_TEMPLATE_VERSION",
    "IntelligentChatMessage",
    "IntelligentMessageRole",
    "IntelligentPlaceholderBuildContext",
    "IntelligentPlaceholderMeta",
    "IntelligentPlaceholderMode",
    "IntelligentPlaceholderRequestContext",
    "IntelligentPlaceholderResponse",
    "IntelligentTriageStatus",
    "PLACEHOLDER_ASSISTANT_GREETING",
    "PLACEHOLDER_ASSISTANT_GUIDANCE",
    "PLACEHOLDER_SYSTEM_NOTICE",
    "build_intelligent_placeholder_response",
    "build_intelligent_placeholder_response_async",
    "build_placeholder_messages",
    "resolve_session_id",
    "serialize_intelligent_placeholder_response",
    "validate_intelligent_request",
    "validate_intelligent_request_async",
]
