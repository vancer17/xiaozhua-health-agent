"""L5 ValidateContent 静态规则表（无 IO）。"""

from xiaozhua_health_agent.guard.rules.emergency_tone import (
    EMERGENCY_POSITIVE_HINTS,
    EMERGENCY_TONE_DOWNGRADE_PHRASES,
)
from xiaozhua_health_agent.guard.rules.evidence_policy import (
    DATA_QUALITY_NORMAL_CLAIM_PHRASES,
    UNSUPPORTED_TREND_PHRASES,
)
from xiaozhua_health_agent.guard.rules.risk_text_consistency import (
    RISK_LEVEL_REQUIRED_HINTS,
    RISK_LEVEL_WEAKENING_PHRASES,
)

__all__ = [
    "DATA_QUALITY_NORMAL_CLAIM_PHRASES",
    "EMERGENCY_POSITIVE_HINTS",
    "EMERGENCY_TONE_DOWNGRADE_PHRASES",
    "RISK_LEVEL_REQUIRED_HINTS",
    "RISK_LEVEL_WEAKENING_PHRASES",
    "UNSUPPORTED_TREND_PHRASES",
]
