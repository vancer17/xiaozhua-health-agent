"""Agent 输出契约枚举、Literal 与子模型（与 output_schema.v1 对齐）。"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal


class OutputRiskLevel(StrEnum):
    """Agent 输出与 case 验收使用的风险等级（不含 unknown）。"""

    NORMAL = "normal"
    WATCH = "watch"
    WARNING = "warning"
    EMERGENCY = "emergency"


OutputRiskLevelLiteral = Literal["normal", "watch", "warning", "emergency"]


class ActionRouteKind(StrEnum):
    """主/次行动的路由类型（实现期可扩展，V1 以字符串 route 透传 App）。"""

    CONTACT_VET = "contact_vet"
    CHECK_DEVICE = "check_device"
    REST_OBSERVE = "rest_observe"
    RECORD_SYMPTOM = "record_symptom"
    UNKNOWN = "unknown"


ActionRouteKindLiteral = Literal[
    "contact_vet",
    "check_device",
    "rest_observe",
    "record_symptom",
    "unknown",
]
