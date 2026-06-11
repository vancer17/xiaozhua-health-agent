"""WP5 文案重试协调器 — ``run_draft_retry_coordinator`` 状态机（``pipeline-design.md`` §6.2）。

在 ③ 文案生成与 ④ ValidateContent 之间编排 **有界循环**：校验 → 分类 →
确定性修补 / LLM 重试 / 终端机械兜底；**不修改** ``TriageCoreResult``。

包外请通过 ``xiaozhua_health_agent.pipeline`` 门面导入
``run_draft_retry_coordinator`` / ``run_draft_retry_coordinator_async``。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import Any, Final, cast

from xiaozhua_health_agent.copy import (
    AsyncQwenClient,
    DraftCopyJSON,
    MechanicalDraftResult,
    generate_mechanical_draft,
)
from xiaozhua_health_agent.eval import Violation
from xiaozhua_health_agent.guard import (
    ContentGuardInput,
    ContentGuardMode,
    ContentGuardResult,
    validate_content_async,
    validate_content_with_sanitize_async,
)
from xiaozhua_health_agent.pipeline.deterministic_repair import (
    apply_deterministic_repair_async,
)
from xiaozhua_health_agent.pipeline.llm_draft_generation import (
    LlmDraftGenerationError,
    generate_guard_repair_llm_draft_async,
    generate_initial_llm_draft_async,
)
from xiaozhua_health_agent.pipeline.retry_types import (
    DEFAULT_DRAFT_RETRY_OPTIONS,
    DraftRetryAttemptRecord,
    DraftRetryContext,
    DraftRetryGeneratorKind,
    DraftRetryGeneratorKindLiteral,
    DraftRetryOptions,
    DraftRetryOutcome,
    RetryAction,
    RetryActionLiteral,
)
from xiaozhua_health_agent.pipeline.violation_classifier import (
    ClassifyViolationsResult,
    classify_violations_detailed,
)

__all__ = [
    "DraftRetryCoordinatorState",
    "run_draft_retry_coordinator",
    "run_draft_retry_coordinator_async",
]

_INITIAL_ACTION_BEFORE_VALIDATE: Final[RetryActionLiteral] = RetryAction.ACCEPT.value
"""首轮校验前尚未执行 corrective 动作时的记录占位。"""

_LOOP_SAFETY_MARGIN: Final[int] = 5
"""在 ``max_attempts`` 之上允许的额外循环步数（确定性修补不计次时的保护）。"""


@dataclass(frozen=True, slots=True)
class DraftRetryCoordinatorState:
    """协调器循环内部可变状态快照（调试 / 单测用，非公开 DTO）。

    :ivar attempt_index: 当前尝试序号（1-based，用于 ``classify_violations`` 预算）。
    :vartype attempt_index: int
    :ivar llm_generation_count: 已执行的 LLM 全文案生成次数（含重试）。
    :vartype llm_generation_count: int
    :ivar draft: 当前文案草稿。
    :vartype draft: DraftCopyJSON
    :ivar generator: 当前文案生成器种类。
    :vartype generator: DraftRetryGeneratorKindLiteral
    :ivar used_mechanical_fallback: 是否已使用终端机械兜底。
    :vartype used_mechanical_fallback: bool
    :ivar history: 各轮校验记录（按时间序追加）。
    :vartype history: list[DraftRetryAttemptRecord]
    :ivar last_guard_result: 最近一轮 ``ContentGuardResult``。
    :vartype last_guard_result: ContentGuardResult | None
    """

    attempt_index: int
    llm_generation_count: int
    draft: DraftCopyJSON
    generator: DraftRetryGeneratorKindLiteral
    used_mechanical_fallback: bool
    history: list[DraftRetryAttemptRecord]
    last_guard_result: ContentGuardResult | None = None


def run_draft_retry_coordinator(
    context: DraftRetryContext,
    *,
    options: DraftRetryOptions | None = None,
    qwen_client: AsyncQwenClient | None = None,
) -> DraftRetryOutcome:
    """执行 WP5 文案重试协调器状态机（同步入口）。

    内部通过 ``asyncio.run`` 委托异步实现；在已有事件循环的上下文（如
    FastAPI 协程内）请直接调用 :func:`run_draft_retry_coordinator_async`。

    :param context: 协调器只读上下文（须含已解析 ``fact_sheet``）。
    :type context: DraftRetryContext
    :param options: 协调器配置；省略时使用 ``DEFAULT_DRAFT_RETRY_OPTIONS``。
    :type options: DraftRetryOptions | None
    :param qwen_client: 可选通义客户端；``llm_enabled=True`` 且省略时使用默认构造。
    :type qwen_client: AsyncQwenClient | None
    :returns: 协调器执行结果（含最终 ``draft`` 与 ``violations_history``）。
    :rtype: DraftRetryOutcome
    :raises ValueError: ``context.parsed.fact_sheet`` 为空时抛出。
    """
    return asyncio.run(
        run_draft_retry_coordinator_async(
            context,
            options=options,
            qwen_client=qwen_client,
        ),
    )


async def run_draft_retry_coordinator_async(
    context: DraftRetryContext,
    *,
    options: DraftRetryOptions | None = None,
    qwen_client: AsyncQwenClient | None = None,
) -> DraftRetryOutcome:
    """执行 WP5 文案重试协调器状态机（异步）。

    状态机主路径：

    1. **GENERATE** — 机械或 LLM 产出首稿 ``DraftCopyJSON``。
    2. **VALIDATE** — ``validate_content_async``（或 sanitize 模式）。
    3. 若通过 → **ACCEPT** → 返回 ``DraftRetryOutcome(passed=True)``。
    4. 否则 **CLASSIFY** → ``classify_violations_detailed``。
    5. 按 ``RetryAction`` 分支：**DETERMINISTIC_REPAIR** / **RETRY_LLM** /
       **MECHANICAL_FALLBACK** / **ABORT**；回到步骤 2 或终止。

    IO 密集步骤（guard 校验、LLM 调用、知识包加载）均走 ``await``；
    CPU 密集步骤（机械生成、确定性修补、违规分类）委托 ``asyncio.to_thread``。

    :param context: 协调器只读上下文。
    :type context: DraftRetryContext
    :param options: 协调器配置。
    :type options: DraftRetryOptions | None
    :param qwen_client: 可选通义客户端（``llm_enabled=True`` 时使用）。
    :type qwen_client: AsyncQwenClient | None
    :returns: 协调器执行结果。
    :rtype: DraftRetryOutcome
    :raises ValueError: ``context.parsed.fact_sheet`` 为空时抛出。
    """
    effective_options = options if options is not None else DEFAULT_DRAFT_RETRY_OPTIONS
    _assert_context_ready(context)

    initial = await _generate_initial_draft_async(
        context,
        options=effective_options,
        qwen_client=qwen_client,
    )

    state = DraftRetryCoordinatorState(
        attempt_index=1,
        llm_generation_count=initial.llm_generation_count,
        draft=initial.draft,
        generator=initial.generator,
        used_mechanical_fallback=False,
        history=[],
    )

    action_before_validate: RetryActionLiteral = _INITIAL_ACTION_BEFORE_VALIDATE
    max_loop_iterations = effective_options.max_attempts + _LOOP_SAFETY_MARGIN

    for _ in range(max_loop_iterations):
        guard_result = await _validate_draft_async(
            context,
            state.draft,
            options=effective_options,
        )
        state = _replace_coordinator_state(
            state,
            last_guard_result=guard_result,
        )

        round_passed = _coordinator_should_accept(
            guard_result,
            options=effective_options,
        )
        state.history.append(
            DraftRetryAttemptRecord(
                attempt_index=state.attempt_index,
                action_before_validate=action_before_validate,
                generator=state.generator,
                passed=round_passed,
                violations=guard_result.violations,
                sanitized=guard_result.sanitized,
            ),
        )

        if round_passed:
            return _build_success_outcome(
                state=state,
                draft=guard_result.draft,
                guard_result=guard_result,
                terminal_action=RetryAction.ACCEPT.value,
            )

        classification = await _classify_detailed_async(
            guard_result.violations,
            options=effective_options,
            attempt_index=state.attempt_index,
        )
        next_action = classification.action

        if next_action == RetryAction.ACCEPT:
            if (
                effective_options.allow_accept_with_med_warnings
                and guard_result.hard_passed
            ):
                return _build_success_outcome(
                    state=state,
                    draft=guard_result.draft,
                    guard_result=guard_result,
                    terminal_action=RetryAction.ACCEPT.value,
                )
            next_action = RetryAction(_mechanical_fallback_or_abort(effective_options))

        if next_action == RetryAction.ABORT:
            return _build_failure_outcome(
                state=state,
                guard_result=guard_result,
                terminal_action=RetryAction.ABORT.value,
                error_message="文案重试协调器收到 abort 动作，无法继续补救。",
            )

        step_result = await _execute_coordinator_action_async(
            context=context,
            state=state,
            options=effective_options,
            action=next_action,
            classification=classification,
            guard_result=guard_result,
            qwen_client=qwen_client,
        )

        state = step_result.state
        action_before_validate = cast(RetryActionLiteral, next_action.value)

        if step_result.terminal_outcome is not None:
            return step_result.terminal_outcome

    return _build_failure_outcome(
        state=state,
        guard_result=state.last_guard_result,
        terminal_action=RetryAction.ABORT.value,
        error_message=(
            f"文案重试协调器超过安全循环上限（{max_loop_iterations} 轮），已终止。"
        ),
    )


@dataclass(frozen=True, slots=True)
class _InitialDraftGeneration:
    """首轮文案生成结果（内部 DTO）。

    :ivar draft: 首稿 ``DraftCopyJSON``。
    :vartype draft: DraftCopyJSON
    :ivar generator: 使用的生成器种类。
    :vartype generator: DraftRetryGeneratorKindLiteral
    :ivar llm_generation_count: 本轮 LLM 调用次数（机械路径为 0）。
    :vartype llm_generation_count: int
    """

    draft: DraftCopyJSON
    generator: DraftRetryGeneratorKindLiteral
    llm_generation_count: int = 0


@dataclass(frozen=True, slots=True)
class _CoordinatorActionStepResult:
    """单步协调动作执行结果（内部 DTO）。

    :ivar state: 更新后的协调器状态。
    :vartype state: DraftRetryCoordinatorState
    :ivar terminal_outcome: 若本步直接终止协调器则非 ``None``。
    :vartype terminal_outcome: DraftRetryOutcome | None
    """

    state: DraftRetryCoordinatorState
    terminal_outcome: DraftRetryOutcome | None = None


def _assert_context_ready(context: DraftRetryContext) -> None:
    """校验协调器上下文具备 ``fact_sheet``（内部辅助）。

    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :raises ValueError: ``fact_sheet`` 缺失时抛出。
    """
    if context.parsed.fact_sheet is None:
        msg = "run_draft_retry_coordinator 要求 context.parsed.fact_sheet 非空。"
        raise ValueError(msg)


def _replace_coordinator_state(
    state: DraftRetryCoordinatorState,
    **updates: Any,
) -> DraftRetryCoordinatorState:
    """基于现有状态构造更新副本（内部辅助）。

    :param state: 当前状态。
    :type state: DraftRetryCoordinatorState
    :param updates: 要覆盖的字段键值（``dataclasses.replace`` 语义）。
    :returns: 新状态对象。
    :rtype: DraftRetryCoordinatorState
    """
    return replace(state, **updates)


async def _generate_initial_draft_async(
    context: DraftRetryContext,
    *,
    options: DraftRetryOptions,
    qwen_client: AsyncQwenClient | None,
) -> _InitialDraftGeneration:
    """执行首轮文案生成（机械或 LLM）（内部辅助）。

    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :param qwen_client: 可选通义客户端。
    :type qwen_client: AsyncQwenClient | None
    :returns: 首稿与生成器元数据。
    :rtype: _InitialDraftGeneration
    """
    if options.llm_enabled:
        return await _generate_initial_llm_draft_async(
            context,
            options=options,
            qwen_client=qwen_client,
        )

    mechanical = await _generate_mechanical_draft_async(
        context,
        options=options.resolved_mechanical_options(),
    )
    return _InitialDraftGeneration(
        draft=mechanical.draft,
        generator=DraftRetryGeneratorKind.MECHANICAL,
        llm_generation_count=0,
    )


async def _generate_initial_llm_draft_async(
    context: DraftRetryContext,
    *,
    options: DraftRetryOptions,
    qwen_client: AsyncQwenClient | None,
) -> _InitialDraftGeneration:
    """执行首轮 LLM 文案生成；失败时按 ``fallback_to_mechanical`` 降级（内部辅助）。

    委托 ``llm_draft_generation.generate_initial_llm_draft_async``（内层
    ``draft_retry`` 单次 LLM）；attempt 预算由外层 ``max_llm_retries`` 管理。

    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :param qwen_client: 可选通义客户端。
    :type qwen_client: AsyncQwenClient | None
    :returns: 首稿与生成器元数据。
    :rtype: _InitialDraftGeneration
    :raises RuntimeError: LLM 失败且 ``fallback_to_mechanical=False`` 时抛出。
    """
    try:
        initial = await generate_initial_llm_draft_async(
            context,
            options=options,
            qwen_client=qwen_client,
        )
    except LlmDraftGenerationError as exc:
        if not options.fallback_to_mechanical:
            msg = str(exc)
            raise RuntimeError(msg) from exc

        mechanical = await _generate_mechanical_fallback_async(
            context,
            options=options,
        )
        inner_count = 0
        if exc.inner_result is not None:
            inner_count = exc.inner_result.attempt_count
        return _InitialDraftGeneration(
            draft=mechanical.draft,
            generator=DraftRetryGeneratorKind.QWEN,
            llm_generation_count=inner_count,
        )

    return _InitialDraftGeneration(
        draft=initial.draft,
        generator=DraftRetryGeneratorKind.QWEN,
        llm_generation_count=initial.llm_call_count,
    )


async def _generate_mechanical_draft_async(
    context: DraftRetryContext,
    *,
    options: object,
) -> MechanicalDraftResult:
    """在线程池中执行机械文案生成（内部辅助）。

    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :param options: ``MechanicalDraftOptions`` 实例。
    :type options: object
    :returns: 机械文案结果。
    :rtype: MechanicalDraftResult
    """

    def _run_mechanical() -> MechanicalDraftResult:
        """执行同步机械文案生成（闭包）。

        :returns: 机械文案结果。
        :rtype: MechanicalDraftResult
        """
        return generate_mechanical_draft(context.resolved, options=options)  # type: ignore[arg-type]

    return await asyncio.to_thread(_run_mechanical)


async def _generate_mechanical_fallback_async(
    context: DraftRetryContext,
    *,
    options: DraftRetryOptions,
) -> MechanicalDraftResult:
    """在线程池中执行终端机械兜底文案生成（内部辅助）。

    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :returns: 强兜底机械文案结果。
    :rtype: MechanicalDraftResult
    """
    return await _generate_mechanical_draft_async(
        context,
        options=options.resolved_mechanical_fallback_options(),
    )


async def _validate_draft_async(
    context: DraftRetryContext,
    draft: DraftCopyJSON,
    *,
    options: DraftRetryOptions,
) -> ContentGuardResult:
    """对当前草稿执行 ValidateContent（异步，内部辅助）。

    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :param draft: 待审查文案草稿。
    :type draft: DraftCopyJSON
    :param options: 协调器配置（含 ``guard_mode`` / ``guard_options``）。
    :type options: DraftRetryOptions
    :returns: 内容守卫聚合结果。
    :rtype: ContentGuardResult
    """
    if context.parsed.fact_sheet is None:
        msg = "ValidateContent 需要 fact_sheet，但 context 中缺失。"
        raise ValueError(msg)

    guard_input = ContentGuardInput(
        draft=draft,
        triage=context.triage,
        fact_sheet=context.parsed.fact_sheet,
        resolved=context.resolved,
        copy_bundle=context.copy_bundle,
        synonym_map=context.synonym_map,
    )

    if options.guard_mode == ContentGuardMode.SANITIZE:
        return await validate_content_with_sanitize_async(
            guard_input,
            options=options.guard_options,
        )
    return await validate_content_async(
        guard_input,
        options=options.guard_options,
    )


def _coordinator_should_accept(
    guard_result: ContentGuardResult,
    *,
    options: DraftRetryOptions,
) -> bool:
    """按 ``guard_mode`` 判断当前轮是否可结束协调器（内部辅助）。

    :param guard_result: 本轮 ValidateContent 结果。
    :type guard_result: ContentGuardResult
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :returns: 为 ``True`` 时应返回 ``DraftRetryOutcome(passed=True)``。
    :rtype: bool
    """
    if options.guard_mode == ContentGuardMode.REPORT_ONLY:
        return guard_result.hard_passed
    return guard_result.passed


async def _classify_detailed_async(
    violations: tuple[Violation, ...],
    *,
    options: DraftRetryOptions,
    attempt_index: int,
) -> ClassifyViolationsResult:
    """在线程池中执行违规分类（内部辅助）。

    :param violations: 单轮校验违规。
    :type violations: tuple[Violation, ...]
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :param attempt_index: 当前尝试序号（1-based）。
    :type attempt_index: int
    :returns: 完整分类结果。
    :rtype: ClassifyViolationsResult
    """

    def _run_classify() -> ClassifyViolationsResult:
        """执行同步违规分类（闭包）。

        :returns: 分类结果。
        :rtype: ClassifyViolationsResult
        """
        return classify_violations_detailed(
            violations,
            options=options,
            attempt_index=attempt_index,
        )

    return await asyncio.to_thread(_run_classify)


async def _execute_coordinator_action_async(
    *,
    context: DraftRetryContext,
    state: DraftRetryCoordinatorState,
    options: DraftRetryOptions,
    action: RetryAction,
    classification: ClassifyViolationsResult,
    guard_result: ContentGuardResult,
    qwen_client: AsyncQwenClient | None,
) -> _CoordinatorActionStepResult:
    """执行单步 ``RetryAction`` 并更新状态（内部辅助）。

    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :param state: 当前协调器状态。
    :type state: DraftRetryCoordinatorState
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :param action: 本轮分类后的协调动作。
    :type action: RetryAction
    :param classification: 完整分类结果（含 ``considered_violations``）。
    :type classification: ClassifyViolationsResult
    :param guard_result: 触发本动作的 guard 结果。
    :type guard_result: ContentGuardResult
    :param qwen_client: 可选通义客户端。
    :type qwen_client: AsyncQwenClient | None
    :returns: 更新后的状态及可选的终端 outcome。
    :rtype: _CoordinatorActionStepResult
    """
    if action == RetryAction.DETERMINISTIC_REPAIR:
        return await _step_deterministic_repair_async(
            context=context,
            state=state,
            options=options,
            violations=classification.considered_violations,
        )

    if action == RetryAction.RETRY_LLM:
        return await _step_retry_llm_async(
            context=context,
            state=state,
            options=options,
            violations=classification.considered_violations,
            current_draft=guard_result.draft,
            qwen_client=qwen_client,
        )

    if action == RetryAction.MECHANICAL_FALLBACK:
        return await _step_mechanical_fallback_async(
            context=context,
            state=state,
            options=options,
        )

    return _CoordinatorActionStepResult(state=state)


async def _step_deterministic_repair_async(
    *,
    context: DraftRetryContext,
    state: DraftRetryCoordinatorState,
    options: DraftRetryOptions,
    violations: tuple[Violation, ...],
) -> _CoordinatorActionStepResult:
    """执行 ``DETERMINISTIC_REPAIR`` 动作（内部辅助）。

    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :param state: 当前状态。
    :type state: DraftRetryCoordinatorState
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :param violations: 触发修补的违规。
    :type violations: tuple[Violation, ...]
    :returns: 更新后的状态。
    :rtype: _CoordinatorActionStepResult
    """
    repair_result = await apply_deterministic_repair_async(
        state.draft,
        violations,
        context,
        options=options,
    )

    next_attempt_index = state.attempt_index
    if repair_result.changed and options.count_repair_as_attempt:
        next_attempt_index = state.attempt_index + 1
    elif not repair_result.changed:
        next_attempt_index = state.attempt_index + 1

    updated_state = _replace_coordinator_state(
        state,
        draft=repair_result.draft,
        attempt_index=next_attempt_index,
    )
    return _CoordinatorActionStepResult(state=updated_state)


async def _step_retry_llm_async(
    *,
    context: DraftRetryContext,
    state: DraftRetryCoordinatorState,
    options: DraftRetryOptions,
    violations: tuple[Violation, ...],
    current_draft: DraftCopyJSON,
    qwen_client: AsyncQwenClient | None,
) -> _CoordinatorActionStepResult:
    """执行 ``RETRY_LLM`` 动作（内部辅助）。

    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :param state: 当前状态。
    :type state: DraftRetryCoordinatorState
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :param violations: 触发 LLM 重写的违规。
    :type violations: tuple[Violation, ...]
    :param current_draft: 当前未通过 guard 的草稿。
    :type current_draft: DraftCopyJSON
    :param qwen_client: 可选通义客户端。
    :type qwen_client: AsyncQwenClient | None
    :returns: 更新后的状态；LLM 失败且可兜底时可能附带终端 outcome。
    :rtype: _CoordinatorActionStepResult
    """
    if not options.can_invoke_llm(state.llm_generation_count):
        return await _step_mechanical_fallback_async(
            context=context,
            state=state,
            options=options,
        )

    try:
        repair_result = await generate_guard_repair_llm_draft_async(
            context,
            current_draft=current_draft,
            violations=violations,
            options=options,
            qwen_client=qwen_client,
        )
    except LlmDraftGenerationError:
        if options.fallback_to_mechanical:
            return await _step_mechanical_fallback_async(
                context=context,
                state=state,
                options=options,
            )
        return _CoordinatorActionStepResult(
            state=state,
            terminal_outcome=_build_failure_outcome(
                state=state,
                guard_result=state.last_guard_result,
                terminal_action=RetryAction.ABORT.value,
                error_message="LLM 重写失败且未启用机械兜底。",
            ),
        )

    updated_state = _replace_coordinator_state(
        state,
        draft=repair_result.draft,
        generator=DraftRetryGeneratorKind.QWEN,
        llm_generation_count=state.llm_generation_count + repair_result.llm_call_count,
        attempt_index=state.attempt_index + 1,
    )
    return _CoordinatorActionStepResult(state=updated_state)


async def _step_mechanical_fallback_async(
    *,
    context: DraftRetryContext,
    state: DraftRetryCoordinatorState,
    options: DraftRetryOptions,
) -> _CoordinatorActionStepResult:
    """执行 ``MECHANICAL_FALLBACK`` 终端兜底（内部辅助）。

    :param context: 协调器上下文。
    :type context: DraftRetryContext
    :param state: 当前状态。
    :type state: DraftRetryCoordinatorState
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :returns: 使用强兜底机械稿更新后的状态。
    :rtype: _CoordinatorActionStepResult
    """
    mechanical = await _generate_mechanical_fallback_async(
        context,
        options=options,
    )
    updated_state = _replace_coordinator_state(
        state,
        draft=mechanical.draft,
        generator=DraftRetryGeneratorKind.MECHANICAL_FALLBACK,
        used_mechanical_fallback=True,
        attempt_index=state.attempt_index + 1,
    )
    return _CoordinatorActionStepResult(state=updated_state)


def _mechanical_fallback_or_abort(options: DraftRetryOptions) -> RetryActionLiteral:
    """在机械兜底与 abort 间选择（内部辅助，委托 classifier 同源逻辑）。

    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :returns: 动作字面量。
    :rtype: RetryActionLiteral
    """
    if options.fallback_to_mechanical:
        return RetryAction.MECHANICAL_FALLBACK.value
    return RetryAction.ABORT.value


def _build_success_outcome(
    *,
    state: DraftRetryCoordinatorState,
    draft: DraftCopyJSON,
    guard_result: ContentGuardResult,
    terminal_action: RetryActionLiteral,
) -> DraftRetryOutcome:
    """构造协调器成功 outcome（内部辅助）。

    :param state: 终止时的协调器状态。
    :type state: DraftRetryCoordinatorState
    :param draft: 最终文案草稿。
    :type draft: DraftCopyJSON
    :param guard_result: 最后一轮 guard 结果。
    :type guard_result: ContentGuardResult
    :param terminal_action: 终止动作（成功时为 ``accept``）。
    :type terminal_action: RetryActionLiteral
    :returns: 成功 outcome。
    :rtype: DraftRetryOutcome
    """
    return DraftRetryOutcome(
        passed=True,
        draft=draft,
        attempt_count=state.attempt_index,
        used_mechanical_fallback=state.used_mechanical_fallback,
        generator=state.generator,
        violations_history=tuple(state.history),
        last_guard_result=guard_result,
        terminal_action=terminal_action,
        error_message=None,
        llm_generation_count=state.llm_generation_count,
    )


def _build_failure_outcome(
    *,
    state: DraftRetryCoordinatorState,
    guard_result: ContentGuardResult | None,
    terminal_action: RetryActionLiteral,
    error_message: str,
) -> DraftRetryOutcome:
    """构造协调器失败 outcome（内部辅助）。

    :param state: 终止时的协调器状态。
    :type state: DraftRetryCoordinatorState
    :param guard_result: 最后一轮 guard 结果；可能为 ``None``。
    :type guard_result: ContentGuardResult | None
    :param terminal_action: 终止动作（如 ``abort``）。
    :type terminal_action: RetryActionLiteral
    :param error_message: 人类可读失败说明。
    :type error_message: str
    :returns: 失败 outcome。
    :rtype: DraftRetryOutcome
    """
    last_draft = guard_result.draft if guard_result is not None else state.draft
    return DraftRetryOutcome(
        passed=False,
        draft=last_draft,
        attempt_count=state.attempt_index,
        used_mechanical_fallback=state.used_mechanical_fallback,
        generator=state.generator,
        violations_history=tuple(state.history),
        last_guard_result=guard_result,
        terminal_action=terminal_action,
        error_message=error_message,
        llm_generation_count=state.llm_generation_count,
    )
