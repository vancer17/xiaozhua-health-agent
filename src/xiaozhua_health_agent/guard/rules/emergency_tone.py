"""紧急语气守卫规则短语表（CFG-L5-02 简化）。"""

from __future__ import annotations

from typing import Final

EMERGENCY_TONE_DOWNGRADE_PHRASES: Final[tuple[str, ...]] = (
    "继续观察即可",
    "先等等",
    "先观察",
    "在家看看",
    "不用就医",
    "不用看医生",
    "无需就医",
    "问题不大",
    "应该没事",
    "不用担心",
    "先在家",
    "可以再观察",
)
"""``finalRiskLevel=emergency`` 时禁止出现的弱化就医短语（归一化后子串匹配）。"""

EMERGENCY_POSITIVE_HINTS: Final[tuple[str, ...]] = (
    "立即",
    "尽快",
    "马上",
    "立刻",
    "紧急",
    "就医",
    "兽医",
)
"""紧急场景建议在 recommendation / whenToSeeVet 中出现的紧迫或就医提示词。"""
