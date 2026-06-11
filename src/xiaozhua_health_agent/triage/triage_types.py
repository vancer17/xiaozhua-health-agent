"""WP3 Triage Core 中间类型定义。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.context import TriageRiskLiteral, WhenBlock
from xiaozhua_health_agent.schemas import ConfidenceLiteral

PrimaryFlagLiteral = Literal[
    "NORMAL_DAILY",
    "POST_EXERCISE",
    "FEVER_RESTING",
    "RESP_RESTING",
    "HR_RESTING_CHRONIC",
    "CHRONIC_HEART_RESP",
    "USER_DEVICE_CONFLICT",
    "REPEATED_VOMITING",
    "SENIOR_DECLINE",
    "PUPPY_FEVER",
    "HRV_STRESS",
    "LIMPING_PAIN",
    "SLOW_RECOVERY",
    "MILD_DIARRHEA",
    "POST_VACCINE",
    "DATA_MISSING",
    "DATA_STALE",
    "EMERGENCY_SEIZURE",
    "EMERGENCY_RESPIRATORY",
    "EMERGENCY_TRAUMA",
]

PrimaryActionHintLiteral = Literal[
    "emergency_now",
    "contact_vet",
    "check_device",
    "rest_observe",
]

RuleLayerLiteral = Literal["EMG", "DQ", "CTX"]


class RuleThen(BaseModel):
    """规则命中后的瘦 emit（``rules[].then``）。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    risk: TriageRiskLiteral | None = None
    risk_floor: TriageRiskLiteral | None = Field(default=None, alias="riskFloor")
    primary_flag: PrimaryFlagLiteral | None = Field(default=None, alias="primaryFlag")
    mentions_add: list[str] = Field(default_factory=list, alias="mentionsAdd")


class TriageRule(BaseModel):
    """单条分诊规则记录。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    layer: RuleLayerLiteral
    when: WhenBlock
    then: RuleThen | None = None
    priority: int | None = None
    name: str | None = None
    case_ids: list[str] = Field(default_factory=list, alias="caseIds")


class RuleHitRecord(BaseModel):
    """规则命中记录（含 emit 快照）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str
    layer: RuleLayerLiteral
    priority: int | None
    then: RuleThen | None


class TriageCoreResult(BaseModel):
    """步骤 ② 产出的锁定分诊结论与文案约束包。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    final_risk_level: TriageRiskLiteral = Field(alias="finalRiskLevel")
    confidence: ConfidenceLiteral
    primary_flag: PrimaryFlagLiteral = Field(alias="primaryFlag")
    forced_mentions: tuple[str, ...] = Field(alias="forcedMentions")
    forbidden_themes: tuple[str, ...] = Field(alias="forbiddenThemes")
    evidence_bullets: tuple[str, ...] = Field(alias="evidenceBullets")
    missing_data_user: tuple[str, ...] = Field(alias="missingDataUser")
    primary_action_hint: PrimaryActionHintLiteral = Field(alias="primaryActionHint")
    safety_notice_required: bool = Field(alias="safetyNoticeRequired")
    arbitration_note: str | None = Field(default=None, alias="arbitrationNote")
    rule_hits: tuple[str, ...] = Field(alias="ruleHits")
    bundle_version: str = Field(alias="bundleVersion")

    def to_risk_only_output(self) -> dict[str, Any]:
        """转为 risk-only 批跑用的 minimal output dict（符合 ``RiskOnlyOutput``）。"""
        return {
            "riskLevel": self.final_risk_level,
            "confidence": self.confidence,
            "scene": "health_triage",
        }
