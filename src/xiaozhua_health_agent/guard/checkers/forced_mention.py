"""② forcedMentions 主题覆盖检查器。"""

from __future__ import annotations

from xiaozhua_health_agent.copy import DraftCopyJSON
from xiaozhua_health_agent.eval import SynonymMap, Violation, ViolationCode
from xiaozhua_health_agent.guard.draft_corpus import build_draft_text_corpus
from xiaozhua_health_agent.guard.violation_factory import make_guard_violation
from xiaozhua_health_agent.triage import TriageCoreResult

__all__ = [
    "check_forced_mentions",
]


def check_forced_mentions(
    draft: DraftCopyJSON,
    triage: TriageCoreResult,
    *,
    synonym_map: SynonymMap,
) -> tuple[Violation, ...]:
    """检查 ② ``forcedMentions`` 主题是否在 draft 合并语料中出现。

    :param draft: 文案草稿。
    :type draft: DraftCopyJSON
    :param triage: 锁定分诊结论。
    :type triage: TriageCoreResult
    :param synonym_map: KB-SYN 同义词扩展表。
    :type synonym_map: SynonymMap
    :returns: 违规列表；全部命中时为空元组。
    :rtype: tuple[Violation, ...]
    """
    mentions = triage.forced_mentions
    if len(mentions) == 0:
        return ()

    corpus = build_draft_text_corpus(draft)
    missing: list[str] = []
    for keyword in mentions:
        candidates = synonym_map.expand_keyword(
            keyword,
            primary_flag=triage.primary_flag,
        )
        if not candidates:
            missing.append(keyword)
            continue
        if not any(candidate in corpus for candidate in candidates):
            missing.append(keyword)

    if not missing:
        return ()

    return (
        make_guard_violation(
            code=ViolationCode.FORCED_MENTION_MISSING.value,
            path="summary",
            field="summary",
            message=(f"文案未覆盖 ② 要求的必提主题：{'、'.join(missing)}。"),
            severity="MEDIUM",
        ),
    )
