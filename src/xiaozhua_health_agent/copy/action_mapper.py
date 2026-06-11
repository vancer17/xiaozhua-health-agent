"""KB-ACTION 主/次行动映射。"""

from __future__ import annotations

from xiaozhua_health_agent.copy.copy_types import KbActionBundle
from xiaozhua_health_agent.schemas import ActionItem
from xiaozhua_health_agent.triage import TriageCoreResult


class ActionMappingError(Exception):
    """KB-ACTION 映射失败。"""


def map_primary_action(
    *,
    kb_action: KbActionBundle,
    triage: TriageCoreResult,
) -> ActionItem:
    """将 ``primaryActionHint`` 映射为 ``ActionItem`` 草稿。

    :param kb_action: KB-ACTION 聚合包。
    :type kb_action: KbActionBundle
    :param triage: 步骤 ② 分诊结果。
    :type triage: TriageCoreResult
    :returns: 主行动草稿。
    :rtype: ActionItem
    :raises ActionMappingError: hint 未注册时抛出。
    """
    hint = triage.primary_action_hint
    entry = kb_action.actions.get(hint)
    if entry is None:
        msg = f"KB-ACTION 未注册 primaryActionHint：{hint}"
        raise ActionMappingError(msg)
    return ActionItem(label=entry.label, route=entry.route)


def map_secondary_action(
    *,
    kb_action: KbActionBundle,
    triage: TriageCoreResult,
) -> ActionItem | None:
    """按 ``secondaryByPrimaryFlag`` 映射次要行动（可选）。

    :param kb_action: KB-ACTION 聚合包。
    :type kb_action: KbActionBundle
    :param triage: 步骤 ② 分诊结果。
    :type triage: TriageCoreResult
    :returns: 次行动草稿；无映射时返回 ``None``。
    :rtype: ActionItem | None
    :raises ActionMappingError: 映射 id 未注册时抛出。
    """
    action_id = kb_action.secondary_by_primary_flag.get(triage.primary_flag)
    if action_id is None:
        return None
    entry = kb_action.secondary_actions.get(action_id)
    if entry is None:
        msg = (
            f"KB-ACTION secondaryByPrimaryFlag[{triage.primary_flag!r}] "
            f"指向未注册的 secondaryActions：{action_id!r}"
        )
        raise ActionMappingError(msg)
    return ActionItem(label=entry.label, route=entry.route)
