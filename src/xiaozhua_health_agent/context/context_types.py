"""WP2 上下文构建中间类型定义。

定义 ``DerivedFacts``、``EvalContext`` 及 when 求值相关类型别名。
对应 ``kb-rule-derived-facts-spec.md`` 与 ``triage-core-spec.md`` §五。
"""

from __future__ import annotations

from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.parse import FactSheet
from xiaozhua_health_agent.schemas import UpstreamRiskLevelLiteral

# ---------------------------------------------------------------------------
# 风险等级类型别名
# ---------------------------------------------------------------------------

TriageRiskLiteral: TypeAlias = Literal["normal", "watch", "warning", "emergency"]
"""分诊管道内可比较的离散风险档位（不含 upstream ``unknown``）。"""

MaxSignalRiskLiteral: TypeAlias = TriageRiskLiteral | None
"""signals 最高风险；无信号时为 ``None``（不参与 fusion 抬高）。"""

# ---------------------------------------------------------------------------
# when 条件块（JSON 结构化条件，运行时以 dict 承载）
# ---------------------------------------------------------------------------

WhenBlock: TypeAlias = dict[str, Any]
"""结构化 ``when`` 条件块；形态见 ``triage-core-spec.md`` §5.2。"""

FieldComparisonOperator: TypeAlias = Literal[
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
]
"""``field`` 原子支持的关系运算符。"""

# ---------------------------------------------------------------------------
# DerivedFacts
# ---------------------------------------------------------------------------


class DerivedFacts(BaseModel):
    """步骤 ② 入口一次性预计算的派生事实。

    仅基于当次 ``FactSheet`` 可核对字段推导，不写入决策表 JSON，
    不暴露给 App，供 ``eval_when`` 与后续 Triage Core 只读消费。
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    is_resting: bool = Field(
        description=(
            "当前处于安静/非运动情境："
            "``activityLevel ∈ {resting, unknown}`` 且 "
            "``recentExercise ∈ {none, unknown}``。"
        ),
    )
    is_active: bool = Field(
        description=(
            "当前处于较高活动水平："
            "``activityLevel ∈ {active, intense}`` 或 "
            "``recentExercise ∈ {moderate, intense}``。"
        ),
    )
    has_exercise_context: bool = Field(
        description=(
            "宽口径运动情境：``is_active`` 或 notes/signal.reason 含运动关键词。"
        ),
    )
    vitals_core_missing: bool = Field(
        description="核心体征三项（体温、心率、呼吸率）均为 null。",
    )
    max_signal_risk: MaxSignalRiskLiteral = Field(
        description="上游 signals 最高风险档；无信号时为 ``None``。",
    )
    upstream_risk: UpstreamRiskLevelLiteral = Field(
        description="``healthEvidence.riskLevel`` 原值（含 ``unknown``）。",
    )
    user_says_normal: bool = Field(
        description="用户主观描述正常且无结构化症状/精力异常。",
    )
    device_shows_resting_fever: bool = Field(
        description="安静情境下设备测得物种相对偏高体温。",
    )
    has_chronic_heart: bool = Field(
        description="存在心脏相关慢病史标签。",
    )
    is_senior: bool = Field(
        description="老年宠物（``ageRisk=senior`` 或月龄超物种阈值）。",
    )
    is_puppy_kitten: bool = Field(
        description="幼宠（``ageRisk=puppy_kitten`` 或月龄 ≤ 配置阈值）。",
    )
    is_brachycephalic: bool = Field(
        description="短鼻/扁脸体质（慢病标签或品种配置列表）。",
    )
    open_mouth_breathing_reported: bool = Field(
        description="用户报告张口呼吸（symptoms 或 text 命中）。",
    )
    severe_resting_resp: bool = Field(
        description="安静态呼吸率极高（≥ 配置阈值，默认 60 bpm）。",
    )
    has_resting_tachycardia: bool = Field(
        description="安静非运动窗口内心率维度客观异常。",
    )
    has_resting_tachypnea: bool = Field(
        description="安静非运动窗口内呼吸维度客观异常。",
    )
    max_signal_risk_at_most_normal: bool = Field(
        description="上游 signals 最高风险不高于 normal（无信号视为满足）。",
    )
    has_stress_context: bool = Field(
        description="存在环境变化或用户报告紧张等压力上下文。",
    )
    has_slow_recovery_context: bool = Field(
        description="用户报告恢复慢或睡眠差（症状或自由文本）。",
    )
    has_chronic_conditions: bool = Field(
        description="宠物档案中存在至少一条慢性病史。",
    )


# ---------------------------------------------------------------------------
# EvalContext
# ---------------------------------------------------------------------------


class EvalContext(BaseModel):
    """``eval_when`` 求值环境：FactSheet + DerivedFacts 只读快照。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fact_sheet: FactSheet = Field(description="步骤 ① 产出的客观事实清单。")
    derived: DerivedFacts = Field(description="步骤 ② 入口预计算的派生事实。")


# ---------------------------------------------------------------------------
# 求值结果（调试 / 测试）
# ---------------------------------------------------------------------------


class WhenEvalTraceEntry(BaseModel):
    """单条 when 子条件求值轨迹。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(description="条件块在树中的路径（如 ``all[0]``）。")
    block_type: str = Field(description="条件块类型（all / fact / field 等）。")
    result: bool = Field(description="该节点求值结果。")
    detail: str | None = Field(
        default=None,
        description="可选说明（如字段实际值）。",
    )


class WhenEvalResult(BaseModel):
    """``eval_when`` 带轨迹的求值结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    matched: bool = Field(description="顶层条件是否满足。")
    trace: tuple[WhenEvalTraceEntry, ...] = Field(
        default_factory=tuple,
        description="按深度优先顺序记录的子条件轨迹。",
    )
