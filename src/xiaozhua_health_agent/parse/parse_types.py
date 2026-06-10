"""WP1 输入解析中间类型定义。

定义步骤 ① 产出的 ``FactSheet`` 及其分组子结构，以及 ``ParseResult`` 等管道边界类型。
对应 ``pipeline-design.md`` §3.2 与架构 L3-01 FactSetExtractor 子集。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.schemas import (
    ActivityLevelLiteral,
    AgeRiskLiteral,
    AppetiteLiteral,
    ConfidenceLiteral,
    DataQualityLiteral,
    DiarrheaLiteral,
    DrinkingLiteral,
    EnergyLiteral,
    HealthSignal,
    MissingDataItemLiteral,
    RecentExerciseLiteral,
    SceneLiteral,
    SexLiteral,
    SleepQualityLiteral,
    SpeciesLiteral,
    UpstreamRiskLevelLiteral,
    VomitingLiteral,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_NORMALIZATION_PROFILE_ID: str = "xiaozhua.parse.normalization.v1"
"""默认归一化配置版本标识。"""

FACT_INDEX_PREFIX: str = "fact"
"""事实路径索引前缀，与架构 L3 ``factIndex`` 约定对齐。"""


# ---------------------------------------------------------------------------
# FactSheet 分组子结构
# ---------------------------------------------------------------------------


class IdentityFacts(BaseModel):
    """标识类客观事实（宠物与请求标识）。"""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(description="稳定 case / 请求标识。")
    pet_id: str = Field(description="宠物唯一标识。")
    pet_name: str = Field(description="宠物名称。")
    species: SpeciesLiteral = Field(description="物种：狗、猫或未知。")
    age_months: float | None = Field(
        default=None,
        description="月龄；未知时保持 null，不补默认值。",
    )
    breed: str | None = Field(
        default=None,
        description="品种；未知时保持 null。",
    )


class ProfileFacts(BaseModel):
    """档案类客观事实（慢病、用药、过敏等）。"""

    model_config = ConfigDict(extra="forbid")

    sex: SexLiteral | None = Field(default=None, description="性别。")
    weight_kg: float | None = Field(
        default=None,
        description="体重（千克）；未知时保持 null。",
    )
    neutered: bool | None = Field(default=None, description="是否绝育。")
    chronic_conditions: list[str] = Field(
        default_factory=list,
        description="慢性病史列表（归一化后去重、稳定排序）。",
    )
    medications: list[str] = Field(
        default_factory=list,
        description="当前用药列表。",
    )
    allergies: list[str] = Field(
        default_factory=list,
        description="过敏史列表。",
    )


class DeviceFacts(BaseModel):
    """设备与数据质量客观事实。"""

    model_config = ConfigDict(extra="forbid")

    device_online: bool = Field(description="设备是否在线。")
    battery_level: float | None = Field(
        default=None,
        description="电量百分比；未知时保持 null。",
    )
    data_quality: DataQualityLiteral = Field(
        description="数据质量：good / partial / stale / missing。",
    )
    last_seen_at: datetime | None = Field(
        default=None,
        description="设备最近上报时间。",
    )
    collar_id: str | None = Field(
        default=None,
        description="项圈设备 ID。",
    )
    warning_text: str | None = Field(
        default=None,
        description="设备侧告警文案。",
    )


class VitalsFacts(BaseModel):
    """生命体征客观事实快照。"""

    model_config = ConfigDict(extra="forbid")

    temperature_c: float | None = Field(
        default=None,
        description="体温（摄氏度）；缺失时保持 null。",
    )
    heart_rate_bpm: float | None = Field(
        default=None,
        description="心率（次/分）。",
    )
    respiratory_rate_bpm: float | None = Field(
        default=None,
        description="呼吸率（次/分）。",
    )
    hrv_ms: float | None = Field(
        default=None,
        description="心率变异性（毫秒）。",
    )
    steps_today: float | None = Field(
        default=None,
        description="当日步数。",
    )
    activity_level: ActivityLevelLiteral = Field(
        description="活动强度档位。",
    )
    sleep_quality: SleepQualityLiteral = Field(
        description="睡眠质量档位。",
    )
    updated_at: datetime | None = Field(
        default=None,
        description="体征数据更新时间。",
    )


class UpstreamFacts(BaseModel):
    """上游 healthEvidence 客观声称（T2，供 ② 条件信任）。"""

    model_config = ConfigDict(extra="forbid")

    risk_level: UpstreamRiskLevelLiteral = Field(
        description="上游综合风险等级。",
    )
    risk_label: str = Field(description="上游风险标签文案。")
    display_claim: str = Field(description="上游展示结论摘要。")
    recommendation_text: str = Field(description="上游建议文案。")
    confidence: ConfidenceLiteral = Field(description="上游综合置信度。")
    signals: list[HealthSignal] = Field(
        default_factory=list,
        description="上游结构化信号列表（原样保留，不做医学修正）。",
    )


class UserReportFacts(BaseModel):
    """用户自述客观事实（结构化字段 + 原文）。"""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(description="用户自由文本描述（归一化后 trim）。")
    duration: str | None = Field(
        default=None,
        description="症状持续时间描述。",
    )
    symptoms: list[str] = Field(
        default_factory=list,
        description="症状关键词列表。",
    )
    appetite: AppetiteLiteral = Field(description="食欲状态。")
    drinking: DrinkingLiteral = Field(description="饮水状态。")
    energy: EnergyLiteral = Field(description="精力状态。")
    vomiting: VomitingLiteral = Field(description="呕吐情况。")
    diarrhea: DiarrheaLiteral = Field(description="腹泻情况。")
    coughing: bool | None = Field(default=None, description="是否咳嗽。")
    breathing_difficulty: bool | None = Field(
        default=None,
        description="是否呼吸困难。",
    )
    pain: bool | None = Field(default=None, description="是否疼痛。")
    limping: bool | None = Field(default=None, description="是否跛行。")
    seizure: bool | None = Field(default=None, description="是否抽搐。")
    trauma: bool | None = Field(default=None, description="是否外伤。")


class ContextFacts(BaseModel):
    """环境与情境修饰客观事实。"""

    model_config = ConfigDict(extra="forbid")

    environment_temp_c: float | None = Field(
        default=None,
        description="环境温度（摄氏度）。",
    )
    recent_exercise: RecentExerciseLiteral = Field(
        description="近期运动强度。",
    )
    recent_vaccination: bool | None = Field(
        default=None,
        description="是否近期接种疫苗。",
    )
    recent_meal: bool | None = Field(
        default=None,
        description="是否近期进食。",
    )
    age_risk: AgeRiskLiteral = Field(description="年龄风险档。")
    notes: list[str] = Field(
        default_factory=list,
        description="情境备注列表。",
    )


class FactSheet(BaseModel):
    """步骤 ① 产出的客观事实清单，供 ②③④ 引用。

    仅包含当次 input 可核对事实，**不含** DerivedFacts（属 WP2）与医学裁决。
    """

    model_config = ConfigDict(extra="forbid")

    scene: SceneLiteral = Field(description="分诊场景，V1 固定 health_triage。")
    timestamp: datetime = Field(description="App 发起分诊请求的时间。")
    timestamp_epoch_ms: int | None = Field(
        default=None,
        description="请求时间的 Unix 毫秒时间戳（管道内部元数据，不回流 App）。",
    )
    identity: IdentityFacts = Field(description="标识类事实。")
    profile: ProfileFacts = Field(description="档案类事实。")
    device: DeviceFacts = Field(description="设备与数据质量事实。")
    vitals: VitalsFacts = Field(description="生命体征事实。")
    upstream: UpstreamFacts = Field(description="上游 healthEvidence 声称。")
    user_report: UserReportFacts = Field(description="用户自述事实。")
    context: ContextFacts = Field(description="情境修饰事实。")
    missing_data: list[MissingDataItemLiteral] = Field(
        default_factory=list,
        description="App 声明的缺失数据项（归一化后去重、稳定排序）。",
    )
    fact_index: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "稳定路径 → 原始值索引，供 evidence 回溯与 L5 真实性审查；"
            "键形如 ``fact.vitals.temperatureC``。"
        ),
    )


# ---------------------------------------------------------------------------
# 归一化配置
# ---------------------------------------------------------------------------


class NormalizationProfile(BaseModel):
    """输入归一化配置（L1-02 InputNormalizer）。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_id: str = Field(
        default=DEFAULT_NORMALIZATION_PROFILE_ID,
        description="归一化配置版本标识。",
    )
    trim_strings: bool = Field(
        default=True,
        description="是否对字符串字段执行首尾空白裁剪。",
    )
    dedupe_string_arrays: bool = Field(
        default=True,
        description="是否对字符串数组去重。",
    )
    sort_string_arrays: bool = Field(
        default=True,
        description="是否对字符串数组稳定排序（便于 diff 与单测）。",
    )
    attach_timestamp_epoch_ms: bool = Field(
        default=True,
        description="是否在 FactSheet 附加 ``timestamp_epoch_ms``。",
    )


DEFAULT_NORMALIZATION_PROFILE: NormalizationProfile = NormalizationProfile()
"""默认归一化配置单例。"""
