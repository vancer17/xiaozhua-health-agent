"""Schema 校验结果与违规项类型定义。"""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

TParsed = TypeVar("TParsed")


class SchemaKind(StrEnum):
    """被校验的契约种类。"""

    INPUT = "input"
    OUTPUT = "output"
    DRAFT_COPY = "draft_copy"


SchemaKindLiteral = Literal["input", "output", "draft_copy"]


class OutputValidationMode(StrEnum):
    """输出校验严格程度。"""

    FULL = "full"
    MINIMAL = "minimal"


OutputValidationModeLiteral = Literal["full", "minimal"]


class ViolationDomain(StrEnum):
    """违规来源域，用于区分契约校验、内容守卫与 L7 评测。

    重试协调器（WP5）应仅消费 ``schema`` / ``guard`` 域的违规；
    ``risk_eval`` / ``semantic_eval`` 仅供批跑报告，不得触发文案重试。
    """

    SCHEMA = "schema"
    GUARD = "guard"
    RISK_EVAL = "risk_eval"
    SEMANTIC_EVAL = "semantic_eval"


ViolationDomainLiteral = Literal["schema", "guard", "risk_eval", "semantic_eval"]


class ViolationCode(StrEnum):
    """结构化违规码，供批跑报告、重试协调器与 risk-only 评测消费。

    契约 / 守卫类码（``PARSE_ERROR`` … ``ACTION_INVALID``）可由 WP5 重试协调器
    按白名单处理；评测类码（``RISK_MISMATCH`` … ``EVAL_SKIPPED``）仅用于 L7
    批跑，**不得**传入重试协调器。
    """

    PARSE_ERROR = "PARSE_ERROR"
    FIELD_MISSING = "FIELD_MISSING"
    TYPE_ERROR = "TYPE_ERROR"
    ENUM_INVALID = "ENUM_INVALID"
    EXTRA_FIELD = "EXTRA_FIELD"
    VALUE_ERROR = "VALUE_ERROR"
    ACTION_INVALID = "ACTION_INVALID"
    ACTION_ROUTE_MISMATCH = "ACTION_ROUTE_MISMATCH"
    ACTION_LABEL_MISMATCH = "ACTION_LABEL_MISMATCH"
    RISK_MISMATCH = "RISK_MISMATCH"
    CONFIDENCE_MISMATCH = "CONFIDENCE_MISMATCH"
    CASE_OUTPUT_MISSING = "CASE_OUTPUT_MISSING"
    EVAL_SKIPPED = "EVAL_SKIPPED"

    # --- L5 内容守卫（guard，WP5 ValidateContent）---
    EMERGENCY_TONE_WEAK = "EMERGENCY_TONE_WEAK"
    EVIDENCE_HALLUCINATION = "EVIDENCE_HALLUCINATION"
    RISK_TEXT_INCONSISTENT = "RISK_TEXT_INCONSISTENT"
    FORCED_MENTION_MISSING = "FORCED_MENTION_MISSING"

    # --- 语义评测（L7 semantic_eval，WP0 续项）---
    MUST_MENTION_MISSING = "MUST_MENTION_MISSING"
    MUST_NOT_MENTION_HIT = "MUST_NOT_MENTION_HIT"
    FORBIDDEN_PATTERN_HIT = "FORBIDDEN_PATTERN_HIT"
    SAFETY_NOTICE_REQUIRED_MISSING = "SAFETY_NOTICE_REQUIRED_MISSING"
    SEMANTIC_EVAL_SKIPPED = "SEMANTIC_EVAL_SKIPPED"


ViolationCodeLiteral = Literal[
    "PARSE_ERROR",
    "FIELD_MISSING",
    "TYPE_ERROR",
    "ENUM_INVALID",
    "EXTRA_FIELD",
    "VALUE_ERROR",
    "ACTION_INVALID",
    "ACTION_ROUTE_MISMATCH",
    "ACTION_LABEL_MISMATCH",
    "RISK_MISMATCH",
    "CONFIDENCE_MISMATCH",
    "CASE_OUTPUT_MISSING",
    "EVAL_SKIPPED",
    # --- L5 内容守卫 ---
    "EMERGENCY_TONE_WEAK",
    "EVIDENCE_HALLUCINATION",
    "RISK_TEXT_INCONSISTENT",
    "FORCED_MENTION_MISSING",
    # --- 语义评测 ---
    "MUST_MENTION_MISSING",
    "MUST_NOT_MENTION_HIT",
    "FORBIDDEN_PATTERN_HIT",
    "SAFETY_NOTICE_REQUIRED_MISSING",
    "SEMANTIC_EVAL_SKIPPED",
]


class ViolationSeverity(StrEnum):
    """违规严重度；结构错误在 WP0 阶段统一视为 HIGH。"""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


ViolationSeverityLiteral = Literal["HIGH", "MEDIUM", "LOW"]


class Violation(BaseModel):
    """单条契约或评测违规记录。"""

    model_config = ConfigDict(extra="forbid")

    code: ViolationCodeLiteral = Field(description="机器可读的违规类型码。")
    domain: ViolationDomainLiteral = Field(
        default="schema",
        description=(
            "违规来源域：schema（契约结构）、guard（内容守卫）、"
            "risk_eval（risk-only 评测）、semantic_eval（语义评测，待实现）。"
        ),
    )
    path: str = Field(
        description="JSON 字段路径，如 ``pet.ageMonths`` 或 ``primaryAction.label``。",
    )
    field: str | None = Field(
        default=None,
        description="顶层字段名（便于报告聚合）；无法解析时为 null。",
    )
    message: str = Field(description="人类可读说明（中文）。")
    severity: ViolationSeverityLiteral = Field(
        default="HIGH",
        description="严重度；Schema 校验器默认均为 HIGH。",
    )


class ValidationResult(BaseModel, Generic[TParsed]):
    """单次 Schema 校验结果。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    passed: bool = Field(description="是否通过契约结构校验。")
    schema_kind: SchemaKindLiteral = Field(description="本次校验的契约种类。")
    schema_version: str = Field(description="对照的 schema 版本标识。")
    mode: OutputValidationModeLiteral | None = Field(
        default=None,
        description="输出校验模式；输入校验时为 null。",
    )
    violations: list[Violation] = Field(
        default_factory=list,
        description="全部违规项；通过时为空列表。",
    )
    parsed: TParsed | None = Field(
        default=None,
        description="校验通过时解析得到的强类型对象。",
    )


class CaseInputValidationRecord(BaseModel, Generic[TParsed]):
    """单条 case 入参的结构校验记录（批跑辅助）。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    case_id: str = Field(alias="caseId", description="case 唯一标识。")
    result: ValidationResult[TParsed] = Field(description="该 case 入参的校验结果。")
