"""跨 input / output / eval 共用的契约类型。"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal


class Confidence(StrEnum):
    """置信度档位。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


ConfidenceLiteral = Literal["low", "medium", "high"]
