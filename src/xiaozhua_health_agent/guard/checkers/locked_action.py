"""行动锁定一致性检查器（ValidateContent 子集）。"""

from __future__ import annotations

from xiaozhua_health_agent.copy import (
    CopyTemplateResolved,
    DraftCopyJSON,
    collect_locked_action_mismatches_from_draft,
)
from xiaozhua_health_agent.eval import (
    Violation,
    ViolationCode,
    ViolationCodeLiteral,
    ViolationSeverity,
)
from xiaozhua_health_agent.guard.violation_factory import make_guard_violation

__all__ = [
    "check_locked_draft_actions",
]


def check_locked_draft_actions(
    draft: DraftCopyJSON,
    resolved: CopyTemplateResolved,
    *,
    lock_label: bool = True,
) -> tuple[Violation, ...]:
    """校验文案草稿主/次行动是否与 ③-1 draft 一致。

    :param draft: 步骤 ③ 文案草稿。
    :type draft: DraftCopyJSON
    :param resolved: 步骤 ③-1 模板解析包（行动 draft 真源）。
    :type resolved: CopyTemplateResolved
    :param lock_label: 是否同时校验 ``label``。
    :type lock_label: bool
    :returns: 违规列表；通过时为空元组。
    :rtype: tuple[Violation, ...]
    """
    violations: list[Violation] = []

    mismatches_primary = collect_locked_action_mismatches_from_draft(
        draft.primary_action,
        expected=resolved.primary_action_draft,
        json_path_prefix="primaryAction",
        field_name="primaryAction",
        required=True,
        lock_label=lock_label,
    )
    violations.extend(
        _mismatches_to_violations(mismatches_primary),
    )

    mismatches_secondary = collect_locked_action_mismatches_from_draft(
        draft.secondary_action,
        expected=resolved.secondary_action_draft,
        json_path_prefix="secondaryAction",
        field_name="secondaryAction",
        required=False,
        lock_label=lock_label,
    )
    violations.extend(
        _mismatches_to_violations(mismatches_secondary),
    )

    return tuple(violations)


def _mismatches_to_violations(
    mismatches: tuple[object, ...],
) -> tuple[Violation, ...]:
    """将 ``LockedActionMismatch`` 转为守卫违规（内部辅助）。

    :param mismatches: 行动不一致记录元组。
    :type mismatches: tuple[object, ...]
    :returns: ``domain=guard`` 违规元组。
    :rtype: tuple[Violation, ...]
    """
    from xiaozhua_health_agent.copy import LockedActionField, LockedActionMismatch

    results: list[Violation] = []
    for item in mismatches:
        if not isinstance(item, LockedActionMismatch):
            continue
        code: ViolationCodeLiteral = (
            ViolationCode.ACTION_LABEL_MISMATCH.value
            if item.mismatch_kind == LockedActionField.LABEL
            else ViolationCode.ACTION_ROUTE_MISMATCH.value
        )
        results.append(
            make_guard_violation(
                code=code,
                path=item.json_path,
                field=item.field,
                message=item.message,
                severity=ViolationSeverity.HIGH.value,
            ),
        )
    return tuple(results)
