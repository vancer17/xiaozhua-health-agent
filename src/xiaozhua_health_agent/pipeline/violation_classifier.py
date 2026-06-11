"""WP5 文案重试协调器 — 违规分类与 ``RetryAction`` 路由（``pipeline-design.md`` §6.2）。

将 ``schema`` / ``guard`` 域的 ``Violation`` 列表映射为协调器下一步动作；
``semantic_eval`` / ``risk_eval`` 域违规会被忽略，不参与路由。

包外请通过 ``xiaozhua_health_agent.pipeline`` 门面导入 ``classify_violations`` /
``classify_violations_async``。
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from typing import Final

from xiaozhua_health_agent.eval import (
    Violation,
    ViolationCode,
    ViolationCodeLiteral,
    ViolationDomain,
    ViolationSeverity,
)
from xiaozhua_health_agent.pipeline.retry_types import (
    DEFAULT_DRAFT_RETRY_OPTIONS,
    DraftRetryOptions,
    RetryAction,
    RetryActionLiteral,
    compare_retry_action_strength,
)

__all__ = [
    "ClassifyViolationsResult",
    "classify_violations",
    "classify_violations_async",
    "filter_retryable_violations",
    "max_retry_action",
]

_RETRYABLE_VIOLATION_DOMAINS: Final[frozenset[str]] = frozenset(
    {
        ViolationDomain.SCHEMA.value,
        ViolationDomain.GUARD.value,
    },
)
"""协调器允许消费的违规域（不含 L7 评测域）。"""

_SCHEMA_STRUCTURE_CODES: Final[frozenset[ViolationCodeLiteral]] = frozenset(
    {
        ViolationCode.PARSE_ERROR.value,
        ViolationCode.FIELD_MISSING.value,
        ViolationCode.TYPE_ERROR.value,
        ViolationCode.ENUM_INVALID.value,
        ViolationCode.EXTRA_FIELD.value,
        ViolationCode.VALUE_ERROR.value,
        ViolationCode.ACTION_INVALID.value,
    },
)
"""④-A 结构校验类违规码。"""

_ACTION_LOCK_CODES: Final[frozenset[ViolationCodeLiteral]] = frozenset(
    {
        ViolationCode.ACTION_ROUTE_MISMATCH.value,
        ViolationCode.ACTION_LABEL_MISMATCH.value,
    },
)
"""主/次行动与 ③-1 draft 不一致类违规码。"""

_HIGH_CONTENT_CODES: Final[frozenset[ViolationCodeLiteral]] = frozenset(
    {
        ViolationCode.FORBIDDEN_PATTERN_HIT.value,
        ViolationCode.EVIDENCE_HALLUCINATION.value,
        ViolationCode.EMERGENCY_TONE_WEAK.value,
    },
)
"""HIGH 严重度内容守卫违规（guard 域）。"""


class ClassifyViolationsResult:
    """``classify_violations`` 的完整分类结果（便于协调器记录审计轨迹）。

    :ivar action: 聚合并套用尝试预算后的最终动作。
    :vartype action: RetryAction
    :ivar raw_action: 未套用 ``attempt_index`` 预算前的聚合动作。
    :vartype raw_action: RetryAction
    :ivar considered_violations: 参与路由的 ``schema`` / ``guard`` 违规。
    :vartype considered_violations: tuple[Violation, ...]
    :ivar ignored_violation_count: 被忽略的 ``semantic_eval`` / ``risk_eval`` 等数量。
    :vartype ignored_violation_count: int
    """

    __slots__ = (
        "action",
        "considered_violations",
        "ignored_violation_count",
        "raw_action",
    )

    def __init__(
        self,
        *,
        action: RetryAction,
        raw_action: RetryAction,
        considered_violations: tuple[Violation, ...],
        ignored_violation_count: int,
    ) -> None:
        """构造分类结果。

        :param action: 最终协调动作。
        :type action: RetryAction
        :param raw_action: 预算调整前的聚合动作。
        :type raw_action: RetryAction
        :param considered_violations: 参与分类的违规列表。
        :type considered_violations: tuple[Violation, ...]
        :param ignored_violation_count: 被过滤掉的违规数量。
        :type ignored_violation_count: int
        """
        self.action = action
        self.raw_action = raw_action
        self.considered_violations = considered_violations
        self.ignored_violation_count = ignored_violation_count


def filter_retryable_violations(
    violations: Sequence[Violation],
) -> tuple[Violation, ...]:
    """保留协调器可消费的 ``schema`` / ``guard`` 违规，丢弃评测域违规。

    :param violations: 原始违规列表（可能含 L7 ``semantic_eval`` 等）。
    :type violations: collections.abc.Sequence[Violation]
    :returns: 可参与 ``RetryAction`` 路由的违规元组。
    :rtype: tuple[Violation, ...]
    """
    return tuple(
        item for item in violations if item.domain in _RETRYABLE_VIOLATION_DOMAINS
    )


def max_retry_action(actions: Sequence[RetryActionLiteral]) -> RetryAction:
    """在多条单违规动作中取强度最高者。

    :param actions: 单违规分类得到的动作字面量序列。
    :type actions: collections.abc.Sequence[RetryActionLiteral]
    :returns: 强度最高的 ``RetryAction``；空序列时为 ``ACCEPT``。
    :rtype: RetryAction
    """
    if len(actions) == 0:
        return RetryAction.ACCEPT

    strongest: RetryActionLiteral = actions[0]
    for candidate in actions[1:]:
        if compare_retry_action_strength(candidate, strongest) > 0:
            strongest = candidate
    return RetryAction(strongest)


def classify_violations(
    violations: Sequence[Violation],
    *,
    options: DraftRetryOptions | None = None,
    attempt_index: int = 1,
) -> RetryAction:
    """将校验违规列表映射为协调器下一步 ``RetryAction``。

    空列表或过滤后无 ``schema`` / ``guard`` 违规时返回 ``ACCEPT``。
    多条违规时按 ``RETRY_ACTION_STRENGTH`` 取最强动作；随后在
    ``attempt_index >= max_attempts`` 时将 ``retry_llm`` / ``deterministic_repair``
    升级为 ``mechanical_fallback``（或 ``abort``）。

    :param violations: 单轮 ``validate_structure`` + ``validate_content`` 产出的违规。
    :type violations: collections.abc.Sequence[Violation]
    :param options: 协调器配置；省略时使用 ``DEFAULT_DRAFT_RETRY_OPTIONS``。
    :type options: DraftRetryOptions | None
    :param attempt_index: 当前尝试序号（1-based），用于尝试预算升级。
    :type attempt_index: int
    :returns: 下一步协调动作。
    :rtype: RetryAction
    :raises ValueError: ``attempt_index`` 小于 1 时抛出。
    """
    result = classify_violations_detailed(
        violations,
        options=options,
        attempt_index=attempt_index,
    )
    return result.action


async def classify_violations_async(
    violations: Sequence[Violation],
    *,
    options: DraftRetryOptions | None = None,
    attempt_index: int = 1,
) -> RetryAction:
    """``classify_violations`` 的异步版本（在线程池中执行 CPU 分类逻辑）。

    :param violations: 单轮校验违规列表。
    :type violations: collections.abc.Sequence[Violation]
    :param options: 协调器配置。
    :type options: DraftRetryOptions | None
    :param attempt_index: 当前尝试序号（1-based）。
    :type attempt_index: int
    :returns: 下一步协调动作。
    :rtype: RetryAction
    :raises ValueError: ``attempt_index`` 小于 1 时抛出。
    """

    def _run_classification() -> RetryAction:
        """在线程池中执行同步分类（闭包）。

        :returns: 下一步协调动作。
        :rtype: RetryAction
        """
        return classify_violations(
            violations,
            options=options,
            attempt_index=attempt_index,
        )

    return await asyncio.to_thread(_run_classification)


def classify_violations_detailed(
    violations: Sequence[Violation],
    *,
    options: DraftRetryOptions | None = None,
    attempt_index: int = 1,
) -> ClassifyViolationsResult:
    """与 :func:`classify_violations` 相同，但返回完整分类元数据。

    :param violations: 单轮校验违规列表。
    :type violations: collections.abc.Sequence[Violation]
    :param options: 协调器配置。
    :type options: DraftRetryOptions | None
    :param attempt_index: 当前尝试序号（1-based）。
    :type attempt_index: int
    :returns: 含原始/最终动作及过滤后违规的结果对象。
    :rtype: ClassifyViolationsResult
    :raises ValueError: ``attempt_index`` 小于 1 时抛出。
    """
    if attempt_index < 1:
        msg = f"attempt_index 必须 >= 1，收到 {attempt_index}。"
        raise ValueError(msg)

    effective_options = options if options is not None else DEFAULT_DRAFT_RETRY_OPTIONS
    considered = filter_retryable_violations(violations)
    ignored_count = len(violations) - len(considered)

    if len(considered) == 0:
        return ClassifyViolationsResult(
            action=RetryAction.ACCEPT,
            raw_action=RetryAction.ACCEPT,
            considered_violations=(),
            ignored_violation_count=ignored_count,
        )

    per_violation_actions: list[RetryActionLiteral] = [
        _classify_single_violation(
            item,
            options=effective_options,
        )
        for item in considered
    ]
    raw_action = max_retry_action(per_violation_actions)
    final_action = _apply_attempt_budget(
        raw_action,
        options=effective_options,
        attempt_index=attempt_index,
    )

    return ClassifyViolationsResult(
        action=final_action,
        raw_action=raw_action,
        considered_violations=considered,
        ignored_violation_count=ignored_count,
    )


def _classify_single_violation(
    violation: Violation,
    *,
    options: DraftRetryOptions,
) -> RetryActionLiteral:
    """将单条 ``schema`` / ``guard`` 违规映射为 ``RetryAction``（内部辅助）。

    :param violation: 单条可路由违规。
    :type violation: Violation
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :returns: 单违规建议动作（未套用尝试预算）。
    :rtype: RetryActionLiteral
    """
    code = violation.code

    if code in _SCHEMA_STRUCTURE_CODES:
        return _action_for_schema_structure(options)

    if code in _ACTION_LOCK_CODES:
        return _action_for_action_lock(options)

    if code in _HIGH_CONTENT_CODES:
        return _action_for_high_content(code, options=options)

    if code == ViolationCode.SAFETY_NOTICE_REQUIRED_MISSING.value:
        return _action_for_safety_notice_missing(options)

    if code == ViolationCode.FORCED_MENTION_MISSING.value:
        return _action_for_forced_mention_missing(options)

    if code == ViolationCode.RISK_TEXT_INCONSISTENT.value:
        return RetryAction.ACCEPT.value

    return _action_for_unknown_retryable_violation(violation, options=options)


def _action_for_schema_structure(options: DraftRetryOptions) -> RetryActionLiteral:
    """结构类违规的路由（内部辅助）。

    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :returns: LLM 重试或机械兜底动作。
    :rtype: RetryActionLiteral
    """
    if options.llm_enabled:
        return RetryAction.RETRY_LLM.value
    return _mechanical_fallback_or_abort(options)


def _action_for_action_lock(options: DraftRetryOptions) -> RetryActionLiteral:
    """行动锁定不一致的路由（内部辅助）。

    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :returns: 优先确定性回写，否则 LLM 或兜底。
    :rtype: RetryActionLiteral
    """
    if options.enable_deterministic_repair:
        return RetryAction.DETERMINISTIC_REPAIR.value
    if options.llm_enabled:
        return RetryAction.RETRY_LLM.value
    return _mechanical_fallback_or_abort(options)


def _action_for_high_content(
    code: ViolationCodeLiteral,
    *,
    options: DraftRetryOptions,
) -> RetryActionLiteral:
    """HIGH 内容守卫违规的路由（内部辅助）。

    :param code: 违规类型码。
    :type code: ViolationCodeLiteral
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :returns: LLM 重试、确定性修补或机械兜底。
    :rtype: RetryActionLiteral
    """
    if options.llm_enabled:
        return RetryAction.RETRY_LLM.value

    if (
        code == ViolationCode.EMERGENCY_TONE_WEAK.value
        and options.enable_deterministic_repair
    ):
        return RetryAction.DETERMINISTIC_REPAIR.value

    return _mechanical_fallback_or_abort(options)


def _action_for_safety_notice_missing(
    options: DraftRetryOptions,
) -> RetryActionLiteral:
    """免责声明缺失（MED）的路由（内部辅助）。

    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :returns: 优先 sanitize 修补，否则兜底。
    :rtype: RetryActionLiteral
    """
    if options.enable_deterministic_repair:
        return RetryAction.DETERMINISTIC_REPAIR.value
    return _mechanical_fallback_or_abort(options)


def _action_for_forced_mention_missing(
    options: DraftRetryOptions,
) -> RetryActionLiteral:
    """``forcedMentions`` 缺失（MED）的路由（内部辅助）。

    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :returns: 按配置在 LLM 重试、机械补 mention 或接受间选择。
    :rtype: RetryActionLiteral
    """
    if options.enforce_forced_mentions_on_retry and options.llm_enabled:
        return RetryAction.RETRY_LLM.value
    if options.enable_deterministic_repair:
        return RetryAction.DETERMINISTIC_REPAIR.value
    if options.allow_accept_with_med_warnings:
        return RetryAction.ACCEPT.value
    return _mechanical_fallback_or_abort(options)


def _action_for_unknown_retryable_violation(
    violation: Violation,
    *,
    options: DraftRetryOptions,
) -> RetryActionLiteral:
    """未显式映射的可路由违规之保守默认（内部辅助）。

    :param violation: 单条违规。
    :type violation: Violation
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :returns: HIGH 走兜底；MED/LOW 在允许时 ``accept``。
    :rtype: RetryActionLiteral
    """
    if violation.severity == ViolationSeverity.HIGH.value:
        if options.llm_enabled:
            return RetryAction.RETRY_LLM.value
        return _mechanical_fallback_or_abort(options)

    if options.allow_accept_with_med_warnings:
        return RetryAction.ACCEPT.value
    if options.enable_deterministic_repair:
        return RetryAction.DETERMINISTIC_REPAIR.value
    return _mechanical_fallback_or_abort(options)


def _apply_attempt_budget(
    action: RetryAction,
    *,
    options: DraftRetryOptions,
    attempt_index: int,
) -> RetryAction:
    """在尝试序号达到上限时将弱动作升级为兜底或 ``abort``（内部辅助）。

    :param action: 聚合后的原始动作。
    :type action: RetryAction
    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :param attempt_index: 当前尝试序号（1-based）。
    :type attempt_index: int
    :returns: 套用预算后的最终动作。
    :rtype: RetryAction
    """
    if attempt_index < options.max_attempts:
        return action

    if action in (RetryAction.RETRY_LLM, RetryAction.DETERMINISTIC_REPAIR):
        return RetryAction(_mechanical_fallback_or_abort(options))

    return action


def _mechanical_fallback_or_abort(options: DraftRetryOptions) -> RetryActionLiteral:
    """在机械兜底与 ``abort`` 间选择（内部辅助）。

    :param options: 协调器配置。
    :type options: DraftRetryOptions
    :returns: ``mechanical_fallback`` 或 ``abort`` 字面量。
    :rtype: RetryActionLiteral
    """
    if options.fallback_to_mechanical:
        return RetryAction.MECHANICAL_FALLBACK.value
    return RetryAction.ABORT.value
