"""HTTP 请求 / 响应 DTO（WP6 阶段 2）。"""

from __future__ import annotations

from typing import Any, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.eval import Violation
from xiaozhua_health_agent.pipeline import HealthTriagePipelineStageLiteral

__all__ = [
    "HealthTriageErrorBody",
    "HealthTriageRequestBody",
    "LivenessResponse",
    "ReadinessResponse",
]

HealthTriageRequestBody: TypeAlias = dict[str, Any]
"""``POST /health`` 请求体：与 ``input_schema.v1`` 对齐的顶层 JSON 对象。"""


class HealthTriageErrorBody(BaseModel):
    """分诊失败时的结构化错误响应体。

    :ivar error: 错误类型标识（如 ``input_validation_failed``）。
    :vartype error: str
    :ivar case_id: 尽力读取的 caseId。
    :vartype case_id: str
    :ivar stage: 管道终止阶段。
    :vartype stage: HealthTriagePipelineStageLiteral
    :ivar message: 人类可读说明。
    :vartype message: str
    :ivar violations: 契约或 schema 违规列表。
    :vartype violations: list[Violation]
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    error: str = Field(description="机器可读错误类型。")
    case_id: str = Field(alias="caseId", description="用例标识。")
    stage: HealthTriagePipelineStageLiteral = Field(description="管道终止阶段。")
    message: str = Field(description="人类可读错误说明。")
    violations: list[Violation] = Field(
        default_factory=list,
        description="结构化违规项列表。",
    )


class LivenessResponse(BaseModel):
    """``GET .../healthz`` 存活探针响应。

    :ivar status: 固定 ``ok`` 表示进程存活。
    :vartype status: str
    """

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="ok", description="存活状态。")


class ReadinessResponse(BaseModel):
    """``GET .../readyz`` 就绪探针响应。

    :ivar ready: 是否可接收分诊流量。
    :vartype ready: bool
    :ivar copy_bundle_ready: KB-TPL 知识包是否已就绪。
    :vartype copy_bundle_ready: bool
    :ivar input_lex_bundle_ready: KB-INPUT-LEX 词表是否已就绪。
    :vartype input_lex_bundle_ready: bool
    :ivar message: 未就绪时的说明；就绪时可为空字符串。
    :vartype message: str
    """

    model_config = ConfigDict(extra="forbid")

    ready: bool = Field(description="服务是否就绪。")
    copy_bundle_ready: bool = Field(
        alias="copyBundleReady",
        description="copy 知识包是否就绪。",
    )
    input_lex_bundle_ready: bool = Field(
        alias="inputLexBundleReady",
        default=True,
        description="KB-INPUT-LEX 词表是否就绪（未启用 enrich 时恒为 true）。",
    )
    message: str = Field(default="", description="补充说明。")
