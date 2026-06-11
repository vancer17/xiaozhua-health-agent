"""ValidateContent 确定性文案修补（sanitize 模式）。"""

from __future__ import annotations

from xiaozhua_health_agent.copy import (
    CopyKnowledgeBundle,
    DraftCopyJSON,
    resolve_safety_notice_snippet,
)
from xiaozhua_health_agent.guard.guard_types import ContentGuardInput
from xiaozhua_health_agent.triage import TriageCoreResult

__all__ = [
    "sanitize_draft_for_guard",
]


def sanitize_draft_for_guard(
    draft: DraftCopyJSON,
    *,
    triage: TriageCoreResult,
    copy_bundle: CopyKnowledgeBundle | None,
) -> tuple[DraftCopyJSON, bool]:
    """对文案草稿做确定性修补（当前仅补全 ``safetyNotice``）。

    :param draft: 原始文案草稿。
    :type draft: DraftCopyJSON
    :param triage: 锁定分诊结论。
    :type triage: TriageCoreResult
    :param copy_bundle: 可选知识包（含 KB-TPL safety snippets）。
    :type copy_bundle: CopyKnowledgeBundle | None
    :returns: ``(修补后 draft, 是否发生修补)`` 元组。
    :rtype: tuple[DraftCopyJSON, bool]
    """
    if not triage.safety_notice_required:
        return draft, False
    if draft.safety_notice.strip():
        return draft, False
    if copy_bundle is None:
        return draft, False

    snippet = resolve_safety_notice_snippet(
        kb_tpl=copy_bundle.kb_tpl,
        triage=triage,
    )
    if not snippet.strip():
        return draft, False

    patched = draft.model_copy(
        update={"safety_notice": snippet},
        deep=True,
    )
    return patched, True


def sanitize_guard_input(
    guard_input: ContentGuardInput,
) -> tuple[ContentGuardInput, bool]:
    """对 ``ContentGuardInput`` 内 draft 执行 sanitize（内部辅助）。

    :param guard_input: 守卫输入上下文。
    :type guard_input: ContentGuardInput
    :returns: ``(更新后的输入, 是否修补)``。
    :rtype: tuple[ContentGuardInput, bool]
    """
    patched_draft, changed = sanitize_draft_for_guard(
        guard_input.draft,
        triage=guard_input.triage,
        copy_bundle=guard_input.copy_bundle,
    )
    if not changed:
        return guard_input, False
    return (
        ContentGuardInput(
            draft=patched_draft,
            triage=guard_input.triage,
            fact_sheet=guard_input.fact_sheet,
            resolved=guard_input.resolved,
            copy_bundle=guard_input.copy_bundle,
            synonym_map=guard_input.synonym_map,
        ),
        True,
    )
