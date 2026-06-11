"""机械健康分诊管道核心编排（WP5 阶段 2 — 重试协调器接入）。

串联 ① 解析 → ② 分诊 → ③-1 模板 → **WP5 文案重试协调器**（含 ④ ValidateContent）
→ ⑤ 合并（含 Merge 阶段兜底）→ 出站 schema 校验。

包内子模块使用；包外请通过 ``xiaozhua_health_agent.pipeline`` 门面调用。
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine, Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any

from xiaozhua_health_agent.copy import (
    CopyKnowledgeBundle,
    CopyTemplateResolved,
    DraftCopyJSON,
    MechanicalDraftWarning,
    generate_mechanical_draft,
    resolve_copy_template,
)
from xiaozhua_health_agent.eval import Violation
from xiaozhua_health_agent.input_lex import (
    InputLexCorpusBuildError,
    InputLexEnrichError,
    InputLexEnrichResult,
    InputLexLoadError,
    enrich_agent_input_payload_async,
)
from xiaozhua_health_agent.guard import ContentGuardMode, ContentGuardResult
from xiaozhua_health_agent.parse import ParseResult, parse_input
from xiaozhua_health_agent.pipeline.merge_fallback import (
    MergeValidateWithFallbackResult,
    merge_and_validate_with_fallback_async,
)
from xiaozhua_health_agent.pipeline.pipeline_types import (
    HealthTriagePipelineOptions,
    HealthTriagePipelineResult,
    HealthTriagePipelineStage,
    MechanicalPipelineArtifacts,
)
from xiaozhua_health_agent.pipeline.retry_coordinator import (
    run_draft_retry_coordinator_async,
)
from xiaozhua_health_agent.pipeline.retry_types import (
    DraftRetryOutcome,
    build_draft_retry_context,
)
from xiaozhua_health_agent.schemas import AgentInput
from xiaozhua_health_agent.triage import TriageCoreResult, run_triage_core

__all__ = [
    "run_mechanical_health_triage_core",
    "run_mechanical_health_triage_core_async",
]


def run_mechanical_health_triage_core(
    agent_input: AgentInput | Mapping[str, Any],
    *,
    options: HealthTriagePipelineOptions,
    copy_bundle: CopyKnowledgeBundle | None,
) -> HealthTriagePipelineResult:
    """执行机械路径健康分诊管道（同步入口）。

    内部通过 ``asyncio.run`` 委托 :func:`run_mechanical_health_triage_core_async`；
    在已有事件循环的上下文（如 FastAPI 协程内）请直接调用异步版本。

    :param agent_input: App / mock case 输入 JSON 或 ``AgentInput`` 模型。
    :type agent_input: AgentInput | collections.abc.Mapping[str, Any]
    :param options: 管道运行配置。
    :type options: HealthTriagePipelineOptions
    :param copy_bundle: 已解析的 KB-TPL 知识包；可为 ``None``（③-1 使用加载器默认）。
    :type copy_bundle: CopyKnowledgeBundle | None
    :returns: 管道执行结果（含 ``passed``、``stage``、``output`` 等）。
    :rtype: HealthTriagePipelineResult
    """
    return _run_async_pipeline_from_sync(
        run_mechanical_health_triage_core_async(
            agent_input,
            options=options,
            copy_bundle=copy_bundle,
        ),
    )


def _run_async_pipeline_from_sync(
    coroutine: Coroutine[Any, Any, HealthTriagePipelineResult],
) -> HealthTriagePipelineResult:
    """在同步上下文中执行管道异步协程（内部辅助）。

    若当前线程无运行中事件循环，使用 ``asyncio.run``；否则在独立线程内
    ``asyncio.run``，避免 ``pytest-asyncio`` 等宿主内嵌套运行失败。

    :param coroutine: 待执行的管道协程对象。
    :type coroutine: collections.abc.Coroutine[Any, Any, HealthTriagePipelineResult]
    :returns: 协程完成后的管道结果。
    :rtype: HealthTriagePipelineResult
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    def _run_in_isolated_loop() -> HealthTriagePipelineResult:
        """在子线程新事件循环中运行管道协程（闭包）。

        :returns: 管道执行结果。
        :rtype: HealthTriagePipelineResult
        """
        return asyncio.run(coroutine)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_in_isolated_loop)
        return future.result()


async def run_mechanical_health_triage_core_async(
    agent_input: AgentInput | Mapping[str, Any],
    *,
    options: HealthTriagePipelineOptions,
    copy_bundle: CopyKnowledgeBundle | None,
) -> HealthTriagePipelineResult:
    """执行机械路径健康分诊管道（异步核心）。

    在 ③ 文案阶段委托 ``run_draft_retry_coordinator_async`` 完成
    「生成 → ValidateContent → 确定性修补 / 机械兜底」有界循环；
    ⑤ 合并阶段委托 ``merge_and_validate_with_fallback_async`` 完成
    Merge 阶段机械兜底；**不修改** ``TriageCoreResult`` 裁决字段。

    :param agent_input: App / mock case 输入 JSON 或 ``AgentInput`` 模型。
    :type agent_input: AgentInput | collections.abc.Mapping[str, Any]
    :param options: 管道运行配置。
    :type options: HealthTriagePipelineOptions
    :param copy_bundle: 已解析的 KB-TPL 知识包；可为 ``None``。
    :type copy_bundle: CopyKnowledgeBundle | None
    :returns: 管道执行结果。
    :rtype: HealthTriagePipelineResult
    """
    case_id = _extract_case_id(agent_input)
    input_lex_enrich: InputLexEnrichResult | None = None
    payload_for_parse: AgentInput | Mapping[str, Any] = agent_input

    if options.input_lex_enabled:
        try:
            input_lex_enrich = await enrich_agent_input_payload_async(
                _coerce_payload_mapping(agent_input),
                bundle=options.input_lex_bundle,
                load_default_bundle=options.load_default_input_lex_bundle,
                options=options.resolved_input_lex_enrich_options(),
            )
            payload_for_parse = input_lex_enrich.enriched_payload
        except (InputLexEnrichError, InputLexCorpusBuildError, InputLexLoadError) as exc:
            return _build_enrich_failure_result(
                case_id=case_id,
                error_message=str(exc),
            )

    parsed = parse_input(payload_for_parse)
    if not parsed.passed or parsed.fact_sheet is None:
        return _build_parse_failure_result(
            case_id=case_id,
            parsed=parsed,
            input_lex_enrich=input_lex_enrich,
        )

    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=copy_bundle,
    )

    if options.skip_content_guard:
        result = await _run_skip_guard_path_async(
            case_id=case_id,
            parsed=parsed,
            triage=triage,
            resolved=resolved,
            options=options,
        )
        return _attach_input_lex_enrich(result, input_lex_enrich)

    retry_context = build_draft_retry_context(
        parsed=parsed,
        triage=triage,
        resolved=resolved,
        copy_bundle=copy_bundle,
        case_id=case_id,
    )
    retry_outcome = await run_draft_retry_coordinator_async(
        retry_context,
        options=options.resolved_draft_retry_options(),
    )

    if not retry_outcome.passed or retry_outcome.draft is None:
        failure = _build_retry_coordinator_failure_result(
            case_id=case_id,
            parsed=parsed,
            triage=triage,
            resolved=resolved,
            retry_outcome=retry_outcome,
        )
        return _attach_input_lex_enrich(failure, input_lex_enrich)

    guard_result = retry_outcome.last_guard_result
    guard_warnings = _resolve_guard_warnings(
        guard_result=guard_result,
        options=options,
    )

    result = await _merge_and_validate_async(
        case_id=case_id,
        parsed=parsed,
        triage=triage,
        resolved=resolved,
        draft=retry_outcome.draft,
        mechanical_warnings=(),
        template_id=resolved.template_id,
        options=options,
        guard_result=guard_result,
        guard_warnings=guard_warnings,
        attempt_count=retry_outcome.attempt_count,
        used_mechanical_fallback=retry_outcome.used_mechanical_fallback,
    )
    return _attach_input_lex_enrich(result, input_lex_enrich)


async def _run_skip_guard_path_async(
    *,
    case_id: str,
    parsed: ParseResult,
    triage: TriageCoreResult,
    resolved: CopyTemplateResolved,
    options: HealthTriagePipelineOptions,
) -> HealthTriagePipelineResult:
    """调试路径：跳过协调器与 ValidateContent，直接机械文案后合并（内部辅助）。

    :param case_id: 用例标识。
    :type case_id: str
    :param parsed: 步骤 ① 解析结果。
    :type parsed: ParseResult
    :param triage: 步骤 ② 分诊结论。
    :type triage: TriageCoreResult
    :param resolved: 步骤 ③-1 模板解析包。
    :type resolved: CopyTemplateResolved
    :param options: 管道配置。
    :type options: HealthTriagePipelineOptions
    :returns: 合并与校验后的管道结果。
    :rtype: HealthTriagePipelineResult
    """

    def _generate_mechanical() -> tuple[
        DraftCopyJSON, tuple[MechanicalDraftWarning, ...]
    ]:
        """在线程池执行机械文案生成（闭包）。

        :returns: ``(draft, warnings)`` 元组。
        :rtype: tuple[DraftCopyJSON, tuple[MechanicalDraftWarning, ...]]
        """
        mechanical_result = generate_mechanical_draft(
            resolved,
            options=options.resolved_mechanical_options(),
        )
        return mechanical_result.draft, mechanical_result.warnings

    draft, mechanical_warnings = await asyncio.to_thread(_generate_mechanical)

    return await _merge_and_validate_async(
        case_id=case_id,
        parsed=parsed,
        triage=triage,
        resolved=resolved,
        draft=draft,
        mechanical_warnings=mechanical_warnings,
        template_id=resolved.template_id,
        options=options,
        guard_result=None,
        guard_warnings=(),
        attempt_count=0,
        used_mechanical_fallback=False,
    )


def _build_retry_coordinator_failure_result(
    *,
    case_id: str,
    parsed: ParseResult,
    triage: TriageCoreResult,
    resolved: CopyTemplateResolved,
    retry_outcome: DraftRetryOutcome,
) -> HealthTriagePipelineResult:
    """构建重试协调器未产出可合并 draft 时的管道失败结果（内部辅助）。

    :param case_id: 用例标识。
    :type case_id: str
    :param parsed: 步骤 ① 解析结果。
    :type parsed: ParseResult
    :param triage: 步骤 ② 分诊结论。
    :type triage: TriageCoreResult
    :param resolved: 步骤 ③-1 模板解析包。
    :type resolved: CopyTemplateResolved
    :param retry_outcome: 协调器终止 outcome。
    :type retry_outcome: DraftRetryOutcome
    :returns: ``stage=guard`` 的管道失败结果。
    :rtype: HealthTriagePipelineResult
    """
    last_draft = retry_outcome.draft
    if last_draft is None and retry_outcome.last_guard_result is not None:
        last_draft = retry_outcome.last_guard_result.draft

    artifacts: MechanicalPipelineArtifacts | None = None
    if last_draft is not None:
        artifacts = MechanicalPipelineArtifacts(
            parse_result=parsed,
            triage=triage,
            resolved=resolved,
            draft=last_draft,
            template_id=resolved.template_id,
            mechanical_warnings=(),
        )

    error_message = (
        retry_outcome.error_message
        or "DraftCopyJSON 未通过 WP5 文案重试协调器（ValidateContent / 兜底）。"
    )

    return HealthTriagePipelineResult(
        passed=False,
        case_id=case_id,
        stage=HealthTriagePipelineStage.GUARD,
        output=None,
        violations=retry_outcome.last_violations,
        triage=triage,
        artifacts=artifacts,
        primary_flag=triage.primary_flag,
        bundle_version=triage.bundle_version,
        guard_result=retry_outcome.last_guard_result,
        guard_warnings=(),
        attempt_count=retry_outcome.attempt_count,
        used_mechanical_fallback=retry_outcome.used_mechanical_fallback,
        error_message=error_message,
    )


def _resolve_guard_warnings(
    *,
    guard_result: ContentGuardResult | None,
    options: HealthTriagePipelineOptions,
) -> tuple[Violation, ...]:
    """按 ``guard_mode`` 解析应写入管道结果的守卫警告副本（内部辅助）。

    :param guard_result: 协调器最后一轮 ValidateContent 结果。
    :type guard_result: ContentGuardResult | None
    :param options: 管道配置。
    :type options: HealthTriagePipelineOptions
    :returns: ``report_only`` 下未阻断的违规副本，或协调器 ``warnings``。
    :rtype: tuple[Violation, ...]
    """
    if guard_result is None:
        return ()

    if options.guard_mode == ContentGuardMode.REPORT_ONLY and not guard_result.passed:
        return guard_result.violations

    if len(guard_result.warnings) > 0:
        return guard_result.warnings

    return ()


async def _merge_and_validate_async(
    *,
    case_id: str,
    parsed: ParseResult,
    triage: TriageCoreResult,
    resolved: CopyTemplateResolved,
    draft: DraftCopyJSON,
    mechanical_warnings: tuple[MechanicalDraftWarning, ...],
    template_id: str,
    options: HealthTriagePipelineOptions,
    guard_result: ContentGuardResult | None = None,
    guard_warnings: tuple[Violation, ...] = (),
    attempt_count: int = 0,
    used_mechanical_fallback: bool = False,
) -> HealthTriagePipelineResult:
    """合并 ② 与 ③ 文案并执行出站 schema 校验（含 Merge 阶段兜底，内部辅助）。

    :param case_id: 用例标识。
    :type case_id: str
    :param parsed: 步骤 ① 解析结果。
    :type parsed: ParseResult
    :param triage: 步骤 ② 分诊结论。
    :type triage: TriageCoreResult
    :param resolved: 步骤 ③-1 模板解析包。
    :type resolved: CopyTemplateResolved
    :param draft: 经协调器审查后的文案草稿。
    :type draft: DraftCopyJSON
    :param mechanical_warnings: 机械文案组装警告。
    :type mechanical_warnings: tuple[MechanicalDraftWarning, ...]
    :param template_id: 模板主键。
    :type template_id: str
    :param options: 管道配置。
    :type options: HealthTriagePipelineOptions
    :param guard_result: 步骤 ④ ValidateContent 结果；跳过时为 ``None``。
    :type guard_result: ContentGuardResult | None
    :param guard_warnings: 未阻断管道的守卫警告。
    :type guard_warnings: tuple[Violation, ...]
    :param attempt_count: 协调器有效尝试次数。
    :type attempt_count: int
    :param used_mechanical_fallback: 协调器是否使用过终端机械兜底。
    :type used_mechanical_fallback: bool
    :returns: 合并与校验后的管道结果。
    :rtype: HealthTriagePipelineResult
    """
    merge_result = await merge_and_validate_with_fallback_async(
        triage=triage,
        draft=draft,
        resolved=resolved,
        options=options,
        mechanical_warnings=mechanical_warnings,
    )
    return _build_pipeline_result_from_merge(
        case_id=case_id,
        parsed=parsed,
        triage=triage,
        resolved=resolved,
        template_id=template_id,
        merge_result=merge_result,
        guard_result=guard_result,
        guard_warnings=guard_warnings,
        attempt_count=attempt_count,
        used_mechanical_fallback=used_mechanical_fallback,
    )


def _build_pipeline_result_from_merge(
    *,
    case_id: str,
    parsed: ParseResult,
    triage: TriageCoreResult,
    resolved: CopyTemplateResolved,
    template_id: str,
    merge_result: MergeValidateWithFallbackResult,
    guard_result: ContentGuardResult | None,
    guard_warnings: tuple[Violation, ...],
    attempt_count: int,
    used_mechanical_fallback: bool,
) -> HealthTriagePipelineResult:
    """将 ``MergeValidateWithFallbackResult`` 映射为 ``HealthTriagePipelineResult``。

    :param case_id: 用例标识。
    :type case_id: str
    :param parsed: 步骤 ① 解析结果。
    :type parsed: ParseResult
    :param triage: 步骤 ② 分诊结论。
    :type triage: TriageCoreResult
    :param resolved: 步骤 ③-1 模板解析包。
    :type resolved: CopyTemplateResolved
    :param template_id: 模板主键。
    :type template_id: str
    :param merge_result: Merge 阶段兜底合并结果。
    :type merge_result: MergeValidateWithFallbackResult
    :param guard_result: ValidateContent 结果。
    :type guard_result: ContentGuardResult | None
    :param guard_warnings: 守卫警告副本。
    :type guard_warnings: tuple[Violation, ...]
    :param attempt_count: 协调器尝试次数。
    :type attempt_count: int
    :param used_mechanical_fallback: 协调器机械兜底标志。
    :type used_mechanical_fallback: bool
    :returns: 管道执行结果。
    :rtype: HealthTriagePipelineResult
    """
    artifacts = MechanicalPipelineArtifacts(
        parse_result=parsed,
        triage=triage,
        resolved=resolved,
        draft=merge_result.draft,
        template_id=template_id,
        mechanical_warnings=merge_result.mechanical_warnings,
    )

    return HealthTriagePipelineResult(
        passed=merge_result.passed,
        case_id=case_id,
        stage=merge_result.stage,
        output=merge_result.output,
        violations=merge_result.violations,
        triage=triage,
        artifacts=artifacts,
        primary_flag=triage.primary_flag,
        bundle_version=triage.bundle_version,
        guard_result=guard_result,
        guard_warnings=guard_warnings,
        attempt_count=attempt_count,
        used_mechanical_fallback=used_mechanical_fallback,
        used_merge_fallback=merge_result.used_merge_fallback,
        merge_fallback_attempted=merge_result.merge_fallback_attempted,
        used_final_schema_recovery=merge_result.used_final_schema_recovery,
        final_schema_recovery_attempted=merge_result.final_schema_recovery_attempted,
        pre_recovery_output=merge_result.pre_recovery_output,
        pre_recovery_violations=merge_result.pre_recovery_violations,
        error_message=merge_result.error_message,
    )


def _build_enrich_failure_result(
    *,
    case_id: str,
    error_message: str,
) -> HealthTriagePipelineResult:
    """构建步骤 ⓪ enrich 失败结果（内部辅助）。

    :param case_id: 用例标识。
    :type case_id: str
    :param error_message: enrich 阶段错误说明。
    :type error_message: str
    :returns: ``stage=enrich`` 的管道失败结果。
    :rtype: HealthTriagePipelineResult
    """
    return HealthTriagePipelineResult(
        passed=False,
        case_id=case_id,
        stage=HealthTriagePipelineStage.ENRICH,
        output=None,
        error_message=error_message,
    )


def _build_parse_failure_result(
    *,
    case_id: str,
    parsed: ParseResult,
    input_lex_enrich: InputLexEnrichResult | None = None,
) -> HealthTriagePipelineResult:
    """构建步骤 ① 失败结果（内部辅助）。

    :param case_id: 用例标识。
    :type case_id: str
    :param parsed: 未通过的解析结果。
    :type parsed: ParseResult
    :param input_lex_enrich: 可选 enrich 阶段产物（enrich 已执行时保留）。
    :type input_lex_enrich: InputLexEnrichResult | None
    :returns: ``stage=parse`` 的管道失败结果。
    :rtype: HealthTriagePipelineResult
    """
    return HealthTriagePipelineResult(
        passed=False,
        case_id=case_id,
        stage=HealthTriagePipelineStage.PARSE,
        output=None,
        violations=tuple(parsed.violations),
        error_message="输入契约校验失败，未进入分诊管道。",
        input_lex_enrich=input_lex_enrich,
    )


def _attach_input_lex_enrich(
    result: HealthTriagePipelineResult,
    input_lex_enrich: InputLexEnrichResult | None,
) -> HealthTriagePipelineResult:
    """将 enrich 产物附加到管道结果（内部辅助）。

    :param result: 原始管道结果。
    :type result: HealthTriagePipelineResult
    :param input_lex_enrich: enrich 编排结果；未启用时为 ``None``。
    :type input_lex_enrich: InputLexEnrichResult | None
    :returns: 附加 ``input_lex_enrich`` 后的结果副本。
    :rtype: HealthTriagePipelineResult
    """
    if input_lex_enrich is None:
        return result
    return replace(result, input_lex_enrich=input_lex_enrich)


def _coerce_payload_mapping(
    agent_input: AgentInput | Mapping[str, Any],
) -> dict[str, Any]:
    """将入参规范化为 camelCase JSON 根字典（内部辅助）。

    :param agent_input: 强类型入参或 JSON 映射。
    :type agent_input: AgentInput | collections.abc.Mapping[str, Any]
    :returns: 可变的根字典副本。
    :rtype: dict[str, Any]
    """
    if isinstance(agent_input, AgentInput):
        return agent_input.model_dump(by_alias=True, mode="json")
    return dict(agent_input)


def _extract_case_id(agent_input: AgentInput | Mapping[str, Any]) -> str:
    """从入参提取 ``caseId``（内部辅助）。

    :param agent_input: 原始入参或强类型模型。
    :type agent_input: AgentInput | collections.abc.Mapping[str, Any]
    :returns: caseId 字符串；无法读取时返回 ``unknown``。
    :rtype: str
    """
    if isinstance(agent_input, AgentInput):
        return agent_input.case_id
    raw_case_id = agent_input.get("caseId")
    if isinstance(raw_case_id, str) and raw_case_id.strip():
        return raw_case_id.strip()
    return "unknown"
