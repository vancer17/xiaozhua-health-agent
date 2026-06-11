"""风险—文案一致性规则表（CFG-L5-03 简化）。"""

from __future__ import annotations

from typing import Final

RISK_LEVEL_REQUIRED_HINTS: Final[dict[str, tuple[str, ...]]] = {
    "warning": (
        "兽医",
        "就医",
        "联系",
        "尽快",
    ),
    "emergency": (
        "立即",
        "尽快",
        "马上",
        "就医",
        "兽医",
        "紧急",
    ),
}
"""各风险档位在 recommendation + whenToSeeVet 合并语料中建议出现的提示词。"""

RISK_LEVEL_WEAKENING_PHRASES: Final[dict[str, tuple[str, ...]]] = {
    "warning": (
        "不用担心",
        "应该没事",
        "问题不大",
        "无需就医",
        "不用看医生",
    ),
    "watch": (
        "一定没事",
        "不用担心",
    ),
}
"""各风险档位不宜出现的过度弱化短语。"""
