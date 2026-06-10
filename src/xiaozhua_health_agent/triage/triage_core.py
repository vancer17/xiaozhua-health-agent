"""Triage Core 门面编排（WP3 步骤 ②）。"""

from __future__ import annotations

from xiaozhua_health_agent.context import build_eval_context, compute_derived_facts
from xiaozhua_health_agent.parse import FactSheet
from xiaozhua_health_agent.triage.confidence_resolver import resolve_confidence
from xiaozhua_health_agent.triage.evidence_builder import build_evidence_bullets
from xiaozhua_health_agent.triage.fusion import fuse_risk
from xiaozhua_health_agent.triage.missing_data import translate_missing_data
from xiaozhua_health_agent.triage.policy_data import BUNDLE_VERSION
from xiaozhua_health_agent.triage.policy_resolve import resolve_policy_tables
from xiaozhua_health_agent.triage.primary_flag_resolver import resolve_primary_flag
from xiaozhua_health_agent.triage.rule_engine import evaluate_rules
from xiaozhua_health_agent.triage.triage_types import TriageCoreResult


def run_triage_core(fact_sheet: FactSheet) -> TriageCoreResult:
    """执行确定性分诊核，产出锁定的 ``TriageCoreResult``。

    严格顺序：DerivedFacts → 规则评估 → ResolvePrimaryFlag → Fusion
    → ConfidenceResolver → PolicyTables → missingDataUser → EvidenceBuilder。

    :param fact_sheet: 步骤 ① 产出的客观事实清单。
    :type fact_sheet: FactSheet
    :returns: 分诊结论与文案约束包。
    :rtype: TriageCoreResult
    """
    derived = compute_derived_facts(fact_sheet)
    ctx = build_eval_context(fact_sheet, derived)

    hits = evaluate_rules(ctx)
    primary_flag = resolve_primary_flag(hits)
    fusion = fuse_risk(hits, fact_sheet=fact_sheet, derived=derived)

    rule_hit_ids = tuple(hit.rule_id for hit in hits)
    confidence = resolve_confidence(
        final_risk_level=fusion.final_risk_level,
        primary_flag=primary_flag,
        rule_hits=rule_hit_ids,
        fact_sheet=fact_sheet,
        derived=derived,
        arbitration_note=fusion.arbitration_note,
    )

    policy = resolve_policy_tables(primary_flag, hits)
    missing_data_user = translate_missing_data(fact_sheet)
    evidence_bullets = build_evidence_bullets(
        primary_flag,
        fact_sheet,
        missing_data_user=missing_data_user,
    )

    return TriageCoreResult(
        finalRiskLevel=fusion.final_risk_level,
        confidence=confidence,
        primaryFlag=primary_flag,
        forcedMentions=policy.forced_mentions,
        forbiddenThemes=policy.forbidden_themes,
        evidenceBullets=evidence_bullets,
        missingDataUser=missing_data_user,
        primaryActionHint=policy.primary_action_hint,
        safetyNoticeRequired=policy.safety_notice_required,
        arbitrationNote=fusion.arbitration_note,
        ruleHits=rule_hit_ids,
        bundleVersion=BUNDLE_VERSION,
    )
