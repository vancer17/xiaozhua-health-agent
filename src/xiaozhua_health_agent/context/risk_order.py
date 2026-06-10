"""风险等级序比较工具（WP2）。

供 ``DerivedFacts.max_signal_risk`` 聚合与 ``eval_when`` 的 ``signal`` / ``derived`` 原子共用，
保证与后续 fusion 语义一致。
"""

from __future__ import annotations

from typing import TypeGuard

from xiaozhua_health_agent.context.context_types import TriageRiskLiteral
from xiaozhua_health_agent.schemas import (
    SignalRiskLevelLiteral,
    UpstreamRiskLevelLiteral,
)

# 从低到高的离散风险序（不含 upstream ``unknown``）
RISK_ORDER: tuple[TriageRiskLiteral, ...] = (
    "normal",
    "watch",
    "warning",
    "emergency",
)

_RISK_RANK: dict[str, int] = {level: index for index, level in enumerate(RISK_ORDER)}


def risk_rank(level: str | None) -> int | None:
    """返回风险档位在序表中的秩；未知或 ``None`` 时返回 ``None``。

    :param level: 风险档位字符串。
    :type level: str | None
    :returns: 秩（越大越严重），无法识别时 ``None``。
    :rtype: int | None
    """
    if level is None:
        return None
    return _RISK_RANK.get(level)


def compare_risk(left: str, right: str) -> int:
    """比较两个可比较风险档位。

    :param left: 左操作数风险档。
    :type left: str
    :param right: 右操作数风险档。
    :type right: str
    :returns: ``left`` 更严重为正，相等为 0，更轻为负。
    :rtype: int
    :raises ValueError: 任一档位不在 ``RISK_ORDER`` 内。
    """
    left_rank = risk_rank(left)
    right_rank = risk_rank(right)
    if left_rank is None or right_rank is None:
        unknown = left if left_rank is None else right
        msg = f"无法比较未知风险档位: {unknown!r}"
        raise ValueError(msg)
    return left_rank - right_rank


def risk_gte(
    actual: str,
    minimum: TriageRiskLiteral | SignalRiskLevelLiteral,
) -> bool:
    """判断 ``actual`` 是否不低于 ``minimum`` 严重度。

    :param actual: 待比较的实际风险档。
    :type actual: str
    :param minimum: 下限风险档。
    :type minimum: TriageRiskLiteral | SignalRiskLevelLiteral
    :returns: ``actual`` 秩 ≥ ``minimum`` 秩时为 ``True``。
    :rtype: bool
    :raises ValueError: 档位无法识别时。
    """
    return compare_risk(actual, minimum) >= 0


def max_risk_level(
    levels: list[TriageRiskLiteral | SignalRiskLevelLiteral],
) -> TriageRiskLiteral | None:
    """从非空风险列表中取最严重档位。

    :param levels: 风险档位列表。
    :type levels: list[TriageRiskLiteral | SignalRiskLevelLiteral]
    :returns: 最严重档位；空列表时 ``None``。
    :rtype: TriageRiskLiteral | None
    """
    if not levels:
        return None
    best: TriageRiskLiteral = "normal"
    for level in levels:
        if compare_risk(level, best) > 0:
            best = level  # type: ignore[assignment]
    return best


def is_upstream_comparable_risk(
    level: UpstreamRiskLevelLiteral,
) -> TypeGuard[TriageRiskLiteral]:
    """判断 upstream 风险是否可参与序比较（排除 ``unknown``）。

    :param level: 上游综合风险档。
    :type level: UpstreamRiskLevelLiteral
    :returns: 非 ``unknown`` 时为 ``True``。
    :rtype: bool
    """
    return level != "unknown"
