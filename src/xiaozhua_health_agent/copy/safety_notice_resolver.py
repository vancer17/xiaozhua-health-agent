"""免责声明片段选用（``safety-notices.v1``）。"""

from __future__ import annotations

from typing import Any

from xiaozhua_health_agent.copy.copy_types import KbTplBundle
from xiaozhua_health_agent.triage import TriageCoreResult


def resolve_safety_notice_snippet(
    *,
    kb_tpl: KbTplBundle,
    triage: TriageCoreResult,
) -> str:
    """按 ``resolveRules`` 顺序选用免责声明片段文本。

    boolean 真源为 ``TriageCoreResult.safety_notice_required``；本函数只返回片段文本。

    :param kb_tpl: KB-TPL 聚合包（含 snippets 与 rules）。
    :type kb_tpl: KbTplBundle
    :param triage: 步骤 ② 锁定分诊结果。
    :type triage: TriageCoreResult
    :returns: 免责声明片段；不需要时为 ``""``。
    :rtype: str
    :raises KeyError: 规则引用的 snippetId 不存在时抛出。
    """
    for rule in kb_tpl.safety_resolve_rules:
        if _rule_matches(when=rule.when, triage=triage):
            snippet_id = rule.snippet_id
            snippet = kb_tpl.safety_snippets.get(snippet_id)
            if snippet is None:
                msg = f"未注册的 safety snippet：{snippet_id}"
                raise KeyError(msg)
            return snippet
    return kb_tpl.safety_snippets.get("SNIP-NONE", "")


def _rule_matches(*, when: dict[str, Any], triage: TriageCoreResult) -> bool:
    """判断单条 safety resolve 规则是否命中。

    :param when: 规则条件对象。
    :type when: dict[str, Any]
    :param triage: 分诊结果。
    :type triage: TriageCoreResult
    :returns: 全部条件满足时为 ``True``。
    :rtype: bool
    """
    for key, expected in when.items():
        if key == "safetyNoticeRequired":
            if triage.safety_notice_required is not expected:
                return False
            continue
        if key == "finalRiskLevel":
            if triage.final_risk_level != expected:
                return False
            continue
        if key == "primaryFlagIn":
            if not isinstance(expected, list):
                return False
            if triage.primary_flag not in expected:
                return False
            continue
        return False
    return True
