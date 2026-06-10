"""Agent 单次分诊输出顶层模型。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.schemas.common_types import ConfidenceLiteral
from xiaozhua_health_agent.schemas.input_types import SceneLiteral
from xiaozhua_health_agent.schemas.output_types import OutputRiskLevelLiteral


class ActionItem(BaseModel):
    """App 可点击的主/次行动项。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    label: str = Field(
        min_length=1,
        description="展示给用户的行动按钮文案，不能为空。",
    )
    route: str | None = Field(
        default=None,
        description="App 内跳转路由或深链；无具体页面时为 null。",
    )


class AgentOutput(BaseModel):
    """Agent 完整结构化输出，与 ``output_schema.v1`` 对齐（full 模式校验真源）。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    risk_level: OutputRiskLevelLiteral = Field(
        alias="riskLevel",
        description="最终风险等级，供 App 卡片与配色使用。",
    )
    scene: SceneLiteral = Field(
        description="分诊场景，V1 固定为 health_triage。",
    )
    title: str = Field(
        min_length=1,
        description="卡片短标题，概括当前风险与主题。",
    )
    summary: str = Field(
        min_length=1,
        description="面向用户的风险解释摘要，不得编造未提供事实。",
    )
    evidence: list[str] = Field(
        description="可核对证据列表，每条应为简短事实句。",
    )
    recommendation: str = Field(
        min_length=1,
        description="建议的下一步行动（观察、休息、联系兽医等）。",
    )
    when_to_see_vet: str = Field(
        alias="whenToSeeVet",
        min_length=1,
        description="何时必须就医的明确升级条件。",
    )
    missing_data: list[str] = Field(
        alias="missingData",
        description="用户可读的缺失数据说明列表。",
    )
    confidence: ConfidenceLiteral = Field(
        description="Agent 对本次分诊结论的置信度档位。",
    )
    safety_notice: str = Field(
        alias="safetyNotice",
        min_length=1,
        description="医疗安全边界声明，强调非诊断、不替代兽医。",
    )
    primary_action: ActionItem = Field(
        alias="primaryAction",
        description="首要行动入口，与 riskLevel 匹配。",
    )
    secondary_action: ActionItem | None = Field(
        default=None,
        alias="secondaryAction",
        description="可选次要行动，如检查设备或记录症状。",
    )


class RiskOnlyOutput(BaseModel):
    """WP3 risk-only 阶段的极简输出（minimal 模式校验真源）。

    仅要求 ``riskLevel`` 必填；``scene`` 与 ``confidence`` 可选。
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    risk_level: OutputRiskLevelLiteral = Field(
        alias="riskLevel",
        description="最终风险等级（minimal 模式唯一硬性必填项）。",
    )
    scene: SceneLiteral | None = Field(
        default=None,
        description="分诊场景；省略时由下游默认视为 health_triage。",
    )
    confidence: ConfidenceLiteral | None = Field(
        default=None,
        description="置信度档位；risk-only 评测可选比对。",
    )
