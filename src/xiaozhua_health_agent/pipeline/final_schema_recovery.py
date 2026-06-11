"""WP5 ⑤ FinalSchemaCheck 失败后的 recovery（机械文案再合并）。

当 ``merge_agent_output`` 已成功产出 ``AgentOutput``，但出站 ``output_schema``
全量校验（FinalSchemaCheck）未通过时，在**不修改** ``TriageCoreResult`` 裁决字段
的前提下，以 ``generate_mechanical_draft`` 重新生成 ``DraftCopyJSON`` 并再执行
一次合并与校验。

与 Merge 阶段兜底（``merge_fallback`` 中针对 ``merge`` / ``merge_ready`` 失败）
分离：本模块**仅**处理 ``stage=final_schema`` 的首次失败。

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
from xiaozhua_health_agent.eval import Violation
from xiaozhua_health_agent.pipeline.merge_fallback import (
    MergeValidateSingleAttemptResult,
    MergeValidateWithFallbackResult,
    attempt_merge_validate_in_thread_async,
)
from xiaozhua_health_agent.pipeline.pipeline_types import (
    HealthTriagePipelineOptions,
    HealthTriagePipelineStage,
    HealthTriagePipelineStageLiteral,
)
from xiaozhua_health_agent.schemas import AgentOutput
from xiaozhua_health_agent.triage import TriageCoreResult

__all__ = [
    "FINAL_SCHEMA_RECOVERY_ERROR_MESSAGE",
    "FinalSchemaRecoveryResult",
    "recover_from_final_schema_failure_async",
    "should_attempt_final_schema_recovery",
    "to_merge_validate_with_fallback_result",
]

_FINAL_SCHEMA_RECOVERY_ERROR_PREFIX: Final[str] = (
    "FinalSchemaCheck 未通过，且 FinalSchema 机械 recovery 仍未通过。"
)
"""FinalSchema recovery 耗尽后的错误消息前缀。"""

FINAL_SCHEMA_RECOVERY_ERROR_MESSAGE: Final[str] = (
    f"{_FINAL_SCHEMA_RECOVERY_ERROR_PREFIX}详见 violations 与 stage。"
)
"""FinalSchema recovery 失败时的默认 ``error_message`` 文案。"""


@dataclass(frozen=True, slots=True)
class FinalSchemaRecoveryResult:
    """FinalSchemaCheck 失败后的 recovery 执行结果。

    :ivar passed: recovery 后是否成功产出合法 ``AgentOutput``。
    :vartype passed: bool
    :ivar stage: 终止阶段；成功时为 ``completed``，仍失败时为 ``final_schema``。
    :vartype stage: HealthTriagePipelineStageLiteral
    :ivar output: 成功时的完整结构化输出。
    :vartype output: AgentOutput | None
    :ivar violations: recovery 仍失败时的违规列表；成功时为空。
    :vartype violations: tuple[Violation, ...]
    :ivar draft: recovery 最终用于合并的文案草稿（机械兜底产物）。
    :vartype draft: DraftCopyJSON
    :ivar mechanical_warnings: 机械文案组装警告。
    :vartype mechanical_warnings: tuple[MechanicalDraftWarning, ...]
    :ivar error_message: 失败说明；成功时为 ``None``。
    :vartype error_message: str | None
    :ivar used_final_schema_recovery: recovery 是否成功完成并产出合法 output。
    :vartype used_final_schema_recovery: bool
    :ivar final_schema_recovery_attempted: 是否曾执行 FinalSchema recovery（含仍失败）。
    :vartype final_schema_recovery_attempted: bool
    :ivar pre_recovery_output: 首次 FinalSchemaCheck 失败时已合并但未通过校验的 output。
    :vartype pre_recovery_output: AgentOutput | None
    :ivar pre_recovery_violations: 首次 FinalSchemaCheck 失败的 schema 违规副本。
    :vartype pre_recovery_violations: tuple[Violation, ...]
    """

    passed: bool
    stage: HealthTriagePipelineStageLiteral
    output: AgentOutput | None
    draft: DraftCopyJSON
    mechanical_warnings: tuple[MechanicalDraftWarning, ...]
    violations: tuple[Violation, ...] = ()
    error_message: str | None = None
    used_final_schema_recovery: bool = False
    final_schema_recovery_attempted: bool = False
    pre_recovery_output: AgentOutput | None = None
    pre_recovery_violations: tuple[Violation, ...] = ()


def should_attempt_final_schema_recovery(
    attempt: MergeValidateSingleAttemptResult,
    *,
    enable_final_schema_recovery: bool,
) -> bool:
    """判断是否应对首次失败尝试执行 FinalSchema recovery。

    仅当首次尝试 ``stage=final_schema``（合并已成功但出站 schema 未通过）且
    配置启用 recovery 时返回 ``True``。

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


async def recover_from_final_schema_failure_async(
    *,
    failed_attempt: MergeValidateSingleAttemptResult,
    triage: TriageCoreResult,
    resolved: CopyTemplateResolved,
    original_draft: DraftCopyJSON,
    options: HealthTriagePipelineOptions,
) -> FinalSchemaRecoveryResult:
    """在 FinalSchemaCheck 首次失败后，以机械文案执行一次 recovery。

    流程：

    1. 记录首次失败的 ``output`` 与 ``violations`` 作为 ``pre_recovery_*``；
    2. ``generate_mechanical_draft`` 生成兜底 ``DraftCopyJSON``；
    3. 再执行一次 merge + FinalSchemaCheck；
    4. **不修改** ``TriageCoreResult`` 任何裁决字段。

    :param failed_attempt: 首次失败的合并/校验结果（须 ``stage=final_schema``）。
    :type failed_attempt: MergeValidateSingleAttemptResult
    :param triage: 步骤 ② 锁定分诊结论。
    :type triage: TriageCoreResult
    :param resolved: 步骤 ③-1 模板解析包（机械填槽真源）。
    :type resolved: CopyTemplateResolved
    :param original_draft: 首次尝试使用的文案草稿（用于失败路径 artifacts 追溯）。
    :type original_draft: DraftCopyJSON
    :param options: 管道运行配置。
    :type options: HealthTriagePipelineOptions
    :returns: FinalSchema recovery 完整结果。
    :rtype: FinalSchemaRecoveryResult
    :raises ValueError: ``failed_attempt.stage`` 不是 ``final_schema`` 时抛出。
    """
    if failed_attempt.stage != HealthTriagePipelineStage.FINAL_SCHEMA:
        msg = (
            "recover_from_final_schema_failure_async 仅处理 stage=final_schema 的首次失败；"
            f"当前 stage={failed_attempt.stage!r}。"
        )
        raise ValueError(msg)

    pre_output = failed_attempt.output
    pre_violations = failed_attempt.violations

    mechanical_result = await _generate_mechanical_draft_for_recovery_async(
        resolved,
        mechanical_options=options.resolved_mechanical_options(),
    )
    recovery_draft = mechanical_result.draft
    recovery_warnings = mechanical_result.warnings

    merge_ready_options = options.resolved_merge_ready_options()
    recovery_attempt = await attempt_merge_validate_in_thread_async(
        triage=triage,
        draft=recovery_draft,
        skip_final_schema_check=options.skip_final_schema_check,
        skip_merge_ready_check=options.skip_merge_ready_check,
        merge_ready_options=merge_ready_options,
    )

    if recovery_attempt.passed:
        return FinalSchemaRecoveryResult(
            passed=True,
            stage=recovery_attempt.stage,
            output=recovery_attempt.output,
            draft=recovery_draft,
            mechanical_warnings=recovery_warnings,
            violations=(),
            error_message=None,
            used_final_schema_recovery=True,
            final_schema_recovery_attempted=True,
            pre_recovery_output=pre_output,
            pre_recovery_violations=pre_violations,
        )

    error_message = recovery_attempt.error_message
    if error_message is not None:
        error_message = f"{FINAL_SCHEMA_RECOVERY_ERROR_MESSAGE} {error_message}".strip()
    else:
        error_message = FINAL_SCHEMA_RECOVERY_ERROR_MESSAGE

    return FinalSchemaRecoveryResult(
        passed=False,
        stage=recovery_attempt.stage,
        output=recovery_attempt.output,
        draft=recovery_draft,
        mechanical_warnings=recovery_warnings,
        violations=recovery_attempt.violations,
        error_message=error_message,
        used_final_schema_recovery=False,
        final_schema_recovery_attempted=True,
        pre_recovery_output=pre_output,
        pre_recovery_violations=pre_violations,
    )


def to_merge_validate_with_fallback_result(
    recovery: FinalSchemaRecoveryResult,
    *,
    original_draft: DraftCopyJSON,
    original_mechanical_warnings: tuple[MechanicalDraftWarning, ...],
) -> MergeValidateWithFallbackResult:
    """将 ``FinalSchemaRecoveryResult`` 转为 ``MergeValidateWithFallbackResult``。

    供 ``merge_and_validate_with_fallback_async`` 统一返回类型。

    :param recovery: FinalSchema recovery 执行结果。
    :type recovery: FinalSchemaRecoveryResult
    :param original_draft: 首次尝试前的文案草稿（recovery 失败且未替换时保留）。
    :type original_draft: DraftCopyJSON
    :param original_mechanical_warnings: 首次尝试前已有的机械文案警告。
    :type original_mechanical_warnings: tuple[MechanicalDraftWarning, ...]
    :returns: 与管道门面一致的合并/校验结果 DTO。
    :rtype: MergeValidateWithFallbackResult
    """
    draft = (
        recovery.draft if recovery.final_schema_recovery_attempted else original_draft
    )
    mechanical_warnings = (
        recovery.mechanical_warnings
        if recovery.final_schema_recovery_attempted
        else original_mechanical_warnings
    )

    return MergeValidateWithFallbackResult(
        passed=recovery.passed,
        stage=recovery.stage,
        output=recovery.output,
        draft=draft,
        mechanical_warnings=mechanical_warnings,
        violations=recovery.violations,
        error_message=recovery.error_message,
        used_merge_fallback=False,
        merge_fallback_attempted=False,
        used_final_schema_recovery=recovery.used_final_schema_recovery,
        final_schema_recovery_attempted=recovery.final_schema_recovery_attempted,
        pre_recovery_output=recovery.pre_recovery_output,
        pre_recovery_violations=recovery.pre_recovery_violations,
    )


async def _generate_mechanical_draft_for_recovery_async(
    resolved: CopyTemplateResolved,
    *,
    mechanical_options: MechanicalDraftOptions,
) -> MechanicalDraftResult:
    """在线程池中生成 FinalSchema recovery 用机械文案（内部辅助）。

    :param resolved: 步骤 ③-1 模板解析包。
    :type resolved: CopyTemplateResolved
    :param mechanical_options: 机械文案组装选项。
    :type mechanical_options: MechanicalDraftOptions
    :returns: 机械文案完整结果。
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
