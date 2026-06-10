"""ResolvePrimaryFlag（WP3）。"""

from __future__ import annotations

from xiaozhua_health_agent.triage.policy_data import PRIMARY_FLAG_TIERS
from xiaozhua_health_agent.triage.triage_types import PrimaryFlagLiteral, RuleHitRecord


def resolve_primary_flag(hits: list[RuleHitRecord]) -> PrimaryFlagLiteral:
    """从全部命中规则中选取唯一 primaryFlag。

    :param hits: 规则命中记录。
    :type hits: list[RuleHitRecord]
    :returns: 叙事主键。
    :rtype: PrimaryFlagLiteral
    :raises ValueError: 无候选 primaryFlag 时。
    """
    candidates: list[tuple[PrimaryFlagLiteral, int | None, str]] = []
    for hit in hits:
        if hit.then is None or hit.then.primary_flag is None:
            continue
        candidates.append((hit.then.primary_flag, hit.priority, hit.rule_id))

    if not candidates:
        msg = "无可用 primaryFlag 候选"
        raise ValueError(msg)

    flag_rank = _build_flag_rank_map()
    best_tier = min(flag_rank[flag] for flag, _, _ in candidates)
    tier_candidates = [
        (flag, priority, rule_id)
        for flag, priority, rule_id in candidates
        if flag_rank[flag] == best_tier
    ]

    if len(tier_candidates) == 1:
        return tier_candidates[0][0]

    # 同层 tie-break：CTX priority 数值最小者优先
    tier_candidates.sort(
        key=lambda item: (
            item[1] if item[1] is not None else 999,
            item[2],
        ),
    )
    return tier_candidates[0][0]


def _build_flag_rank_map() -> dict[PrimaryFlagLiteral, int]:
    """构建 primaryFlag → 叙事层级 rank（越小越高）。"""
    mapping: dict[PrimaryFlagLiteral, int] = {}
    for tier_index, tier in enumerate(PRIMARY_FLAG_TIERS):
        for flag in tier:
            mapping[flag] = tier_index
    return mapping
