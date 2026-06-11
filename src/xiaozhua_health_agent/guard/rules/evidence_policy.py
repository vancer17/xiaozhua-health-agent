"""证据真实性审查规则短语表（CFG-L5-06 简化）。"""

from __future__ import annotations

from typing import Final

UNSUPPORTED_TREND_PHRASES: Final[tuple[str, ...]] = (
    "过去一周",
    "过去几天",
    "持续下降",
    "持续升高",
    "越来越",
    "一直",
    "长期以来",
    "近期趋势",
    "较基线",
    "高于基线",
    "低于基线",
)
"""输入未提供历史趋势时，evidence/summary 中不宜出现的表述。"""

DATA_QUALITY_NORMAL_CLAIM_PHRASES: Final[tuple[str, ...]] = (
    "一切正常",
    "目前健康正常",
    "当前正常",
    "当前健康正常",
    "状态正常",
    "应该没事",
    "没有异常",
)
"""数据缺失/过期场景禁止暗示「当前健康正常」的短语。"""
