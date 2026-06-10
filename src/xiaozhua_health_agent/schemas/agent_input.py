"""Agent 单次分诊入参顶层模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.schemas.input_types import (
    Context,
    DeviceState,
    HealthEvidence,
    MissingDataItemLiteral,
    PetProfile,
    SceneLiteral,
    UserReport,
    Vitals,
)


class AgentInput(BaseModel):
    """Agent 单次分诊入参，与 ``input_schema.v1`` 对齐。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    case_id: str = Field(alias="caseId", description="本次请求的稳定 case 标识。")
    scene: SceneLiteral = Field(description="分诊场景，V1 固定为 health_triage。")
    timestamp: datetime = Field(description="App 发起分诊请求的时间。")
    pet: PetProfile = Field(description="宠物档案。")
    device: DeviceState = Field(description="设备与数据质量。")
    vitals: Vitals = Field(description="生命体征快照。")
    health_evidence: HealthEvidence = Field(
        alias="healthEvidence",
        description="上游聚合健康证据。",
    )
    user_report: UserReport = Field(
        alias="userReport",
        description="用户自述与结构化症状。",
    )
    context: Context = Field(description="环境与情境信息。")
    missing_data: list[MissingDataItemLiteral] = Field(
        alias="missingData",
        default_factory=list,
        description="App 声明的缺失数据项列表。",
    )
