"""``/intelligent`` 占位响应 DTO（方案 A · 纯静态模板）。"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "INTELLIGENT_PLACEHOLDER_SCHEMA_VERSION",
    "INTELLIGENT_PLACEHOLDER_TEMPLATE_VERSION",
    "IntelligentChatMessage",
    "IntelligentMessageRole",
    "IntelligentMessageRoleLiteral",
    "IntelligentPlaceholderMeta",
    "IntelligentPlaceholderResponse",
    "IntelligentPlaceholderMode",
    "IntelligentPlaceholderModeLiteral",
    "IntelligentTriageStatus",
    "IntelligentTriageStatusLiteral",
]

INTELLIGENT_PLACEHOLDER_SCHEMA_VERSION: str = (
    "xiaozhua.health_agent.intelligent.placeholder.v1"
)
"""占位响应信封 schema 版本。"""

INTELLIGENT_PLACEHOLDER_TEMPLATE_VERSION: str = "placeholder.static.v1"
"""静态模板内容版本（与分诊 ``bundleVersion`` 独立）。"""

IntelligentPlaceholderModeLiteral: TypeAlias = Literal["placeholder"]
"""占位接口固定 ``mode`` 取值。"""

IntelligentTriageStatusLiteral: TypeAlias = Literal["not_run"]
"""方案 A 不运行分诊管道时的 ``triageStatus`` 取值。"""

IntelligentMessageRoleLiteral: TypeAlias = Literal["assistant", "system"]
"""占位对话消息角色。"""


class IntelligentPlaceholderMode:
    """``mode`` 字段常量。"""

    PLACEHOLDER: IntelligentPlaceholderModeLiteral = "placeholder"


class IntelligentTriageStatus:
    """``triageStatus`` 字段常量。"""

    NOT_RUN: IntelligentTriageStatusLiteral = "not_run"


class IntelligentMessageRole(StrEnum):
    """对话消息角色枚举。"""

    ASSISTANT = "assistant"
    SYSTEM = "system"


class IntelligentChatMessage(BaseModel):
    """单条占位对话消息。

    :ivar role: 消息角色（占位阶段仅 ``assistant`` / ``system``）。
    :vartype role: IntelligentMessageRoleLiteral
    :ivar content: 展示给用户的文本内容。
    :vartype content: str
    :ivar timestamp: ISO-8601 时间戳；占位可为服务端生成时刻。
    :vartype timestamp: str | None
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    role: IntelligentMessageRoleLiteral = Field(
        description="消息角色：assistant 或 system。",
    )
    content: str = Field(
        min_length=1,
        description="消息正文，不得包含未验证的医学数值。",
    )
    timestamp: str | None = Field(
        default=None,
        description="可选 ISO-8601 时间戳。",
    )


class IntelligentPlaceholderMeta(BaseModel):
    """占位响应元数据。

    :ivar placeholder: 固定为 ``True``，标明非真实多轮 LLM。
    :vartype placeholder: bool
    :ivar schema_version: 信封 schema 版本。
    :vartype schema_version: str
    :ivar template_version: 静态模板版本。
    :vartype template_version: str
    :ivar generated_at: 响应生成时刻（ISO-8601）。
    :vartype generated_at: str
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    placeholder: bool = Field(
        default=True,
        description="是否为 V1 占位实现。",
    )
    schema_version: str = Field(
        alias="schemaVersion",
        description="占位信封 schema 版本。",
    )
    template_version: str = Field(
        alias="templateVersion",
        description="静态模板内容版本。",
    )
    generated_at: str = Field(
        alias="generatedAt",
        description="响应生成时间（ISO-8601）。",
    )


class IntelligentPlaceholderResponse(BaseModel):
    """``POST /intelligent`` 方案 A 标准占位响应体。

    :ivar mode: 固定 ``placeholder``。
    :vartype mode: IntelligentPlaceholderModeLiteral
    :ivar session_id: 会话标识（请求头回显或服务端生成）。
    :vartype session_id: str
    :ivar turn_index: 轮次序号；占位固定为 ``1``。
    :vartype turn_index: int
    :ivar messages: 供 App 聊天 UI 渲染的占位消息列表。
    :vartype messages: list[IntelligentChatMessage]
    :ivar suggested_prompts: 入口快捷提问建议。
    :vartype suggested_prompts: list[str]
    :ivar triage: 方案 A 不运行管道，固定为 ``null``。
    :vartype triage: None
    :ivar triage_status: 分诊载荷状态，固定 ``not_run``。
    :vartype triage_status: IntelligentTriageStatusLiteral
    :ivar case_id: 校验通过时回显入参 ``caseId``。
    :vartype case_id: str | None
    :ivar pet_id: 校验通过时回显入参 ``pet.petId``。
    :vartype pet_id: str | None
    :ivar pet_name: 校验通过时回显入参 ``pet.name``（仅润色展示用）。
    :vartype pet_name: str | None
    :ivar meta: 占位元数据。
    :vartype meta: IntelligentPlaceholderMeta
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mode: IntelligentPlaceholderModeLiteral = Field(
        default=IntelligentPlaceholderMode.PLACEHOLDER,
        description="接口运行模式。",
    )
    session_id: str = Field(
        alias="sessionId",
        min_length=1,
        description="会话标识。",
    )
    turn_index: int = Field(
        alias="turnIndex",
        default=1,
        ge=1,
        description="当前对话轮次（占位固定为 1）。",
    )
    messages: list[IntelligentChatMessage] = Field(
        min_length=1,
        description="占位对话消息列表。",
    )
    suggested_prompts: list[str] = Field(
        alias="suggestedPrompts",
        default_factory=list,
        description="建议用户尝试的快捷提问。",
    )
    triage: None = Field(
        default=None,
        description="方案 A 不嵌入 ``output_schema`` 分诊结果。",
    )
    triage_status: IntelligentTriageStatusLiteral = Field(
        alias="triageStatus",
        default=IntelligentTriageStatus.NOT_RUN,
        description="分诊载荷是否已执行。",
    )
    case_id: str | None = Field(
        default=None,
        alias="caseId",
        description="回显的 case 标识。",
    )
    pet_id: str | None = Field(
        default=None,
        alias="petId",
        description="回显的宠物标识。",
    )
    pet_name: str | None = Field(
        default=None,
        alias="petName",
        description="回显的宠物昵称。",
    )
    meta: IntelligentPlaceholderMeta = Field(
        description="占位元数据。",
    )
