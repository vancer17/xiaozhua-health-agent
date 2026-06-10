"""语义评测违规码常量、严重度映射与 ``Violation`` 工厂函数（WP0 续项）。

本模块是 L7 语义评测与 ``ViolationCode`` 扩展之间的桥梁：所有语义维度检查器
与 ``semantic_eval_types`` 组装逻辑应通过此处工厂构造 ``domain=semantic_eval``
的违规记录，以保持 ``code`` / ``severity`` / ``path`` 约定一致。

设计依据：

- ``docs/plans/coze-workflow-dev-plan.md`` § WP0 语义评测器
- ``docs/schema/xiaozhua_health_agent_output_schema.v1.json`` ``forbiddenOutputPatterns``
- ``eval/validation_result.py`` — 共用 ``Violation`` / ``ViolationCode`` 底座
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, Literal, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.eval.validation_result import (
    Violation,
    ViolationCode,
    ViolationCodeLiteral,
    ViolationDomainLiteral,
    ViolationSeverityLiteral,
)

# ---------------------------------------------------------------------------
# 常量与类型别名
# ---------------------------------------------------------------------------

SEMANTIC_EVAL_DOMAIN: ViolationDomainLiteral = "semantic_eval"
"""语义评测违规固定来源域；对应 ``ViolationDomain.SEMANTIC_EVAL``。"""

SemanticViolationCodeLiteral: TypeAlias = Literal[
    "MUST_MENTION_MISSING",
    "MUST_NOT_MENTION_HIT",
    "FORBIDDEN_PATTERN_HIT",
    "SAFETY_NOTICE_REQUIRED_MISSING",
    "SEMANTIC_EVAL_SKIPPED",
]
"""语义评测专用 ``ViolationCode`` 字面量联合类型。"""

SEMANTIC_VIOLATION_CODES: Final[frozenset[SemanticViolationCodeLiteral]] = frozenset(
    {
        "MUST_MENTION_MISSING",
        "MUST_NOT_MENTION_HIT",
        "FORBIDDEN_PATTERN_HIT",
        "SAFETY_NOTICE_REQUIRED_MISSING",
        "SEMANTIC_EVAL_SKIPPED",
    }
)
"""全部语义评测违规码集合，供报告聚合与门禁断言使用。"""

DEFAULT_SEMANTIC_VIOLATION_SEVERITY: Final[
    Mapping[SemanticViolationCodeLiteral, ViolationSeverityLiteral]
] = {
    "MUST_MENTION_MISSING": "MEDIUM",
    "MUST_NOT_MENTION_HIT": "HIGH",
    "FORBIDDEN_PATTERN_HIT": "HIGH",
    "SAFETY_NOTICE_REQUIRED_MISSING": "HIGH",
    "SEMANTIC_EVAL_SKIPPED": "LOW",
}
"""各语义违规码的默认严重度；工厂函数在未显式传入 ``severity`` 时采用此表。"""


# ---------------------------------------------------------------------------
# 辅助模型（工厂入参 / 报告 details 共用）
# ---------------------------------------------------------------------------


class SemanticTextHit(BaseModel):
    """单条文本命中记录（禁止词 / mustNotMention / forbidden pattern）。"""

    model_config = ConfigDict(extra="forbid")

    keyword: str = Field(
        min_length=1,
        description="命中的关键词或禁止 pattern 原文。",
    )
    field_path: str = Field(
        min_length=1,
        description=(
            "命中所在 JSON 字段路径，如 ``summary``、``evidence[0]``、"
            "``primaryAction.label``。"
        ),
    )
    snippet: str | None = Field(
        default=None,
        description="可选；命中处前后若干字的摘录，便于批跑报告人工复核。",
    )


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _format_case_suffix(case_id: str | None) -> str:
    """为违规 ``message`` 追加可选 caseId 后缀。

    :param case_id: 可选 case 唯一标识；为 ``None`` 时不追加后缀。
    :type case_id: str | None
    :returns: 空字符串或 ``（case: {case_id}）`` 形式后缀。
    :rtype: str
    """
    if case_id is None:
        return ""
    return f"（case: {case_id}）"


def _resolve_semantic_severity(
    code: SemanticViolationCodeLiteral,
    *,
    severity: ViolationSeverityLiteral | None,
) -> ViolationSeverityLiteral:
    """解析语义违规的最终严重度。

    :param code: 语义违规类型码。
    :type code: SemanticViolationCodeLiteral
    :param severity: 调用方显式指定的严重度；为 ``None`` 时使用默认映射表。
    :type severity: ViolationSeverityLiteral | None
    :returns: 最终写入 ``Violation.severity`` 的字面量。
    :rtype: ViolationSeverityLiteral
    """
    if severity is not None:
        return severity
    return DEFAULT_SEMANTIC_VIOLATION_SEVERITY[code]


def _build_semantic_violation(
    *,
    code: SemanticViolationCodeLiteral,
    path: str,
    message: str,
    field: str | None = None,
    severity: ViolationSeverityLiteral | None = None,
) -> Violation:
    """构造 ``domain=semantic_eval`` 的 ``Violation``（内部统一入口）。

    :param code: 语义违规类型码。
    :type code: SemanticViolationCodeLiteral
    :param path: JSON 字段路径或逻辑路径（如 ``$.textCorpus``）。
    :type path: str
    :param message: 人类可读中文说明。
    :type message: str
    :param field: 可选顶层字段名，便于 ``count_violations_by_code`` 聚合。
    :type field: str | None
    :param severity: 可选严重度；省略时使用 ``DEFAULT_SEMANTIC_VIOLATION_SEVERITY``。
    :type severity: ViolationSeverityLiteral | None
    :returns: ``domain`` 固定为 ``semantic_eval`` 的违规记录。
    :rtype: Violation
    """
    resolved_severity = _resolve_semantic_severity(code, severity=severity)
    return Violation(
        code=code,
        domain=SEMANTIC_EVAL_DOMAIN,
        path=path,
        field=field,
        message=message,
        severity=resolved_severity,
    )


# ---------------------------------------------------------------------------
# 判定辅助（报告 / 门禁）
# ---------------------------------------------------------------------------


def is_semantic_eval_violation_code(
    code: ViolationCodeLiteral,
) -> bool:
    """判断给定违规码是否属于语义评测专用集合。

    :param code: 任意 ``ViolationCodeLiteral`` 字符串。
    :type code: ViolationCodeLiteral
    :returns: 若 ``code`` 在 ``SEMANTIC_VIOLATION_CODES`` 内则为 ``True``。
    :rtype: bool
    """
    return code in SEMANTIC_VIOLATION_CODES


def is_semantic_eval_violation(violation: Violation) -> bool:
    """判断单条 ``Violation`` 是否来自语义评测域。

    :param violation: 待判定的违规记录。
    :type violation: Violation
    :returns: ``domain`` 为 ``semantic_eval`` 且 ``code`` 为语义专用码时为 ``True``。
    :rtype: bool
    """
    return violation.domain == SEMANTIC_EVAL_DOMAIN and is_semantic_eval_violation_code(
        violation.code
    )


def violation_code_from_enum(
    code: ViolationCode,
) -> ViolationCodeLiteral:
    """将 ``ViolationCode`` 枚举成员转为 Pydantic 使用的字面量字符串。

    :param code: ``ViolationCode`` 枚举成员。
    :type code: ViolationCode
    :returns: 与枚举值相同的 ``ViolationCodeLiteral`` 字符串。
    :rtype: ViolationCodeLiteral
    """
    return cast(ViolationCodeLiteral, code.value)


def semantic_violation_code_from_enum(
    code: ViolationCode,
) -> SemanticViolationCodeLiteral:
    """将语义类 ``ViolationCode`` 枚举成员转为语义专用字面量。

    :param code: 须为 ``MUST_MENTION_MISSING`` 等语义成员之一。
    :type code: ViolationCode
    :returns: 对应的 ``SemanticViolationCodeLiteral`` 字符串。
    :rtype: SemanticViolationCodeLiteral
    :raises ValueError: ``code`` 不在 ``SEMANTIC_VIOLATION_CODES`` 内时抛出。
    """
    value = violation_code_from_enum(code)
    if not is_semantic_eval_violation_code(value):
        msg = f"ViolationCode {code!r} 不是语义评测专用码。"
        raise ValueError(msg)
    return cast(SemanticViolationCodeLiteral, value)


# ---------------------------------------------------------------------------
# 公开工厂函数
# ---------------------------------------------------------------------------


def make_must_mention_missing_violation(
    *,
    missing_keywords: Sequence[str],
    case_id: str | None = None,
    severity: ViolationSeverityLiteral | None = None,
) -> Violation:
    """构造 ``mustMention`` 关键词未命中的违规记录。

    当 ``CaseExpected.mustMention`` 中任一关键词（经 KB-SYN 扩展后）未在
    输出语料中出现时产生；默认 ``severity=MEDIUM``，``domain=semantic_eval``。

    :param missing_keywords: 未命中的关键词列表；空列表时仍生成一条汇总违规
        （message 标明「无缺失项」，供调试一致性用，正常检查器不应传入空列表）。
    :type missing_keywords: collections.abc.Sequence[str]
    :param case_id: 可选 caseId，写入 ``message`` 便于批跑定位。
    :type case_id: str | None
    :param severity: 可选严重度；默认 ``MEDIUM``（软门槛维度）。
    :type severity: ViolationSeverityLiteral | None
    :returns: ``code=MUST_MENTION_MISSING`` 的违规记录。
    :rtype: Violation
    :raises ValueError: ``missing_keywords`` 为空时抛出。
    """
    if len(missing_keywords) == 0:
        msg = "missing_keywords 不能为空；无缺失时不应调用本工厂。"
        raise ValueError(msg)

    case_suffix = _format_case_suffix(case_id)
    joined = "、".join(repr(item) for item in missing_keywords)
    message = f"mustMention 关键词未命中：{joined}{case_suffix}"

    return _build_semantic_violation(
        code="MUST_MENTION_MISSING",
        path="$.textCorpus",
        field=None,
        message=message,
        severity=severity,
    )


def make_must_not_mention_hit_violation(
    *,
    keyword: str,
    field_path: str,
    case_id: str | None = None,
    snippet: str | None = None,
    severity: ViolationSeverityLiteral | None = None,
) -> Violation:
    """构造 ``mustNotMention`` 关键词命中的违规记录。

    当 ``CaseExpected.mustNotMention`` 中任一关键词出现在输出语料中时产生；
    默认 ``severity=HIGH``（硬门槛）。

    :param keyword: 命中的禁止关键词（来自 case expected）。
    :type keyword: str
    :param field_path: 命中所在字段路径，如 ``summary``。
    :type field_path: str
    :param case_id: 可选 caseId。
    :type case_id: str | None
    :param snippet: 可选命中上下文摘录。
    :type snippet: str | None
    :param severity: 可选严重度；默认 ``HIGH``。
    :type severity: ViolationSeverityLiteral | None
    :returns: ``code=MUST_NOT_MENTION_HIT`` 的违规记录。
    :rtype: Violation
    :raises ValueError: ``keyword`` 或 ``field_path`` 为空时抛出。
    """
    if not keyword.strip():
        raise ValueError("keyword 不能为空。")
    if not field_path.strip():
        raise ValueError("field_path 不能为空。")

    case_suffix = _format_case_suffix(case_id)
    snippet_part = f"，摘录：{snippet!r}" if snippet is not None else ""
    message = (
        f"mustNotMention 命中禁止词 {keyword!r}，"
        f"字段 {field_path!r}{snippet_part}{case_suffix}"
    )

    top_field = field_path.split(".", maxsplit=1)[0].split("[", maxsplit=1)[0]

    return _build_semantic_violation(
        code="MUST_NOT_MENTION_HIT",
        path=field_path,
        field=top_field if top_field else None,
        message=message,
        severity=severity,
    )


def make_must_not_mention_hits_violation(
    *,
    hits: Sequence[SemanticTextHit],
    case_id: str | None = None,
    severity: ViolationSeverityLiteral | None = None,
) -> Violation:
    """将多条 ``mustNotMention`` 命中合并为单条聚合违规（推荐批报格式）。

    :param hits: 至少一条文本命中记录。
    :type hits: collections.abc.Sequence[SemanticTextHit]
    :param case_id: 可选 caseId。
    :type case_id: str | None
    :param severity: 可选严重度；默认 ``HIGH``。
    :type severity: ViolationSeverityLiteral | None
    :returns: 单条聚合 ``MUST_NOT_MENTION_HIT`` 违规。
    :rtype: Violation
    :raises ValueError: ``hits`` 为空时抛出。
    """
    if len(hits) == 0:
        raise ValueError("hits 不能为空。")

    case_suffix = _format_case_suffix(case_id)
    parts: list[str] = []
    for hit in hits:
        snippet_part = f"，摘录：{hit.snippet!r}" if hit.snippet is not None else ""
        parts.append(f"{hit.keyword!r}@{hit.field_path}{snippet_part}")

    joined = "；".join(parts)
    first_path = hits[0].field_path
    top_field = first_path.split(".", maxsplit=1)[0].split("[", maxsplit=1)[0]

    return _build_semantic_violation(
        code="MUST_NOT_MENTION_HIT",
        path=first_path if len(hits) == 1 else "$.textCorpus",
        field=top_field if top_field else None,
        message=f"mustNotMention 命中：{joined}{case_suffix}",
        severity=severity,
    )


def make_forbidden_pattern_hit_violation(
    *,
    pattern: str,
    field_path: str,
    case_id: str | None = None,
    snippet: str | None = None,
    severity: ViolationSeverityLiteral | None = None,
) -> Violation:
    """构造全局禁止 pattern 命中的违规记录。

    对照 ``output_schema.forbiddenOutputPatterns`` 或 KB-FORBID 扩展表；
    默认 ``severity=HIGH``（硬门槛）。

    :param pattern: 命中的禁止表述 pattern 原文。
    :type pattern: str
    :param field_path: 命中所在字段路径。
    :type field_path: str
    :param case_id: 可选 caseId。
    :type case_id: str | None
    :param snippet: 可选命中上下文摘录。
    :type snippet: str | None
    :param severity: 可选严重度；默认 ``HIGH``。
    :type severity: ViolationSeverityLiteral | None
    :returns: ``code=FORBIDDEN_PATTERN_HIT`` 的违规记录。
    :rtype: Violation
    :raises ValueError: ``pattern`` 或 ``field_path`` 为空时抛出。
    """
    if not pattern.strip():
        raise ValueError("pattern 不能为空。")
    if not field_path.strip():
        raise ValueError("field_path 不能为空。")

    case_suffix = _format_case_suffix(case_id)
    snippet_part = f"，摘录：{snippet!r}" if snippet is not None else ""
    message = (
        f"命中禁止表述 {pattern!r}，字段 {field_path!r}{snippet_part}{case_suffix}"
    )

    top_field = field_path.split(".", maxsplit=1)[0].split("[", maxsplit=1)[0]

    return _build_semantic_violation(
        code="FORBIDDEN_PATTERN_HIT",
        path=field_path,
        field=top_field if top_field else None,
        message=message,
        severity=severity,
    )


def make_forbidden_pattern_hits_violation(
    *,
    hits: Sequence[SemanticTextHit],
    case_id: str | None = None,
    severity: ViolationSeverityLiteral | None = None,
) -> Violation:
    """将多条禁止 pattern 命中合并为单条聚合违规。

    :param hits: 至少一条命中记录；``keyword`` 字段存放 pattern 原文。
    :type hits: collections.abc.Sequence[SemanticTextHit]
    :param case_id: 可选 caseId。
    :type case_id: str | None
    :param severity: 可选严重度；默认 ``HIGH``。
    :type severity: ViolationSeverityLiteral | None
    :returns: 单条聚合 ``FORBIDDEN_PATTERN_HIT`` 违规。
    :rtype: Violation
    :raises ValueError: ``hits`` 为空时抛出。
    """
    if len(hits) == 0:
        raise ValueError("hits 不能为空。")

    case_suffix = _format_case_suffix(case_id)
    parts: list[str] = []
    for hit in hits:
        snippet_part = f"，摘录：{hit.snippet!r}" if hit.snippet is not None else ""
        parts.append(f"{hit.keyword!r}@{hit.field_path}{snippet_part}")

    joined = "；".join(parts)
    first_path = hits[0].field_path
    top_field = first_path.split(".", maxsplit=1)[0].split("[", maxsplit=1)[0]

    return _build_semantic_violation(
        code="FORBIDDEN_PATTERN_HIT",
        path=first_path if len(hits) == 1 else "$.textCorpus",
        field=top_field if top_field else None,
        message=f"禁止表述命中：{joined}{case_suffix}",
        severity=severity,
    )


def make_safety_notice_required_missing_violation(
    *,
    min_length: int,
    actual_length: int,
    case_id: str | None = None,
    severity: ViolationSeverityLiteral | None = None,
) -> Violation:
    """构造 ``safetyNoticeRequired=true`` 但 ``safetyNotice`` 无效的违规记录。

    当 ``CaseExpected.safetyNoticeRequired`` 为 ``True``，而输出 ``safetyNotice``
    为空、仅空白或长度低于 ``min_length`` 时产生；默认 ``severity=HIGH``。

    :param min_length: 配置的最小有效长度（如 8）。
    :type min_length: int
    :param actual_length: 实际 ``safetyNotice`` 归一化后的长度。
    :type actual_length: int
    :param case_id: 可选 caseId。
    :type case_id: str | None
    :param severity: 可选严重度；默认 ``HIGH``。
    :type severity: ViolationSeverityLiteral | None
    :returns: ``code=SAFETY_NOTICE_REQUIRED_MISSING`` 的违规记录。
    :rtype: Violation
    :raises ValueError: ``min_length`` 小于 1 时抛出。
    """
    if min_length < 1:
        raise ValueError("min_length 必须 >= 1。")

    case_suffix = _format_case_suffix(case_id)
    message = (
        f"safetyNoticeRequired 为 true，但 safetyNotice 无效："
        f"要求最小长度 {min_length}，实际长度 {actual_length}{case_suffix}"
    )

    return _build_semantic_violation(
        code="SAFETY_NOTICE_REQUIRED_MISSING",
        path="safetyNotice",
        field="safetyNotice",
        message=message,
        severity=severity,
    )


def make_semantic_eval_skipped_violation(
    *,
    reason: str,
    case_id: str | None = None,
    severity: ViolationSeverityLiteral | None = None,
) -> Violation:
    """构造因前置条件失败而跳过语义评测的违规记录。

    典型场景：FULL ``output_schema`` 未通过、批跑缺完整输出等；
    默认 ``severity=LOW``。与 ``risk_eval`` 的 ``EVAL_SKIPPED`` 区分域与码。

    :param reason: 跳过原因（如「output 未通过 full schema 校验」）。
    :type reason: str
    :param case_id: 可选 caseId。
    :type case_id: str | None
    :param severity: 可选严重度；默认 ``LOW``。
    :type severity: ViolationSeverityLiteral | None
    :returns: ``code=SEMANTIC_EVAL_SKIPPED`` 的违规记录。
    :rtype: Violation
    :raises ValueError: ``reason`` 为空时抛出。
    """
    if not reason.strip():
        raise ValueError("reason 不能为空。")

    case_suffix = _format_case_suffix(case_id)
    message = f"跳过语义评测：{reason}{case_suffix}"

    return _build_semantic_violation(
        code="SEMANTIC_EVAL_SKIPPED",
        path="$",
        field=None,
        message=message,
        severity=severity,
    )
