"""KB-TPL 模板查表与 fallback 解析。"""

from __future__ import annotations

from xiaozhua_health_agent.copy.copy_types import (
    FallbackLookupKeyLiteral,
    FallbackTemplateEntry,
    KbTplBundle,
    TemplateEntry,
    TemplateLookupResult,
)
from xiaozhua_health_agent.context import TriageRiskLiteral


def build_template_id(
    *,
    final_risk_level: TriageRiskLiteral,
    primary_flag: str,
) -> str:
    """构建模板主键 ``{riskLevel}.{primaryFlag}``。

    :param final_risk_level: ② 锁定的最终风险等级。
    :type final_risk_level: TriageRiskLiteral
    :param primary_flag: ② 锁定的情境主键。
    :type primary_flag: str
    :returns: 模板查表键。
    :rtype: str
    """
    return f"{final_risk_level}.{primary_flag}"


def lookup_template(
    *,
    kb_tpl: KbTplBundle,
    template_id: str,
    final_risk_level: TriageRiskLiteral,
) -> TemplateLookupResult:
    """按主键查找模板，未命中时走 ``fallback-by-risk`` 链。

    查找顺序（``kb-tpl-template-spec.md`` §3.2）：

    1. ``templates[templateId]``
    2. ``fallbacks[finalRiskLevel]``
    3. ``fallbacks.DEFAULT``

    :param kb_tpl: KB-TPL 聚合包。
    :type kb_tpl: KbTplBundle
    :param template_id: 请求的主键。
    :type template_id: str
    :param final_risk_level: 最终风险等级（fallback 键）。
    :type final_risk_level: TriageRiskLiteral
    :returns: 查表结果（含是否 fallback 与 risk 不一致标记）。
    :rtype: TemplateLookupResult
    :raises KeyError: fallback 链断裂（缺少 risk 与 DEFAULT）时抛出。
    """
    entry = kb_tpl.templates.get(template_id)
    if entry is not None:
        return _from_template_entry(
            requested_template_id=template_id,
            entry=entry,
            used_fallback=False,
        )

    fallback_key: FallbackLookupKeyLiteral = final_risk_level
    fallback = kb_tpl.fallbacks.get(fallback_key)
    resolved_key: FallbackLookupKeyLiteral = fallback_key
    if fallback is None:
        fallback = kb_tpl.fallbacks.get("DEFAULT")
        resolved_key = "DEFAULT"
    if fallback is None:
        msg = f"fallback-by-risk 缺少 {final_risk_level!r} 与 DEFAULT 条目。"
        raise KeyError(msg)

    return _from_fallback_entry(
        requested_template_id=template_id,
        resolved_lookup_key=resolved_key,
        fallback=fallback,
        used_fallback=True,
    )


def _from_template_entry(
    *,
    requested_template_id: str,
    entry: TemplateEntry,
    used_fallback: bool,
) -> TemplateLookupResult:
    """由主模板条目构建查表结果。

    :param requested_template_id: 请求主键。
    :type requested_template_id: str
    :param entry: 命中模板。
    :type entry: TemplateEntry
    :param used_fallback: 是否走了 fallback。
    :type used_fallback: bool
    :returns: 查表结果。
    :rtype: TemplateLookupResult
    """
    prefix_risk = requested_template_id.split(".", 1)[0]
    risk_mismatch = entry.meta.risk_level != prefix_risk

    return TemplateLookupResult(
        requested_template_id=requested_template_id,
        resolved_lookup_key=requested_template_id,
        used_fallback=used_fallback,
        title_pattern=entry.copy_block.title_pattern,
        summary_outline=tuple(entry.copy_block.summary_outline),
        recommendation_template=entry.copy_block.recommendation_template,
        when_to_see_vet_template=entry.copy_block.when_to_see_vet_template,
        tone_profile_id=entry.meta.tone_profile_id,
        evidence_style=entry.meta.evidence_style,
        binding_slots=tuple(entry.binding.slots),
        summary_slot_priority=dict(entry.binding.summary_slot_priority),
        llm_instructions=entry.guidance.llm_instructions,
        risk_level_mismatch=risk_mismatch,
    )


def _from_fallback_entry(
    *,
    requested_template_id: str,
    resolved_lookup_key: str,
    fallback: FallbackTemplateEntry,
    used_fallback: bool,
) -> TemplateLookupResult:
    """由 fallback 条目构建查表结果。

    :param requested_template_id: 原始请求主键。
    :type requested_template_id: str
    :param resolved_lookup_key: 实际 fallback 键。
    :type resolved_lookup_key: str
    :param fallback: fallback 模板。
    :type fallback: FallbackTemplateEntry
    :param used_fallback: 恒为 ``True``。
    :type used_fallback: bool
    :returns: 查表结果（无 binding slots）。
    :rtype: TemplateLookupResult
    """
    return TemplateLookupResult(
        requested_template_id=requested_template_id,
        resolved_lookup_key=resolved_lookup_key,
        used_fallback=used_fallback,
        title_pattern=fallback.title_pattern,
        summary_outline=tuple(fallback.summary_outline),
        recommendation_template=fallback.recommendation_template,
        when_to_see_vet_template=fallback.when_to_see_vet_template,
        tone_profile_id=fallback.tone_profile_id,
        evidence_style=fallback.evidence_style,
        binding_slots=(),
        summary_slot_priority={},
        llm_instructions="",
        risk_level_mismatch=False,
    )
