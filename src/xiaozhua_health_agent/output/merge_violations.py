"""WP5 ⑤ MergeOutput 失败 — 结构化 ``Violation`` 映射。

将 ``MergeOutputError`` 与 Pydantic ``ValidationError`` 转为 ``eval.Violation``，
供 ``pipeline.merge_fallback`` 与 HTTP 错误体消费（``domain=schema``）。

包外请通过 ``xiaozhua_health_agent.output`` 门面导入公开符号。
"""

from __future__ import annotations

import asyncio
from typing import Final, cast

from pydantic import ValidationError

from xiaozhua_health_agent.eval import (
    Violation,
    ViolationCode,
    ViolationCodeLiteral,
    ViolationDomainLiteral,
    ViolationSeverity,
    violations_from_pydantic_validation_error,
)
from xiaozhua_health_agent.output.merge_types import (
    MergeOutputError,
    MergeOutputFailureKind,
    MergeOutputFailureKindLiteral,
)

__all__ = [
    "MERGE_SAFETY_NOTICE_MISSING_MESSAGE",
    "build_merge_output_error_for_safety_notice",
    "build_merge_output_error_for_validation",
    "make_merge_safety_notice_missing_violation",
    "violations_from_merge_output_error",
    "violations_from_merge_output_error_async",
]

_MERGE_VIOLATION_DOMAIN: Final[ViolationDomainLiteral] = "schema"
"""Merge 阶段违规统一归入 ``schema`` 域（与 merge-ready / FinalSchemaCheck 一致）。"""

MERGE_SAFETY_NOTICE_MISSING_MESSAGE: Final[str] = (
    "safetyNoticeRequired 为 true，但 DraftCopyJSON.safetyNotice 为空；"
    "应在 ③ 阶段写入免责声明片段后再合并。"
)
"""``merge_agent_output`` 在必填免责声明缺失时使用的默认说明。"""


def make_merge_safety_notice_missing_violation() -> Violation:
    """构造 merge 阶段「必填免责声明缺失」违规项。

    :returns: ``code=SAFETY_NOTICE_REQUIRED_MISSING``、``path=safetyNotice`` 的违规。
    :rtype: Violation
    """
    return Violation(
        code=cast(
            ViolationCodeLiteral,
            ViolationCode.SAFETY_NOTICE_REQUIRED_MISSING.value,
        ),
        domain=_MERGE_VIOLATION_DOMAIN,
        path="safetyNotice",
        field="safetyNotice",
        message=MERGE_SAFETY_NOTICE_MISSING_MESSAGE,
        severity=ViolationSeverity.HIGH.value,
    )


def build_merge_output_error_for_safety_notice(
    *,
    message: str | None = None,
) -> MergeOutputError:
    """构建「必填免责声明缺失」的 ``MergeOutputError``（含 violations）。

    :param message: 可选自定义说明；省略时使用 ``MERGE_SAFETY_NOTICE_MISSING_MESSAGE``。
    :type message: str | None
    :returns: 带结构化 ``violations`` 的合并异常。
    :rtype: MergeOutputError
    """
    resolved_message = (
        message if message is not None else MERGE_SAFETY_NOTICE_MISSING_MESSAGE
    )
    violation = make_merge_safety_notice_missing_violation()
    return MergeOutputError(
        resolved_message,
        violations=(violation,),
        failure_kind=MergeOutputFailureKind.SAFETY_NOTICE_REQUIRED_MISSING,
    )


def build_merge_output_error_for_validation(
    error: ValidationError,
    *,
    message: str | None = None,
) -> MergeOutputError:
    """将 ``AgentOutput.model_validate`` 的 ``ValidationError`` 包装为 ``MergeOutputError``。

    :param error: Pydantic 出站契约校验异常。
    :type error: pydantic.ValidationError
    :param message: 可选自定义顶层说明；省略时使用默认中文摘要。
    :type message: str | None
    :returns: 带逐字段 ``violations`` 的合并异常（``__cause__`` 链至 ``error``）。
    :rtype: MergeOutputError
    """
    violations = violations_from_pydantic_validation_error(
        error,
        domain=_MERGE_VIOLATION_DOMAIN,
    )
    resolved_message = message
    if resolved_message is None:
        resolved_message = (
            f"合并后的 AgentOutput 未通过契约校验（{error.error_count()} 项错误）。"
        )
    merge_error = MergeOutputError(
        resolved_message,
        violations=violations,
        failure_kind=MergeOutputFailureKind.AGENT_OUTPUT_VALIDATION_FAILED,
    )
    merge_error.__cause__ = error
    return merge_error


def violations_from_merge_output_error(
    error: MergeOutputError,
) -> tuple[Violation, ...]:
    """从 ``MergeOutputError`` 解析结构化违规列表（同步）。

    优先返回 ``error.violations``；若为空则按 ``failure_kind`` 或 ``__cause__``
    推导；仍无法识别时返回单条 ``VALUE_ERROR`` 兜底违规。

    :param error: ``merge_agent_output`` 抛出的合并异常。
    :type error: MergeOutputError
    :returns: 非空的违规元组。
    :rtype: tuple[Violation, ...]
    """
    if len(error.violations) > 0:
        return error.violations

    derived = _derive_violations_from_failure_kind(error.failure_kind)
    if derived:
        return derived

    cause = error.__cause__
    if isinstance(cause, ValidationError):
        return violations_from_pydantic_validation_error(
            cause,
            domain=_MERGE_VIOLATION_DOMAIN,
        )

    return (
        Violation(
            code=cast(ViolationCodeLiteral, ViolationCode.VALUE_ERROR.value),
            domain=_MERGE_VIOLATION_DOMAIN,
            path="$",
            field=None,
            message=error.message,
            severity=ViolationSeverity.HIGH.value,
        ),
    )


async def violations_from_merge_output_error_async(
    error: MergeOutputError,
) -> tuple[Violation, ...]:
    """从 ``MergeOutputError`` 解析结构化违规列表（异步；CPU 路径委托线程池）。

    :param error: ``merge_agent_output`` 抛出的合并异常。
    :type error: MergeOutputError
    :returns: 非空的违规元组。
    :rtype: tuple[Violation, ...]
    """

    def _map_in_thread() -> tuple[Violation, ...]:
        """在线程池执行违规映射（闭包）。

        :returns: 结构化违规元组。
        :rtype: tuple[Violation, ...]
        """
        return violations_from_merge_output_error(error)

    return await asyncio.to_thread(_map_in_thread)


def _derive_violations_from_failure_kind(
    failure_kind: MergeOutputFailureKindLiteral,
) -> tuple[Violation, ...]:
    """按 ``failure_kind`` 生成默认违规项（内部辅助）。

    :param failure_kind: 合并失败分类。
    :type failure_kind: MergeOutputFailureKindLiteral
    :returns: 可识别的违规元组；未知种类时为空。
    :rtype: tuple[Violation, ...]
    """
    if failure_kind == MergeOutputFailureKind.SAFETY_NOTICE_REQUIRED_MISSING:
        return (make_merge_safety_notice_missing_violation(),)
    return ()
