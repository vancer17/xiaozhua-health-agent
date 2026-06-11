"""从 ``CopyTemplateResolved`` 构建 ③ 锁定字段（evidence / 行动 / 免责）。

与 ``draft_parser.backfill_draft_payload`` 共用语义，供机械文案路径与 LLM 回填一致。
"""

from __future__ import annotations

from dataclasses import dataclass

from xiaozhua_health_agent.copy.copy_types import CopyTemplateResolved
from xiaozhua_health_agent.schemas import ActionItem

__all__ = [
    "LockedDraftFields",
    "build_locked_draft_fields",
]


@dataclass(frozen=True, slots=True)
class LockedDraftFields:
    """③ 中由 ② / ③-1 锁定、不由 LLM 裁决的文案字段草稿。

    :ivar evidence: 证据列表；机械路径恒为 ``evidenceBullets`` 原文。
    :vartype evidence: tuple[str, ...]
    :ivar safety_notice: 免责声明片段；未要求时为空串。
    :vartype safety_notice: str
    :ivar primary_action: 主行动入口。
    :vartype primary_action: ActionItem
    :ivar secondary_action: 次要行动；无映射时为 ``None``。
    :vartype secondary_action: ActionItem | None
    """

    evidence: tuple[str, ...]
    safety_notice: str
    primary_action: ActionItem
    secondary_action: ActionItem | None


def build_locked_draft_fields(resolved: CopyTemplateResolved) -> LockedDraftFields:
    """从 ③-1 解析包构建锁定字段（evidence / safety / actions）。

    :param resolved: 步骤 ③-1 产出的模板解析包。
    :type resolved: CopyTemplateResolved
    :returns: 锁定字段聚合。
    :rtype: LockedDraftFields
    """
    safety_snippet = resolved.safety_notice_snippet.strip()
    return LockedDraftFields(
        evidence=resolved.evidence_bullets,
        safety_notice=safety_snippet,
        primary_action=resolved.primary_action_draft.model_copy(deep=True),
        secondary_action=(
            resolved.secondary_action_draft.model_copy(deep=True)
            if resolved.secondary_action_draft is not None
            else None
        ),
    )
