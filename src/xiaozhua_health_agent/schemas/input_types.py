"""Agent 入参子模型与 input_schema.v1 枚举 / Literal。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.schemas.common_types import ConfidenceLiteral

# ---------------------------------------------------------------------------
# 枚举（仅作常量分组；模型字段使用 Literal，避免 Pydantic 版本差异）
# ---------------------------------------------------------------------------


class Scene(StrEnum):
    """Agent 场景枚举。"""

    HEALTH_TRIAGE = "health_triage"


class Species(StrEnum):
    """宠物物种。"""

    DOG = "dog"
    CAT = "cat"
    UNKNOWN = "unknown"


class Sex(StrEnum):
    """宠物性别。"""

    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class DataQuality(StrEnum):
    """设备数据质量。"""

    GOOD = "good"
    PARTIAL = "partial"
    STALE = "stale"
    MISSING = "missing"


class ActivityLevel(StrEnum):
    """活动强度。"""

    RESTING = "resting"
    LIGHT = "light"
    ACTIVE = "active"
    INTENSE = "intense"
    UNKNOWN = "unknown"


class SleepQuality(StrEnum):
    """睡眠质量。"""

    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    UNKNOWN = "unknown"


class UpstreamRiskLevel(StrEnum):
    """上游 healthEvidence 风险等级（含 unknown）。"""

    NORMAL = "normal"
    WATCH = "watch"
    WARNING = "warning"
    EMERGENCY = "emergency"
    UNKNOWN = "unknown"


class SignalRiskLevel(StrEnum):
    """单条 signal 风险等级。"""

    NORMAL = "normal"
    WATCH = "watch"
    WARNING = "warning"
    EMERGENCY = "emergency"


class SignalId(StrEnum):
    """健康信号标识。"""

    TEMPERATURE = "temperature"
    RESPIRATORY = "respiratory"
    HEART_RATE = "heart_rate"
    HRV = "hrv"
    PAIN = "pain"
    RECOVERY = "recovery"
    MISSING_DATA = "missing_data"
    USER_REPORT = "user_report"
    OTHER = "other"


class SignalCategory(StrEnum):
    """信号分类。"""

    VITAL = "vital"
    BEHAVIOR = "behavior"
    RECOVERY = "recovery"
    USER_REPORT = "user_report"
    DATA_QUALITY = "data_quality"


class Appetite(StrEnum):
    """食欲状态。"""

    NORMAL = "normal"
    REDUCED = "reduced"
    NONE = "none"
    UNKNOWN = "unknown"


class Drinking(StrEnum):
    """饮水状态。"""

    NORMAL = "normal"
    INCREASED = "increased"
    REDUCED = "reduced"
    UNKNOWN = "unknown"


class Energy(StrEnum):
    """精力状态。"""

    NORMAL = "normal"
    LOWER = "lower"
    VERY_LOW = "very_low"
    UNKNOWN = "unknown"


class Vomiting(StrEnum):
    """呕吐情况。"""

    NONE = "none"
    ONCE = "once"
    REPEATED = "repeated"
    UNKNOWN = "unknown"


class Diarrhea(StrEnum):
    """腹泻情况。"""

    NONE = "none"
    MILD = "mild"
    SEVERE = "severe"
    UNKNOWN = "unknown"


class RecentExercise(StrEnum):
    """近期运动强度。"""

    NONE = "none"
    LIGHT = "light"
    MODERATE = "moderate"
    INTENSE = "intense"
    UNKNOWN = "unknown"


class AgeRisk(StrEnum):
    """年龄风险档。"""

    PUPPY_KITTEN = "puppy_kitten"
    SENIOR = "senior"
    NORMAL = "normal"
    UNKNOWN = "unknown"


class MissingDataItem(StrEnum):
    """缺失数据项标识。"""

    TEMPERATURE = "temperature"
    HEART_RATE = "heart_rate"
    RESPIRATORY_RATE = "respiratory_rate"
    HRV = "hrv"
    ACTIVITY = "activity"
    USER_REPORT = "user_report"
    DEVICE_FRESHNESS = "device_freshness"
    PET_PROFILE = "pet_profile"
    DRINKING = "drinking"
    OTHER = "other"


# Literal 类型别名（字段注解使用这些，而非 StrEnum 本身）
SceneLiteral = Literal["health_triage"]
SpeciesLiteral = Literal["dog", "cat", "unknown"]
SexLiteral = Literal["male", "female", "unknown"]
DataQualityLiteral = Literal["good", "partial", "stale", "missing"]
ActivityLevelLiteral = Literal["resting", "light", "active", "intense", "unknown"]
SleepQualityLiteral = Literal["good", "fair", "poor", "unknown"]
UpstreamRiskLevelLiteral = Literal["normal", "watch", "warning", "emergency", "unknown"]
SignalRiskLevelLiteral = Literal["normal", "watch", "warning", "emergency"]
SignalIdLiteral = Literal[
    "temperature",
    "respiratory",
    "heart_rate",
    "hrv",
    "pain",
    "recovery",
    "missing_data",
    "user_report",
    "other",
]
SignalCategoryLiteral = Literal[
    "vital", "behavior", "recovery", "user_report", "data_quality"
]
AppetiteLiteral = Literal["normal", "reduced", "none", "unknown"]
DrinkingLiteral = Literal["normal", "increased", "reduced", "unknown"]
EnergyLiteral = Literal["normal", "lower", "very_low", "unknown"]
VomitingLiteral = Literal["none", "once", "repeated", "unknown"]
DiarrheaLiteral = Literal["none", "mild", "severe", "unknown"]
RecentExerciseLiteral = Literal["none", "light", "moderate", "intense", "unknown"]
AgeRiskLiteral = Literal["puppy_kitten", "senior", "normal", "unknown"]
MissingDataItemLiteral = Literal[
    "temperature",
    "heart_rate",
    "respiratory_rate",
    "hrv",
    "activity",
    "user_report",
    "device_freshness",
    "pet_profile",
    "drinking",
    "other",
]

# ---------------------------------------------------------------------------
# 入参子模型
# ---------------------------------------------------------------------------


class PetProfile(BaseModel):
    """宠物档案。"""

    model_config = ConfigDict(extra="forbid")

    pet_id: str = Field(alias="petId", description="宠物唯一标识。")
    name: str = Field(description="宠物名称。")
    species: SpeciesLiteral = Field(description="物种：狗、猫或未知。")
    breed: str | None = Field(default=None, description="品种，未知可为 null。")
    sex: SexLiteral | None = Field(default=None, description="性别。")
    age_months: float | None = Field(
        alias="ageMonths",
        description="月龄，未知可为 null。",
    )
    weight_kg: float | None = Field(
        alias="weightKg",
        description="体重（千克），未知可为 null。",
    )
    neutered: bool | None = Field(default=None, description="是否绝育。")
    chronic_conditions: list[str] = Field(
        alias="chronicConditions",
        default_factory=list,
        description="慢性病史列表。",
    )
    medications: list[str] = Field(
        default_factory=list,
        description="当前用药列表。",
    )
    allergies: list[str] = Field(
        default_factory=list,
        description="过敏史列表。",
    )


class DeviceState(BaseModel):
    """设备与数据质量状态。"""

    model_config = ConfigDict(extra="forbid")

    device_online: bool = Field(alias="deviceOnline", description="设备是否在线。")
    battery_level: float | None = Field(
        alias="batteryLevel",
        default=None,
        description="电量百分比，未知可为 null。",
    )
    last_seen_at: datetime | None = Field(
        alias="lastSeenAt",
        default=None,
        description="设备最近上报时间。",
    )
    collar_id: str | None = Field(
        alias="collarId",
        default=None,
        description="项圈设备 ID。",
    )
    data_quality: DataQualityLiteral = Field(
        alias="dataQuality",
        description="当前数据质量：good / partial / stale / missing。",
    )
    warning_text: str | None = Field(
        alias="warningText",
        default=None,
        description="设备侧告警文案。",
    )


class Vitals(BaseModel):
    """生命体征快照。"""

    model_config = ConfigDict(extra="forbid")

    temperature_c: float | None = Field(
        alias="temperatureC",
        default=None,
        description="体温（摄氏度）。",
    )
    heart_rate_bpm: float | None = Field(
        alias="heartRateBpm",
        default=None,
        description="心率（次/分）。",
    )
    respiratory_rate_bpm: float | None = Field(
        alias="respiratoryRateBpm",
        default=None,
        description="呼吸率（次/分）。",
    )
    hrv_ms: float | None = Field(
        alias="hrvMs",
        default=None,
        description="心率变异性（毫秒）。",
    )
    steps_today: float | None = Field(
        alias="stepsToday",
        default=None,
        description="当日步数。",
    )
    activity_level: ActivityLevelLiteral = Field(
        alias="activityLevel",
        default="unknown",
        description="活动强度档位。",
    )
    sleep_quality: SleepQualityLiteral = Field(
        alias="sleepQuality",
        default="unknown",
        description="睡眠质量档位。",
    )
    updated_at: datetime | None = Field(
        alias="updatedAt",
        default=None,
        description="体征数据更新时间。",
    )


class HealthSignal(BaseModel):
    """上游 healthEvidence 中的单条信号。"""

    model_config = ConfigDict(extra="forbid")

    id: SignalIdLiteral = Field(description="信号类型标识。")
    label: str = Field(description="信号展示标签。")
    category: SignalCategoryLiteral = Field(description="信号分类。")
    risk_level: SignalRiskLevelLiteral = Field(
        alias="riskLevel",
        description="该信号的风险等级。",
    )
    value: float | str | None = Field(
        default=None,
        description="信号当前值，可为数值或字符串。",
    )
    unit: str | None = Field(default=None, description="数值单位。")
    baseline: float | str | None = Field(
        default=None,
        description="个体或参考基线。",
    )
    reason: str = Field(description="上游给出该信号的原因说明。")
    confidence: ConfidenceLiteral = Field(description="上游对该信号的确信度。")
    updated_at: datetime | None = Field(
        alias="updatedAt",
        default=None,
        description="信号更新时间。",
    )


class HealthEvidence(BaseModel):
    """上游聚合健康证据。"""

    model_config = ConfigDict(extra="forbid")

    risk_level: UpstreamRiskLevelLiteral = Field(
        alias="riskLevel",
        description="上游综合风险等级，数据不足时可为 unknown。",
    )
    risk_label: str = Field(alias="riskLabel", description="上游风险标签文案。")
    display_claim: str = Field(
        alias="displayClaim",
        description="上游展示给用户的结论摘要。",
    )
    recommendation_text: str = Field(
        alias="recommendationText",
        description="上游建议文案。",
    )
    confidence: ConfidenceLiteral = Field(description="上游综合置信度。")
    signals: list[HealthSignal] = Field(
        default_factory=list,
        description="结构化信号列表。",
    )


class UserReport(BaseModel):
    """用户自述与结构化症状字段。"""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="用户自由文本描述。")
    duration: str | None = Field(default=None, description="症状持续时间描述。")
    symptoms: list[str] = Field(
        default_factory=list,
        description="用户勾选或提取的症状关键词。",
    )
    appetite: AppetiteLiteral = Field(
        default="unknown",
        description="食欲状态。",
    )
    drinking: DrinkingLiteral = Field(
        default="unknown",
        description="饮水状态。",
    )
    energy: EnergyLiteral = Field(
        default="unknown",
        description="精力状态。",
    )
    vomiting: VomitingLiteral = Field(
        default="unknown",
        description="呕吐情况。",
    )
    diarrhea: DiarrheaLiteral = Field(
        default="unknown",
        description="腹泻情况。",
    )
    coughing: bool | None = Field(default=None, description="是否咳嗽。")
    breathing_difficulty: bool | None = Field(
        alias="breathingDifficulty",
        default=None,
        description="是否呼吸困难。",
    )
    pain: bool | None = Field(default=None, description="是否疼痛。")
    limping: bool | None = Field(default=None, description="是否跛行。")
    seizure: bool | None = Field(default=None, description="是否抽搐。")
    trauma: bool | None = Field(default=None, description="是否外伤。")


class Context(BaseModel):
    """环境与情境修饰信息。"""

    model_config = ConfigDict(extra="forbid")

    environment_temp_c: float | None = Field(
        alias="environmentTempC",
        default=None,
        description="环境温度（摄氏度）。",
    )
    recent_exercise: RecentExerciseLiteral = Field(
        alias="recentExercise",
        default="unknown",
        description="近期运动强度。",
    )
    recent_vaccination: bool | None = Field(
        alias="recentVaccination",
        default=None,
        description="是否近期接种疫苗。",
    )
    recent_meal: bool | None = Field(
        alias="recentMeal",
        default=None,
        description="是否近期进食。",
    )
    age_risk: AgeRiskLiteral = Field(
        alias="ageRisk",
        default="unknown",
        description="年龄风险档：幼宠、老年、正常或未知。",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="额外情境备注。",
    )
