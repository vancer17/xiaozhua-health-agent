"""WP4 ③-1 模板解析器（Template Resolver）。

将 ``FactSheet`` + 锁定的 ``TriageCoreResult`` 解析为 ``CopyTemplateResolved``，
供 ③-2 LLM 填槽与 WP5 模板兜底消费。
"""

from __future__ import annotations

from xiaozhua_health_agent.copy.action_mapper import (
    map_primary_action,
    map_secondary_action,
)
from xiaozhua_health_agent.copy.copy_bundle import load_default_copy_knowledge_bundle
from xiaozhua_health_agent.copy.copy_types import (
    CopyKnowledgeBundle,
    CopyTemplateResolved,
    KbTplBundle,
)
from xiaozhua_health_agent.copy.forbidden_union import merge_forbidden_for_copy
from xiaozhua_health_agent.copy.inline_rules import apply_inline_summary_rules
from xiaozhua_health_agent.copy.safety_notice_resolver import (
    resolve_safety_notice_snippet,
)
from xiaozhua_health_agent.copy.slot_filler import fill_template_slots
from xiaozhua_health_agent.copy.template_lookup import (
    build_template_id,
    lookup_template,
)
from xiaozhua_health_agent.parse import FactSheet
from xiaozhua_health_agent.triage import TriageCoreResult


def resolve_copy_template(
    fact_sheet: FactSheet,
    triage: TriageCoreResult,
    *,
    bundle: CopyKnowledgeBundle | None = None,
) -> CopyTemplateResolved:
    """执行步骤 ③-1：查表、填槽、合规注入，产出 ``CopyTemplateResolved``。

    不修改 ``TriageCoreResult`` 中任何医学裁决字段；不调用 LLM。

    :param fact_sheet: 步骤 ① 客观事实清单。
    :type fact_sheet: FactSheet
    :param triage: 步骤 ② 锁定分诊结论与文案约束包。
    :type triage: TriageCoreResult
    :param bundle: 可选知识资产聚合包；省略时使用默认缓存制品。
    :type bundle: CopyKnowledgeBundle | None
    :returns: 已解析文案模板包。
    :rtype: CopyTemplateResolved
    :raises KeyError: 槽位或 safety snippet 未注册时抛出。
    :raises xiaozhua_health_agent.copy.action_mapper.ActionMappingError: 行动映射失败时抛出。
    """
    knowledge = bundle if bundle is not None else load_default_copy_knowledge_bundle()
    kb_tpl = knowledge.kb_tpl

    template_id = build_template_id(
        final_risk_level=triage.final_risk_level,
        primary_flag=triage.primary_flag,
    )
    lookup = lookup_template(
        kb_tpl=kb_tpl,
        template_id=template_id,
        final_risk_level=triage.final_risk_level,
    )

    filled_slots = fill_template_slots(
        slot_ids=lookup.binding_slots,
        slot_definitions=kb_tpl.slots,
        fact_sheet=fact_sheet,
        triage=triage,
        summary_slot_priority=lookup.summary_slot_priority,
    )

    summary_outline = apply_inline_summary_rules(
        summary_outline=lookup.summary_outline,
        fact_sheet=fact_sheet,
    )

    safety_snippet = resolve_safety_notice_snippet(kb_tpl=kb_tpl, triage=triage)
    primary_action = map_primary_action(kb_action=knowledge.kb_action, triage=triage)
    secondary_action = map_secondary_action(
        kb_action=knowledge.kb_action, triage=triage
    )

    forbidden = merge_forbidden_for_copy(
        forbidden_themes=triage.forbidden_themes,
        kb_forbid_patterns=knowledge.kb_forbid.forbidden_patterns,
    )

    tone_profile = kb_tpl.tone_profiles.get(lookup.tone_profile_id)
    evidence_instruction = _resolve_evidence_instruction(
        kb_tpl=kb_tpl,
        template_id=template_id,
        used_fallback=lookup.used_fallback,
    )

    return CopyTemplateResolved(
        template_id=template_id,
        resolved_lookup_key=lookup.resolved_lookup_key,
        used_fallback=lookup.used_fallback,
        risk_level_mismatch=lookup.risk_level_mismatch,
        tone_profile_id=lookup.tone_profile_id,
        evidence_style=lookup.evidence_style,
        title_pattern=lookup.title_pattern,
        summary_outline=summary_outline,
        recommendation_template=lookup.recommendation_template,
        when_to_see_vet_template=lookup.when_to_see_vet_template,
        filled_slots=filled_slots,
        evidence_bullets=triage.evidence_bullets,
        required_mentions=triage.forced_mentions,
        forbidden=forbidden,
        llm_instructions=lookup.llm_instructions,
        safety_notice_snippet=safety_snippet,
        primary_action_hint=triage.primary_action_hint,
        primary_action_draft=primary_action,
        secondary_action_draft=secondary_action,
        tone_profile=tone_profile,
        evidence_instruction=evidence_instruction,
    )


def _resolve_evidence_instruction(
    *,
    kb_tpl: KbTplBundle,
    template_id: str,
    used_fallback: bool,
) -> str | None:
    """从主模板 copy 块读取可选 ``evidenceInstruction``。

    :param kb_tpl: KB-TPL 聚合包。
    :type kb_tpl: KbTplBundle
    :param template_id: 请求模板主键。
    :type template_id: str
    :param used_fallback: 是否使用了 fallback 模板。
    :type used_fallback: bool
    :returns: evidence 改写说明；fallback 或无字段时返回 ``None``。
    :rtype: str | None
    """
    if used_fallback:
        return None
    entry = kb_tpl.templates.get(template_id)
    if entry is None:
        return None
    return entry.copy_block.evidence_instruction
