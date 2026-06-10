"""多源风险融合（FUS-00 简化版，WP3）。"""

from __future__ import annotations

from dataclasses import dataclass

from xiaozhua_health_agent.context import DerivedFacts, TriageRiskLiteral, max_risk_level
from xiaozhua_health_agent.parse import FactSheet
from xiaozhua_health_agent.triage.triage_types import RuleHitRecord


@dataclass(frozen=True, slots=True)
class FusionResult:
    """融合产出。"""

    final_risk_level: TriageRiskLiteral
    arbitration_note: str | None
    dq_floor_active: bool


def fuse_risk(
    hits: list[RuleHitRecord],
    *,
    fact_sheet: FactSheet,
    derived: DerivedFacts,
) -> FusionResult:
    """合并规则候选、上游信号与用户硬字段升级。

    :param hits: 规则命中记录。
    :type hits: list[RuleHitRecord]
    :param fact_sheet: 客观事实。
    :type fact_sheet: FactSheet
    :param derived: 派生事实。
    :type derived: DerivedFacts
    :returns: 最终风险与仲裁说明。
    :rtype: FusionResult
    """
    candidates: list[TriageRiskLiteral] = []

    for hit in hits:
        if hit.then is None:
            continue
        if hit.then.risk is not None:
            candidates.append(hit.then.risk)
        if hit.then.risk_floor is not None:
            candidates.append(hit.then.risk_floor)

    if derived.upstream_risk != "unknown":
        candidates.append(derived.upstream_risk)  # type: ignore[arg-type]

    if derived.max_signal_risk is not None:
        candidates.append(derived.max_signal_risk)

    # 用户硬字段升级
    user_report = fact_sheet.user_report
    if user_report.seizure is True:
        candidates.append("emergency")
    if user_report.vomiting == "repeated":
        candidates.append("warning")
    if user_report.limping is True or user_report.pain is True:
        candidates.append("watch")

    dq_floor_active = _dq_floor_active(hits)
    if dq_floor_active:
        candidates.append("watch")

    if not candidates:
        candidates.append("watch")

    final = max_risk_level(candidates)
    if dq_floor_active and final == "normal":
        final = "watch"

    arbitration_note = _build_arbitration_note(final, derived)
    return FusionResult(
        final_risk_level=final,
        arbitration_note=arbitration_note,
        dq_floor_active=dq_floor_active,
    )


def _dq_floor_active(hits: list[RuleHitRecord]) -> bool:
    """DQ-01/02 是否激活风险下限。"""
    for hit in hits:
        if hit.rule_id in {"DQ-01", "DQ-02"}:
            return True
    return False


def _build_arbitration_note(
    final: TriageRiskLiteral,
    derived: DerivedFacts,
) -> str | None:
    """当最终风险低于上游信号时记录仲裁说明。"""
    notes: list[str] = []
    if derived.max_signal_risk is not None and _risk_rank(final) < _risk_rank(
        derived.max_signal_risk,
    ):
        notes.append(
            f"最终风险 {final} 低于上游 signals 最高档 {derived.max_signal_risk}",
        )
    if derived.upstream_risk not in {"unknown", final} and _risk_rank(final) < _risk_rank(
        derived.upstream_risk,  # type: ignore[arg-type]
    ):
        notes.append(
            f"最终风险 {final} 低于 healthEvidence.riskLevel {derived.upstream_risk}",
        )
    if not notes:
        return None
    return "；".join(notes)


def _risk_rank(level: TriageRiskLiteral) -> int:
    order = {"normal": 0, "watch": 1, "warning": 2, "emergency": 3}
    return order[level]
