"""步骤 ④-B 行动锁定一致性校验（ValidateContent 子集）。

检测 ``DraftCopyJSON`` 中 ``primaryAction`` / ``secondaryAction`` 是否与
③-1 ``CopyTemplateResolved`` draft 一致；供重试协调器与 strict 模式批跑使用。

比对逻辑委托 ``xiaozhua_health_agent.copy`` 公开的 ``collect_locked_action_mismatches_from_draft``。
运行时从 ``copy`` 包门面惰性导入，避免 ``eval`` ↔ ``copy`` 循环依赖。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from xiaozhua_health_agent.eval.validation_result import (
    Violation,
    ViolationCode,
    ViolationCodeLiteral,
    ViolationDomain,
    ViolationSeverity,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from xiaozhua_health_agent.copy import (
        CopyTemplateResolved,
        DraftCopyJSON,
        LockedActionMismatch,
    )

__all__ = [
    "locked_action_mismatches_to_violations",
    "validate_locked_draft_actions",
]


def validate_locked_draft_actions(
    draft: DraftCopyJSON,
    resolved: CopyTemplateResolved,
    *,
    lock_label: bool = True,
) -> tuple[Violation, ...]:
    """校验文案草稿主/次行动是否与 ③-1 draft 一致。

    :param draft: 步骤 ③-2 产出的文案草稿。
    :type draft: DraftCopyJSON
    :param resolved: 同次请求的模板解析包（draft 真源）。
    :type resolved: CopyTemplateResolved
    :param lock_label: 是否同时校验 ``label``。
    :type lock_label: bool
    :returns: 违规列表；通过时为空元组。
    :rtype: tuple[Violation, ...]
    """
    from xiaozhua_health_agent.copy import collect_locked_action_mismatches_from_draft

    mismatches: list[LockedActionMismatch] = []

    mismatches.extend(
        collect_locked_action_mismatches_from_draft(
            draft.primary_action,
            expected=resolved.primary_action_draft,
            json_path_prefix="primaryAction",
            field_name="primaryAction",
            required=True,
            lock_label=lock_label,
        ),
    )
    mismatches.extend(
        collect_locked_action_mismatches_from_draft(
            draft.secondary_action,
            expected=resolved.secondary_action_draft,
            json_path_prefix="secondaryAction",
            field_name="secondaryAction",
            required=False,
            lock_label=lock_label,
        ),
    )

    return locked_action_mismatches_to_violations(mismatches)


def locked_action_mismatches_to_violations(
    mismatches: Sequence[LockedActionMismatch],
) -> tuple[Violation, ...]:
    """将 ``LockedActionMismatch`` 列表转为 ``Violation`` 列表（供重试协调器消费）。

    :param mismatches: 行动不一致记录。
    :type mismatches: collections.abc.Sequence[LockedActionMismatch]
    :returns: ``domain=guard`` 的违规元组。
    :rtype: tuple[Violation, ...]
    """
    violations: list[Violation] = []
    for item in mismatches:
        violations.append(
            Violation(
                code=_violation_code_for_mismatch(item),
                domain=ViolationDomain.GUARD.value,
                path=item.json_path,
                field=item.field,
                message=item.message,
                severity=ViolationSeverity.HIGH.value,
            ),
        )
    return tuple(violations)


def _violation_code_for_mismatch(
    mismatch: LockedActionMismatch,
) -> ViolationCodeLiteral:
    """将 mismatch 映射为 ``ViolationCode``（内部辅助）。

    :param mismatch: 不一致记录。
    :type mismatch: LockedActionMismatch
    :returns: 违规码字面量。
    :rtype: ViolationCodeLiteral
    """
    from xiaozhua_health_agent.copy import LockedActionField

    if mismatch.mismatch_kind == LockedActionField.ROUTE:
        return cast(ViolationCodeLiteral, ViolationCode.ACTION_ROUTE_MISMATCH.value)
    if mismatch.mismatch_kind == LockedActionField.LABEL:
        return cast(ViolationCodeLiteral, ViolationCode.ACTION_LABEL_MISMATCH.value)
    return cast(ViolationCodeLiteral, ViolationCode.ACTION_ROUTE_MISMATCH.value)
