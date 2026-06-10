"""Agent 入参 / 出参契约模型 — 公开 API 门面。

与 ``docs/schema/xiaozhua_health_agent_{input,output}_schema.v1.json`` 对齐；
可执行真源为本包 Pydantic 模型（非独立 jsonschema 运行时）。

包外代码应只从本模块导入，避免直接依赖 ``schemas`` 子模块实现文件：

.. code-block:: python

    from xiaozhua_health_agent.schemas import (
        AgentInput,
        AgentOutput,
        PetProfile,
        OutputRiskLevelLiteral,
    )

子模块之间（如 ``agent_input`` → ``input_types``）仍使用子模块直引，
勿从本 ``__init__`` 回引，以免循环导入。

结构校验请使用 ``xiaozhua_health_agent.eval``（``validate_input`` / ``validate_output``），
本包不负责校验逻辑。
"""

from __future__ import annotations

from xiaozhua_health_agent.schemas.agent_input import AgentInput
from xiaozhua_health_agent.schemas.agent_output import (
    ActionItem,
    AgentOutput,
    RiskOnlyOutput,
)
from xiaozhua_health_agent.schemas.common_types import (
    Confidence,
    ConfidenceLiteral,
)
from xiaozhua_health_agent.schemas.input_types import (
    ActivityLevel,
    ActivityLevelLiteral,
    AgeRisk,
    AgeRiskLiteral,
    Appetite,
    AppetiteLiteral,
    Context,
    DataQuality,
    DataQualityLiteral,
    DeviceState,
    Diarrhea,
    DiarrheaLiteral,
    Drinking,
    DrinkingLiteral,
    Energy,
    EnergyLiteral,
    HealthEvidence,
    HealthSignal,
    MissingDataItem,
    MissingDataItemLiteral,
    PetProfile,
    RecentExercise,
    RecentExerciseLiteral,
    Scene,
    SceneLiteral,
    Sex,
    SexLiteral,
    SignalCategory,
    SignalCategoryLiteral,
    SignalId,
    SignalIdLiteral,
    SignalRiskLevel,
    SignalRiskLevelLiteral,
    SleepQuality,
    SleepQualityLiteral,
    Species,
    SpeciesLiteral,
    UpstreamRiskLevel,
    UpstreamRiskLevelLiteral,
    UserReport,
    Vitals,
    Vomiting,
    VomitingLiteral,
)
from xiaozhua_health_agent.schemas.output_types import (
    ActionRouteKind,
    ActionRouteKindLiteral,
    OutputRiskLevel,
    OutputRiskLevelLiteral,
)

__all__ = [
    # --- 顶层契约（App / 管道边界）---
    "AgentInput",
    "AgentOutput",
    "RiskOnlyOutput",
    "ActionItem",
    # --- 共用 ---
    "Confidence",
    "ConfidenceLiteral",
    # --- 输出枚举 ---
    "OutputRiskLevel",
    "OutputRiskLevelLiteral",
    "ActionRouteKind",
    "ActionRouteKindLiteral",
    # --- 入参枚举（StrEnum，便于常量引用与文档）---
    "Scene",
    "Species",
    "Sex",
    "DataQuality",
    "ActivityLevel",
    "SleepQuality",
    "UpstreamRiskLevel",
    "SignalRiskLevel",
    "SignalId",
    "SignalCategory",
    "Appetite",
    "Drinking",
    "Energy",
    "Vomiting",
    "Diarrhea",
    "RecentExercise",
    "AgeRisk",
    "MissingDataItem",
    # --- 入参 Literal（字段注解与校验真源）---
    "SceneLiteral",
    "SpeciesLiteral",
    "SexLiteral",
    "DataQualityLiteral",
    "ActivityLevelLiteral",
    "SleepQualityLiteral",
    "UpstreamRiskLevelLiteral",
    "SignalRiskLevelLiteral",
    "SignalIdLiteral",
    "SignalCategoryLiteral",
    "AppetiteLiteral",
    "DrinkingLiteral",
    "EnergyLiteral",
    "VomitingLiteral",
    "DiarrheaLiteral",
    "RecentExerciseLiteral",
    "AgeRiskLiteral",
    "MissingDataItemLiteral",
    # --- 入参子模型 ---
    "PetProfile",
    "DeviceState",
    "Vitals",
    "HealthSignal",
    "HealthEvidence",
    "UserReport",
    "Context",
]
