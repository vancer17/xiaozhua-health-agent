"""L5 ValidateContent 聚合门面（④-B）。"""

from __future__ import annotations

import asyncio

from xiaozhua_health_agent.eval import (
    Violation,
    ViolationSeverity,
    validate_draft_structure,
)
from xiaozhua_health_agent.guard.checkers.emergency_tone import check_emergency_tone
from xiaozhua_health_agent.guard.checkers.evidence_authenticity import (
    check_evidence_authenticity,
)
from xiaozhua_health_agent.guard.checkers.forced_mention import check_forced_mentions
from xiaozhua_health_agent.guard.checkers.forbidden_pattern import (
    check_forbidden_patterns,
    resolve_forbidden_patterns,
)
from xiaozhua_health_agent.guard.checkers.locked_action import (
    check_locked_draft_actions,
)
from xiaozhua_health_agent.guard.checkers.risk_text_consistency import (
    check_risk_text_consistency,
)
from xiaozhua_health_agent.guard.checkers.safety_notice import check_safety_notice
from xiaozhua_health_agent.guard.guard_types import (
    CONTENT_GUARD_SCHEMA_VERSION,
    ContentGuardInput,
    ContentGuardOptions,
    ContentGuardResult,
    DEFAULT_CONTENT_GUARD_OPTIONS,
)
from xiaozhua_health_agent.guard.resources import (
    resolve_synonym_map_for_guard,
    resolve_synonym_map_for_guard_async,
)
from xiaozhua_health_agent.guard.sanitizer import sanitize_guard_input

__all__ = [
    "CONTENT_GUARD_SCHEMA_VERSION",
    "DEFAULT_CONTENT_GUARD_OPTIONS",
    "build_content_guard_result",
    "run_content_guard_checks",
    "validate_content",
    "validate_content_async",
]


def validate_content(
    guard_input: ContentGuardInput,
    *,
    options: ContentGuardOptions | None = None,
) -> ContentGuardResult:
    """对 ``DraftCopyJSON`` 执行 ValidateContent（同步）。

    固定顺序：结构（④-A 委托）→ 行动锁定 → 禁止词 → 紧急语气 → 证据真实性
    → 免责声明 → 风险文案一致性 → forcedMentions。

    :param guard_input: 守卫输入上下文。
    :type guard_input: ContentGuardInput
    :param options: 运行配置；省略时使用 ``DEFAULT_CONTENT_GUARD_OPTIONS``。
    :type options: ContentGuardOptions | None
    :returns: 内容守卫聚合结果。
    :rtype: ContentGuardResult
    """
    effective_options = (
        options if options is not None else DEFAULT_CONTENT_GUARD_OPTIONS
    )
    synonym_map = resolve_synonym_map_for_guard(
        synonym_map=guard_input.synonym_map,
        options=effective_options,
    )
    enriched_input = ContentGuardInput(
        draft=guard_input.draft,
        triage=guard_input.triage,
        fact_sheet=guard_input.fact_sheet,
        resolved=guard_input.resolved,
        copy_bundle=guard_input.copy_bundle,
        synonym_map=synonym_map,
    )
    violations = run_content_guard_checks(enriched_input, options=effective_options)
    return build_content_guard_result(
        draft=enriched_input.draft,
        violations=violations,
        options=effective_options,
    )


async def validate_content_async(
    guard_input: ContentGuardInput,
    *,
    options: ContentGuardOptions | None = None,
) -> ContentGuardResult:
    """对 ``DraftCopyJSON`` 执行 ValidateContent（异步）。

    KB-SYN 磁盘加载在线程池执行；检查器本体在线程池中运行以避免阻塞事件循环。

    :param guard_input: 守卫输入上下文。
    :type guard_input: ContentGuardInput
    :param options: 运行配置。
    :type options: ContentGuardOptions | None
    :returns: 内容守卫聚合结果。
    :rtype: ContentGuardResult
    """
    effective_options = (
        options if options is not None else DEFAULT_CONTENT_GUARD_OPTIONS
    )
    synonym_map = await resolve_synonym_map_for_guard_async(
        synonym_map=guard_input.synonym_map,
        options=effective_options,
    )
    enriched_input = ContentGuardInput(
        draft=guard_input.draft,
        triage=guard_input.triage,
        fact_sheet=guard_input.fact_sheet,
        resolved=guard_input.resolved,
        copy_bundle=guard_input.copy_bundle,
        synonym_map=synonym_map,
    )

    def _run_checks() -> tuple[Violation, ...]:
        """在线程池执行同步守卫检查（闭包）。

        :returns: 全部违规元组。
        :rtype: tuple[Violation, ...]
        """
        return run_content_guard_checks(enriched_input, options=effective_options)

    violations = await asyncio.to_thread(_run_checks)
    return build_content_guard_result(
        draft=enriched_input.draft,
        violations=violations,
        options=effective_options,
    )


def run_content_guard_checks(
    guard_input: ContentGuardInput,
    *,
    options: ContentGuardOptions,
) -> tuple[Violation, ...]:
    """运行全部内容守卫子检查器并合并违规（不含 passed 聚合）。

    :param guard_input: 守卫输入上下文（应已解析 ``synonym_map``）。
    :type guard_input: ContentGuardInput
    :param options: 运行配置。
    :type options: ContentGuardOptions
    :returns: 全部 ``domain=guard`` 违规（含 schema 结构失败时仅结构违规）。
    :rtype: tuple[Violation, ...]
    """
    draft = guard_input.draft
    structure = validate_draft_structure(draft)
    if not structure.passed:
        return tuple(structure.violations)

    kb_patterns: tuple[str, ...] | None = None
    if guard_input.copy_bundle is not None:
        kb_patterns = guard_input.copy_bundle.kb_forbid.forbidden_patterns

    forbidden_patterns = resolve_forbidden_patterns(
        forbidden_themes=guard_input.triage.forbidden_themes,
        kb_forbid_patterns=kb_patterns,
    )

    collected: list[Violation] = []
    collected.extend(
        check_locked_draft_actions(
            draft,
            guard_input.resolved,
            lock_label=options.lock_action_label,
        ),
    )
    collected.extend(
        check_forbidden_patterns(
            draft,
            patterns=forbidden_patterns,
            include_action_labels=options.include_action_labels_in_forbidden_scan,
        ),
    )
    collected.extend(check_emergency_tone(draft, guard_input.triage))
    collected.extend(
        check_evidence_authenticity(
            draft,
            guard_input.triage,
            guard_input.fact_sheet,
        ),
    )
    collected.extend(
        check_safety_notice(
            draft,
            guard_input.triage,
            min_length=options.min_safety_notice_length,
        ),
    )
    if not options.skip_risk_text_consistency:
        collected.extend(
            check_risk_text_consistency(draft, guard_input.triage),
        )
    if guard_input.synonym_map is not None:
        collected.extend(
            check_forced_mentions(
                draft,
                guard_input.triage,
                synonym_map=guard_input.synonym_map,
            ),
        )

    return tuple(collected)


def build_content_guard_result(
    *,
    draft: object,
    violations: tuple[Violation, ...],
    options: ContentGuardOptions,
    sanitized: bool = False,
) -> ContentGuardResult:
    """由违规列表聚合 ``ContentGuardResult``。

    :param draft: 审查后的文案草稿（``DraftCopyJSON``）。
    :type draft: object
    :param violations: 全部守卫违规。
    :type violations: tuple[Violation, ...]
    :param options: 运行配置。
    :type options: ContentGuardOptions
    :param sanitized: 是否经过确定性修补。
    :type sanitized: bool
    :returns: 聚合结果。
    :rtype: ContentGuardResult
    """
    from xiaozhua_health_agent.copy import DraftCopyJSON

    if not isinstance(draft, DraftCopyJSON):
        msg = f"draft 必须为 DraftCopyJSON，收到 {type(draft).__name__}。"
        raise TypeError(msg)

    hard_violations = tuple(
        item for item in violations if item.severity == ViolationSeverity.HIGH.value
    )
    med_violations = tuple(
        item for item in violations if item.severity == ViolationSeverity.MEDIUM.value
    )
    low_violations = tuple(
        item for item in violations if item.severity == ViolationSeverity.LOW.value
    )

    hard_passed = len(hard_violations) == 0
    soft_passed = hard_passed and len(med_violations) == 0 and len(low_violations) == 0

    if options.enforce_forced_mentions:
        passed = soft_passed
        warnings: tuple[Violation, ...] = ()
    else:
        passed = hard_passed
        warnings = med_violations + low_violations

    return ContentGuardResult(
        passed=passed,
        hard_passed=hard_passed,
        soft_passed=soft_passed,
        violations=violations,
        warnings=warnings,
        draft=draft,
        sanitized=sanitized,
    )


def validate_content_with_sanitize(
    guard_input: ContentGuardInput,
    *,
    options: ContentGuardOptions | None = None,
) -> ContentGuardResult:
    """执行 ValidateContent；若仅 safetyNotice 缺失则尝试确定性修补后再验。

    :param guard_input: 守卫输入上下文。
    :type guard_input: ContentGuardInput
    :param options: 运行配置。
    :type options: ContentGuardOptions | None
    :returns: 内容守卫结果（可能含 ``sanitized=True``）。
    :rtype: ContentGuardResult
    """
    first = validate_content(guard_input, options=options)
    if first.passed:
        return first

    patched_input, changed = sanitize_guard_input(guard_input)
    if not changed:
        return first

    second = validate_content(patched_input, options=options)
    return ContentGuardResult(
        passed=second.passed,
        hard_passed=second.hard_passed,
        soft_passed=second.soft_passed,
        violations=second.violations,
        warnings=second.warnings,
        draft=second.draft,
        sanitized=True,
    )


async def validate_content_with_sanitize_async(
    guard_input: ContentGuardInput,
    *,
    options: ContentGuardOptions | None = None,
) -> ContentGuardResult:
    """``validate_content_with_sanitize`` 的异步版本。

    :param guard_input: 守卫输入上下文。
    :type guard_input: ContentGuardInput
    :param options: 运行配置。
    :type options: ContentGuardOptions | None
    :returns: 内容守卫结果。
    :rtype: ContentGuardResult
    """
    first = await validate_content_async(guard_input, options=options)
    if first.passed:
        return first

    patched_input, changed = sanitize_guard_input(guard_input)
    if not changed:
        return first

    second = await validate_content_async(patched_input, options=options)
    return ContentGuardResult(
        passed=second.passed,
        hard_passed=second.hard_passed,
        soft_passed=second.soft_passed,
        violations=second.violations,
        warnings=second.warnings,
        draft=second.draft,
        sanitized=True,
    )
