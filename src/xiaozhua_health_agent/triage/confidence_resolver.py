"""ConfidenceResolver L / H′ / H / M（WP3）。"""

from __future__ import annotations

from xiaozhua_health_agent.context import DerivedFacts, TriageRiskLiteral
from xiaozhua_health_agent.parse import FactSheet
from xiaozhua_health_agent.schemas import ConfidenceLiteral
from xiaozhua_health_agent.triage.triage_types import PrimaryFlagLiteral


def resolve_confidence(
    *,
    final_risk_level: TriageRiskLiteral,
    primary_flag: PrimaryFlagLiteral,
    rule_hits: tuple[str, ...],
    fact_sheet: FactSheet,
    derived: DerivedFacts,
    arbitration_note: str | None,
) -> ConfidenceLiteral:
    """按固定顺序计算 confidence。

    :returns: low / medium / high。
    :rtype: ConfidenceLiteral
    """
    device = fact_sheet.device

    # L: missing / vitalsCoreMissing / stale
    if (
        device.data_quality == "missing"
        or derived.vitals_core_missing
        or device.data_quality == "stale"
    ):
        return "low"

    # H′: emergency + EMG + seizure
    if (
        final_risk_level == "emergency"
        and _has_emg_hit(rule_hits)
        and fact_sheet.user_report.seizure is True
    ):
        return "high"

    # H: good + not conflict + multi-source agreement
    if device.data_quality == "good" and primary_flag != "USER_DEVICE_CONFLICT":
        if final_risk_level == "normal" and not fact_sheet.missing_data:
            return "high"
        if final_risk_level in {"warning", "emergency"} and _sources_agree(
            final_risk_level,
            derived,
            arbitration_note,
        ):
            return "high"

    return "medium"


def _has_emg_hit(rule_hits: tuple[str, ...]) -> bool:
    return any(hit.startswith("EMG-") for hit in rule_hits)


def _sources_agree(
    final_risk: TriageRiskLiteral,
    derived: DerivedFacts,
    arbitration_note: str | None,
) -> bool:
    if arbitration_note:
        return False
    upstream = derived.upstream_risk
    signal = derived.max_signal_risk
    if upstream != "unknown" and upstream != final_risk:
        return False
    if signal is not None and _risk_rank(signal) > _risk_rank(final_risk):
        return False
    return True


def _risk_rank(level: TriageRiskLiteral) -> int:
    order = {"normal": 0, "watch": 1, "warning": 2, "emergency": 3}
    return order[level]
