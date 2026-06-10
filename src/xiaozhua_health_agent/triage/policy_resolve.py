"""PolicyTablesResolve（WP3）。"""

from __future__ import annotations

from dataclasses import dataclass

from xiaozhua_health_agent.triage.policy_data import (
    ACTION_BY_FLAG,
    FORBIDDEN_BY_FLAG,
    FORCED_MENTIONS_BY_FLAG,
    GLOBAL_FORBIDDEN_THEMES,
    SAFETY_BY_FLAG,
)
from xiaozhua_health_agent.triage.triage_types import (
    PrimaryActionHintLiteral,
    PrimaryFlagLiteral,
    RuleHitRecord,
)


@dataclass(frozen=True, slots=True)
class PolicyResolveResult:
    """PolicyTables 查表结果。"""

    forced_mentions: tuple[str, ...]
    forbidden_themes: tuple[str, ...]
    safety_notice_required: bool
    primary_action_hint: PrimaryActionHintLiteral


def resolve_policy_tables(
    primary_flag: PrimaryFlagLiteral,
    hits: list[RuleHitRecord],
) -> PolicyResolveResult:
    """按 primaryFlag 查四表并合并规则层 mentionsAdd。"""
    base_mentions = list(FORCED_MENTIONS_BY_FLAG[primary_flag])
    for hit in hits:
        if hit.then is None:
            continue
        for mention in hit.then.mentions_add:
            if mention not in base_mentions:
                base_mentions.append(mention)

    flag_forbidden = list(FORBIDDEN_BY_FLAG[primary_flag])
    forbidden_set = set(GLOBAL_FORBIDDEN_THEMES) | set(flag_forbidden)
    forbidden = tuple(sorted(forbidden_set))

    return PolicyResolveResult(
        forced_mentions=tuple(base_mentions),
        forbidden_themes=forbidden,
        safety_notice_required=SAFETY_BY_FLAG[primary_flag],
        primary_action_hint=ACTION_BY_FLAG[primary_flag],
    )
