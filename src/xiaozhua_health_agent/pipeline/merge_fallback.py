"""WP5 ⑤ Merge 阶段兜底 — 合并与 FinalSchemaCheck 有界重试。

当 ``merge_agent_output`` 或出站 ``output_schema`` 全量校验失败时，在**不修改**
``TriageCoreResult`` 裁决字段的前提下，以 ``generate_mechanical_draft`` 重新生成
``DraftCopyJSON`` 并再执行一次合并与校验。

包内子模块；包外请通过 ``xiaozhua_health_agent.pipeline`` 门面导入公开符号。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Final

from xiaozhua_health_agent.copy import (
    CopyTemplateResolved,
    DraftCopyJSON,
    MechanicalDraftOptions,
    MechanicalDraftResult,
    MechanicalDraftWarning,
    generate_mechanical_draft,
)
from xiaozhua_health_agent.eval import (
    OutputValidationMode,
    ValidationResult,
    Violation,
    validate_output,
)
from xiaozhua_health_agent.output import (
    MERGE_READY_ERROR_MESSAGE,
    MergeOutputError,
    MergeReadyOptions,
    check_merge_ready,
    merge_agent_output,
    violations_from_merge_output_error,
)
from xiaozhua_health_agent.pipeline.pipeline_types import (
    HealthTriagePipelineOptions,
    HealthTriagePipelineStage,
    HealthTriagePipelineStageLiteral,
)
from xiaozhua_health_agent.schemas import AgentOutput, RiskOnlyOutput
from xiaozhua_health_agent.triage import TriageCoreResult

__all__ = [
    "MERGE_FALLBACK_ERROR_MESSAGE",
    "MergeValidateSingleAttemptResult",
    "MergeValidateWithFallbackResult",
    "attempt_merge_and_validate_once",
    "attempt_merge_validate_in_thread_async",
    "generate_mechanical_draft_for_merge_fallback_async",
    "merge_and_validate_with_fallback_async",
    "should_attempt_merge_stage_fallback",
]

_MERGE_FALLBACK_ERROR_PREFIX: Final[str] = (
    "合并与出站 schema 校验失败，且 Merge 阶段机械兜底仍未通过。"
)
"""Merge 阶段兜底耗尽后的错误消息前缀。"""

MERGE_FALLBACK_ERROR_MESSAGE: Final[str] = (
    f"{_MERGE_FALLBACK_ERROR_PREFIX}详见 violations 与 stage。"
)
"""Merge 阶段兜底失败时的默认 ``error_message`` 文案。"""


@dataclass(frozen=True, slots=True)
class MergeValidateSingleAttemptResult:
    """单次「合并 + 可选 FinalSchemaCheck」尝试结果。

    :ivar passed: 是否已通过合并且（若启用）出站 schema 校验。
    :vartype passed: bool
    :ivar stage: 终止阶段；成功时为 ``completed``，失败时为 ``merge`` 或 ``final_schema``。
    :vartype stage: HealthTriagePipelineStageLiteral
    :ivar output: 成功时的 ``AgentOutput``；合并失败时为 ``None``；schema 失败时可能保留
        已合并但未通过校验的对象。
    :vartype output: AgentOutput | None
    :ivar violations: 出站 schema 或 merge 失败时的结构化违规；成功时为空。
    :vartype violations: tuple[Violation, ...]
    :ivar error_message: 人类可读失败说明；成功时为 ``None``。
    :vartype error_message: str | None
    """

    passed: bool
    stage: HealthTriagePipelineStageLiteral
    output: AgentOutput | None
    violations: tuple[Violation, ...] = ()
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class MergeValidateWithFallbackResult:
    """带 Merge 阶段兜底的合并与校验最终结果。

    :ivar passed: 是否成功产出合法 ``AgentOutput``。
    :vartype passed: bool
    :ivar stage: 管道终止阶段。
    :vartype stage: HealthTriagePipelineStageLiteral
    :ivar output: 成功时的完整结构化输出。
    :vartype output: AgentOutput | None
    :ivar violations: 失败时的违规列表。
    :vartype violations: tuple[Violation, ...]
    :ivar draft: 最终用于合并的文案草稿（可能经兜底替换）。
    :vartype draft: DraftCopyJSON
    :ivar mechanical_warnings: 若触发 Merge 兜底，为机械文案组装警告；否则为调用方传入值。
    :vartype mechanical_warnings: tuple[MechanicalDraftWarning, ...]
    :ivar error_message: 失败说明；成功时为 ``None``。
    :vartype error_message: str | None
    :ivar used_merge_fallback: 是否执行过 Merge 阶段机械兜底并成功或仍失败。
    :vartype used_merge_fallback: bool
    :ivar merge_fallback_attempted: 是否曾尝试 Merge 阶段兜底（含失败情形）。
    :vartype merge_fallback_attempted: bool
    :ivar used_final_schema_recovery: FinalSchema recovery 是否成功完成。
    :vartype used_final_schema_recovery: bool
    :ivar final_schema_recovery_attempted: 是否曾尝试 FinalSchema recovery（含仍失败）。
    :vartype final_schema_recovery_attempted: bool
    :ivar pre_recovery_output: FinalSchema recovery 前已合并但未通过校验的 output。
    :vartype pre_recovery_output: AgentOutput | None
    :ivar pre_recovery_violations: FinalSchema recovery 前首次 schema 失败违规副本。
    :vartype pre_recovery_violations: tuple[Violation, ...]
    """

    passed: bool
    stage: HealthTriagePipelineStageLiteral
    output: AgentOutput | None
    draft: DraftCopyJSON
    mechanical_warnings: tuple[MechanicalDraftWarning, ...]
    violations: tuple[Violation, ...] = ()
    error_message: str | None = None
    used_merge_fallback: bool = False
    merge_fallback_attempted: bool = False
    used_final_schema_recovery: bool = False
    final_schema_recovery_attempted: bool = False
    pre_recovery_output: AgentOutput | None = None
    pre_recovery_violations: tuple[Violation, ...] = ()


def attempt_merge_and_validate_once(
    *,
    triage: TriageCoreResult,
    draft: DraftCopyJSON,
    skip_final_schema_check: bool,
    skip_merge_ready_check: bool = False,
    merge_ready_options: MergeReadyOptions | None = None,
) -> MergeValidateSingleAttemptResult:
    """执行单次 merge-ready 预检、合并与可选 FinalSchemaCheck（同步 CPU 路径）。

    供 ``asyncio.to_thread`` 在线程池中调用，避免阻塞事件循环。

    :param triage: 步骤 ② 锁定分诊结论。
    :type triage: TriageCoreResult
    :param draft: 步骤 ③ 文案草稿。
    :type draft: DraftCopyJSON
    :param skip_final_schema_check: 为 ``True`` 时合并成功后跳过 FULL schema 校验。
    :type skip_final_schema_check: bool
    :param skip_merge_ready_check: 为 ``True`` 时跳过 merge-ready 契约预检（仅调试）。
    :type skip_merge_ready_check: bool
    :param merge_ready_options: merge-ready 校验配置；省略时使用默认配置。
    :type merge_ready_options: MergeReadyOptions | None
    :returns: 单次尝试结果。
    :rtype: MergeValidateSingleAttemptResult
    """
    if not skip_merge_ready_check:
        ready = check_merge_ready(
            draft,
            triage,
            options=merge_ready_options,
        )
        if not ready.passed:
            return MergeValidateSingleAttemptResult(
                passed=False,
                stage=HealthTriagePipelineStage.MERGE_READY,
                output=None,
                violations=ready.violations,
                error_message=MERGE_READY_ERROR_MESSAGE,
            )

    try:
        output = merge_agent_output(triage=triage, draft=draft)
    except MergeOutputError as exc:
        return MergeValidateSingleAttemptResult(
            passed=False,
            stage=HealthTriagePipelineStage.MERGE,
            output=None,
            violations=violations_from_merge_output_error(exc),
            error_message=str(exc),
        )

    if skip_final_schema_check:
        return MergeValidateSingleAttemptResult(
            passed=True,
            stage=HealthTriagePipelineStage.COMPLETED,
            output=output,
            violations=(),
            error_message=None,
        )

    schema_check = validate_output(
        output,
        mode=OutputValidationMode.FULL,
    )
    if not schema_check.passed:
        return MergeValidateSingleAttemptResult(
            passed=False,
            stage=HealthTriagePipelineStage.FINAL_SCHEMA,
            output=output,
            violations=tuple(schema_check.violations),
            error_message="合并后的 AgentOutput 未通过 output_schema 全量校验。",
        )

    coerced = _coerce_validated_agent_output(schema_check, fallback=output)
    return MergeValidateSingleAttemptResult(
        passed=True,
        stage=HealthTriagePipelineStage.COMPLETED,
        output=coerced,
        violations=(),
        error_message=None,
    )


async def generate_mechanical_draft_for_merge_fallback_async(
    resolved: CopyTemplateResolved,
    *,
    mechanical_options: MechanicalDraftOptions,
) -> MechanicalDraftResult:
    """在线程池中生成 Merge 阶段兜底用机械文案。

    :param resolved: 步骤 ③-1 模板解析包。
    :type resolved: CopyTemplateResolved
    :param mechanical_options: 机械文案组装选项。
    :type mechanical_options: MechanicalDraftOptions
    :returns: 机械文案完整结果（含 ``draft`` 与 ``warnings``）。
    :rtype: MechanicalDraftResult
    """

    def _generate_in_thread() -> MechanicalDraftResult:
        """在线程池执行机械文案生成（闭包）。

        :returns: 机械文案组装结果。
        :rtype: MechanicalDraftResult
        """
        return generate_mechanical_draft(
            resolved,
            options=mechanical_options,
        )

    return await asyncio.to_thread(_generate_in_thread)


def should_attempt_merge_stage_fallback(
    attempt: MergeValidateSingleAttemptResult,
    *,
    enable_merge_fallback: bool,
) -> bool:
    """判断是否应对首次失败尝试执行 Merge 阶段机械兜底。

    仅当 ``stage`` 为 ``merge_ready`` 或 ``merge`` 且配置启用兜底时返回 ``True``。
    ``final_schema`` 失败由 ``final_schema_recovery`` 模块处理。

    :param attempt: 首次 merge + FinalSchemaCheck 尝试结果。
    :type attempt: MergeValidateSingleAttemptResult
    :param enable_merge_fallback: 管道是否启用 Merge 阶段兜底。
    :type enable_merge_fallback: bool
    :returns: 应执行 Merge 阶段兜底时为 ``True``。
    :rtype: bool
    """
    if not enable_merge_fallback:
        return False
    if attempt.passed:
        return False
    return attempt.stage in (
        HealthTriagePipelineStage.MERGE_READY,
        HealthTriagePipelineStage.MERGE,
    )


def _should_attempt_final_schema_recovery(
    attempt: MergeValidateSingleAttemptResult,
    *,
    enable_final_schema_recovery: bool,
) -> bool:
    """判断是否应对首次失败尝试执行 FinalSchema recovery（内部辅助）。

    :param attempt: 首次 merge + FinalSchemaCheck 尝试结果。
    :type attempt: MergeValidateSingleAttemptResult
    :param enable_final_schema_recovery: 管道是否启用 FinalSchema recovery。
    :type enable_final_schema_recovery: bool
    :returns: 应执行 recovery 时为 ``True``。
    :rtype: bool
    """
    if not enable_final_schema_recovery:
        return False
    if attempt.passed:
        return False
    return attempt.stage == HealthTriagePipelineStage.FINAL_SCHEMA


async def merge_and_validate_with_fallback_async(
    *,
    triage: TriageCoreResult,
    draft: DraftCopyJSON,
    resolved: CopyTemplateResolved,
    options: HealthTriagePipelineOptions,
    mechanical_warnings: tuple[MechanicalDraftWarning, ...] = (),
) -> MergeValidateWithFallbackResult:
    """合并 ② 与 ③ 并执行 FinalSchemaCheck；按失败阶段选择 recovery 策略。

    流程：

    1. 对当前 ``draft`` 执行一次 ``attempt_merge_and_validate_once``；
    2. 若 ``stage=final_schema`` 且启用 recovery → ``final_schema_recovery``；
    3. 若 ``stage=merge`` / ``merge_ready`` 且启用兜底 → Merge 阶段机械兜底；
    4. **不修改** ``TriageCoreResult`` 任何裁决字段。

    :param triage: 步骤 ② 锁定分诊结论。
    :type triage: TriageCoreResult
    :param draft: 经协调器或调用方提供的文案草稿。
    :type draft: DraftCopyJSON
    :param resolved: 步骤 ③-1 模板解析包（兜底填槽真源）。
    :type resolved: CopyTemplateResolved
    :param options: 管道运行配置。
    :type options: HealthTriagePipelineOptions
    :param mechanical_warnings: 首次尝试前已有的机械文案警告；未触发 recovery 时原样返回。
    :type mechanical_warnings: tuple[MechanicalDraftWarning, ...]
    :returns: 含最终 ``draft``、Merge 兜底与 FinalSchema recovery 标志的完整结果。
    :rtype: MergeValidateWithFallbackResult
    """
    skip_schema = options.skip_final_schema_check
    merge_ready_options = options.resolved_merge_ready_options()
    first_attempt = await attempt_merge_validate_in_thread_async(
        triage=triage,
        draft=draft,
        skip_final_schema_check=skip_schema,
        skip_merge_ready_check=options.skip_merge_ready_check,
        merge_ready_options=merge_ready_options,
    )

    if first_attempt.passed:
        return MergeValidateWithFallbackResult(
            passed=True,
            stage=first_attempt.stage,
            output=first_attempt.output,
            draft=draft,
            mechanical_warnings=mechanical_warnings,
            violations=(),
            error_message=None,
            used_merge_fallback=False,
            merge_fallback_attempted=False,
            used_final_schema_recovery=False,
            final_schema_recovery_attempted=False,
        )

    if _should_attempt_final_schema_recovery(
        first_attempt,
        enable_final_schema_recovery=options.enable_final_schema_recovery,
    ):
        from xiaozhua_health_agent.pipeline.final_schema_recovery import (
            recover_from_final_schema_failure_async,
            to_merge_validate_with_fallback_result,
        )

        recovery_result = await recover_from_final_schema_failure_async(
            failed_attempt=first_attempt,
            triage=triage,
            resolved=resolved,
            original_draft=draft,
            options=options,
        )
        return to_merge_validate_with_fallback_result(
            recovery_result,
            original_draft=draft,
            original_mechanical_warnings=mechanical_warnings,
        )

    if should_attempt_merge_stage_fallback(
        first_attempt,
        enable_merge_fallback=options.enable_merge_fallback,
    ):
        return await _execute_merge_stage_fallback_async(
            triage=triage,
            resolved=resolved,
            options=options,
            original_draft=draft,
            original_mechanical_warnings=mechanical_warnings,
        )

    return _build_failure_from_single_attempt(
        attempt=first_attempt,
        draft=draft,
        mechanical_warnings=mechanical_warnings,
        used_merge_fallback=False,
        merge_fallback_attempted=False,
    )


async def _execute_merge_stage_fallback_async(
    *,
    triage: TriageCoreResult,
    resolved: CopyTemplateResolved,
    options: HealthTriagePipelineOptions,
    original_draft: DraftCopyJSON,
    original_mechanical_warnings: tuple[MechanicalDraftWarning, ...],
) -> MergeValidateWithFallbackResult:
    """在 Merge / merge-ready 首次失败后执行机械兜底（内部辅助）。

    :param triage: 步骤 ② 锁定分诊结论。
    :type triage: TriageCoreResult
    :param resolved: 步骤 ③-1 模板解析包。
    :type resolved: CopyTemplateResolved
    :param options: 管道运行配置。
    :type options: HealthTriagePipelineOptions
    :param original_draft: 首次尝试使用的文案草稿。
    :type original_draft: DraftCopyJSON
    :param original_mechanical_warnings: 首次尝试前已有的机械文案警告。
    :type original_mechanical_warnings: tuple[MechanicalDraftWarning, ...]
    :returns: Merge 阶段兜底后的合并/校验结果。
    :rtype: MergeValidateWithFallbackResult
    """
    skip_schema = options.skip_final_schema_check
    merge_ready_options = options.resolved_merge_ready_options()

    mechanical_result = await generate_mechanical_draft_for_merge_fallback_async(
        resolved,
        mechanical_options=options.resolved_mechanical_options(),
    )
    fallback_draft = mechanical_result.draft
    fallback_warnings = mechanical_result.warnings

    second_attempt = await attempt_merge_validate_in_thread_async(
        triage=triage,
        draft=fallback_draft,
        skip_final_schema_check=skip_schema,
        skip_merge_ready_check=options.skip_merge_ready_check,
        merge_ready_options=merge_ready_options,
    )

    if second_attempt.passed:
        return MergeValidateWithFallbackResult(
            passed=True,
            stage=second_attempt.stage,
            output=second_attempt.output,
            draft=fallback_draft,
            mechanical_warnings=fallback_warnings,
            violations=(),
            error_message=None,
            used_merge_fallback=True,
            merge_fallback_attempted=True,
            used_final_schema_recovery=False,
            final_schema_recovery_attempted=False,
        )

    return _build_failure_from_single_attempt(
        attempt=second_attempt,
        draft=fallback_draft,
        mechanical_warnings=fallback_warnings,
        used_merge_fallback=True,
        merge_fallback_attempted=True,
        prefix_error=MERGE_FALLBACK_ERROR_MESSAGE,
    )


async def attempt_merge_validate_in_thread_async(
    *,
    triage: TriageCoreResult,
    draft: DraftCopyJSON,
    skip_final_schema_check: bool,
    skip_merge_ready_check: bool,
    merge_ready_options: MergeReadyOptions,
) -> MergeValidateSingleAttemptResult:
    """在线程池中执行 merge-ready 预检、合并与校验（内部辅助）。

    :param triage: 步骤 ② 锁定分诊结论。
    :type triage: TriageCoreResult
    :param draft: 文案草稿。
    :type draft: DraftCopyJSON
    :param skip_final_schema_check: 是否跳过 FULL schema 校验。
    :type skip_final_schema_check: bool
    :param skip_merge_ready_check: 是否跳过 merge-ready 预检。
    :type skip_merge_ready_check: bool
    :param merge_ready_options: merge-ready 校验配置。
    :type merge_ready_options: MergeReadyOptions
    :returns: 单次尝试结果。
    :rtype: MergeValidateSingleAttemptResult
    """

    def _run_attempt() -> MergeValidateSingleAttemptResult:
        """在线程池执行 merge-ready、合并与校验（闭包）。

        :returns: 单次尝试结果。
        :rtype: MergeValidateSingleAttemptResult
        """
        return attempt_merge_and_validate_once(
            triage=triage,
            draft=draft,
            skip_final_schema_check=skip_final_schema_check,
            skip_merge_ready_check=skip_merge_ready_check,
            merge_ready_options=merge_ready_options,
        )

    return await asyncio.to_thread(_run_attempt)


def _build_failure_from_single_attempt(
    *,
    attempt: MergeValidateSingleAttemptResult,
    draft: DraftCopyJSON,
    mechanical_warnings: tuple[MechanicalDraftWarning, ...],
    used_merge_fallback: bool,
    merge_fallback_attempted: bool,
    prefix_error: str | None = None,
) -> MergeValidateWithFallbackResult:
    """由单次失败尝试构建 ``MergeValidateWithFallbackResult``（内部辅助）。

    :param attempt: 失败的单次合并/校验结果。
    :type attempt: MergeValidateSingleAttemptResult
    :param draft: 本次尝试使用的文案草稿。
    :type draft: DraftCopyJSON
    :param mechanical_warnings: 机械文案警告。
    :type mechanical_warnings: tuple[MechanicalDraftWarning, ...]
    :param used_merge_fallback: 是否已使用 Merge 阶段兜底路径。
    :type used_merge_fallback: bool
    :param merge_fallback_attempted: 是否曾尝试 Merge 兜底。
    :type merge_fallback_attempted: bool
    :param prefix_error: 可选错误前缀；省略时使用 ``attempt.error_message``。
    :type prefix_error: str | None
    :returns: 失败时的兜底结果 DTO。
    :rtype: MergeValidateWithFallbackResult
    """
    error_message = attempt.error_message
    if prefix_error is not None:
        detail = attempt.error_message or ""
        error_message = f"{prefix_error} {detail}".strip()

    return MergeValidateWithFallbackResult(
        passed=False,
        stage=attempt.stage,
        output=attempt.output,
        draft=draft,
        mechanical_warnings=mechanical_warnings,
        violations=attempt.violations,
        error_message=error_message,
        used_merge_fallback=used_merge_fallback,
        merge_fallback_attempted=merge_fallback_attempted,
    )


def _coerce_validated_agent_output(
    schema_check: ValidationResult[AgentOutput | RiskOnlyOutput],
    *,
    fallback: AgentOutput,
) -> AgentOutput:
    """从 schema 校验结果取出强类型 ``AgentOutput``（内部辅助）。

    :param schema_check: 出站 schema 校验结果。
    :type schema_check: ValidationResult[AgentOutput | RiskOnlyOutput]
    :param fallback: 校验通过但 ``parsed`` 非 ``AgentOutput`` 时的回退对象。
    :type fallback: AgentOutput
    :returns: 校验后的输出模型。
    :rtype: AgentOutput
    """
    parsed = schema_check.parsed
    if isinstance(parsed, AgentOutput):
        return parsed
    return fallback
