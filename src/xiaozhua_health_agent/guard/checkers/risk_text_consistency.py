"""风险—文案一致性守卫检查器。"""

from __future__ import annotations

from xiaozhua_health_agent.copy import DraftCopyJSON
from xiaozhua_health_agent.eval import Violation, ViolationCode, normalize_text
from xiaozhua_health_agent.guard.rules.risk_text_consistency import (
    RISK_LEVEL_REQUIRED_HINTS,
    RISK_LEVEL_WEAKENING_PHRASES,
)
from xiaozhua_health_agent.guard.violation_factory import make_guard_violation
from xiaozhua_health_agent.triage import TriageCoreResult

__all__ = [
    "check_risk_text_consistency",
]

_CONFLICT_PRIMARY_FLAG: str = "USER_DEVICE_CONFLICT"
"""用户与设备冲突叙事主键。"""


def check_risk_text_consistency(
    draft: DraftCopyJSON,
    triage: TriageCoreResult,
) -> tuple[Violation, ...]:
    """检查文案语气是否与冻结的 ``finalRiskLevel`` 一致。

    :param draft: 文案草稿。
    :type draft: DraftCopyJSON
    :param triage: 锁定分诊结论。
    :type triage: TriageCoreResult
    :returns: 违规列表；一致时为空元组。
    :rtype: tuple[Violation, ...]
    """
    risk_level = triage.final_risk_level
    violations: list[Violation] = []

    recommendation_corpus = normalize_text(
        f"{draft.recommendation}\n{draft.when_to_see_vet}",
    )
    summary_corpus = normalize_text(draft.summary)

    weakening = RISK_LEVEL_WEAKENING_PHRASES.get(risk_level, ())
    for phrase in weakening:
        normalized_phrase = normalize_text(phrase)
        if not normalized_phrase:
            continue
        if (
            normalized_phrase in recommendation_corpus
            or normalized_phrase in summary_corpus
        ):
            violations.append(
                make_guard_violation(
                    code=ViolationCode.RISK_TEXT_INCONSISTENT.value,
                    path="summary",
                    field="summary",
                    message=(
                        f"riskLevel={risk_level} 时文案不得过度弱化；命中「{phrase}」。"
                    ),
                    severity="MEDIUM",
                ),
            )

    required_hints = RISK_LEVEL_REQUIRED_HINTS.get(risk_level, ())
    if required_hints and recommendation_corpus:
        if not any(
            normalize_text(hint) in recommendation_corpus for hint in required_hints
        ):
            violations.append(
                make_guard_violation(
                    code=ViolationCode.RISK_TEXT_INCONSISTENT.value,
                    path="recommendation",
                    field="recommendation",
                    message=(
                        f"riskLevel={risk_level} 时 recommendation / whenToSeeVet "
                        f"应体现相应就医强度（建议含："
                        f"{'、'.join(required_hints)} 等）。"
                    ),
                    severity="MEDIUM",
                ),
            )

    if triage.primary_flag == _CONFLICT_PRIMARY_FLAG:
        dismissive_phrases = ("以主人感受为准", "忽略设备", "不用管设备")
        combined = f"{summary_corpus}\n{recommendation_corpus}"
        for phrase in dismissive_phrases:
            normalized_phrase = normalize_text(phrase)
            if normalized_phrase and normalized_phrase in combined:
                violations.append(
                    make_guard_violation(
                        code=ViolationCode.RISK_TEXT_INCONSISTENT.value,
                        path="summary",
                        field="summary",
                        message=(
                            "用户与设备数据冲突时不应建议忽略设备监测；"
                            f"命中「{phrase}」。"
                        ),
                        severity="HIGH",
                    ),
                )

    return tuple(violations)
