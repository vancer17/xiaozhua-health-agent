"""紧急语气守卫检查器。"""

from __future__ import annotations

from xiaozhua_health_agent.copy import DraftCopyJSON
from xiaozhua_health_agent.eval import Violation, ViolationCode, normalize_text
from xiaozhua_health_agent.guard.rules.emergency_tone import (
    EMERGENCY_POSITIVE_HINTS,
    EMERGENCY_TONE_DOWNGRADE_PHRASES,
)
from xiaozhua_health_agent.guard.violation_factory import make_guard_violation
from xiaozhua_health_agent.triage import TriageCoreResult

__all__ = [
    "check_emergency_tone",
]

_EMERGENCY_PRIMARY_FLAGS: frozenset[str] = frozenset(
    {
        "EMERGENCY_SEIZURE",
        "EMERGENCY_RESPIRATORY",
        "EMERGENCY_TRAUMA",
    },
)
"""视为紧急叙事主键的 ``primaryFlag`` 集合。"""

_GUARD_FIELDS: tuple[tuple[str, str], ...] = (
    ("summary", "summary"),
    ("recommendation", "recommendation"),
    ("whenToSeeVet", "when_to_see_vet"),
)
"""紧急语气扫描的字段（path, draft 属性名）。"""


def check_emergency_tone(
    draft: DraftCopyJSON,
    triage: TriageCoreResult,
) -> tuple[Violation, ...]:
    """当分诊为紧急时，检测文案是否弱化就医紧迫性。

    :param draft: 文案草稿。
    :type draft: DraftCopyJSON
    :param triage: 锁定分诊结论。
    :type triage: TriageCoreResult
    :returns: 违规列表；非紧急或未命中弱化短语时为空。
    :rtype: tuple[Violation, ...]
    """
    if not _is_emergency_context(triage):
        return ()

    violations: list[Violation] = []
    for path, attr_name in _GUARD_FIELDS:
        raw_text = getattr(draft, attr_name)
        normalized = normalize_text(raw_text)
        if not normalized:
            continue
        for phrase in EMERGENCY_TONE_DOWNGRADE_PHRASES:
            normalized_phrase = normalize_text(phrase)
            if normalized_phrase and normalized_phrase in normalized:
                violations.append(
                    make_guard_violation(
                        code=ViolationCode.EMERGENCY_TONE_WEAK.value,
                        path=path,
                        field=path,
                        message=(
                            f"紧急场景文案不得弱化就医紧迫性；"
                            f"字段 {path} 命中弱化短语「{phrase}」。"
                        ),
                        severity="HIGH",
                    ),
                )

    recommendation_corpus = normalize_text(
        f"{draft.recommendation}\n{draft.when_to_see_vet}",
    )
    if recommendation_corpus and not _has_positive_emergency_hint(
        recommendation_corpus,
    ):
        violations.append(
            make_guard_violation(
                code=ViolationCode.EMERGENCY_TONE_WEAK.value,
                path="recommendation",
                field="recommendation",
                message=(
                    "紧急场景 recommendation / whenToSeeVet 应体现紧迫就医导向"
                    "（如「立即」「尽快」「兽医」「就医」等）。"
                ),
                severity="MEDIUM",
            ),
        )

    return tuple(violations)


def _is_emergency_context(triage: TriageCoreResult) -> bool:
    """判断是否处于紧急审查上下文（内部辅助）。

    :param triage: 分诊结论。
    :type triage: TriageCoreResult
    :returns: 紧急时为 ``True``。
    :rtype: bool
    """
    if triage.final_risk_level == "emergency":
        return True
    return triage.primary_flag in _EMERGENCY_PRIMARY_FLAGS


def _has_positive_emergency_hint(corpus: str) -> bool:
    """合并语料是否包含紧迫就医正向提示词（内部辅助）。

    :param corpus: 归一化后的合并语料。
    :type corpus: str
    :returns: 包含任一正向提示词时为 ``True``。
    :rtype: bool
    """
    for hint in EMERGENCY_POSITIVE_HINTS:
        normalized_hint = normalize_text(hint)
        if normalized_hint and normalized_hint in corpus:
            return True
    return False
