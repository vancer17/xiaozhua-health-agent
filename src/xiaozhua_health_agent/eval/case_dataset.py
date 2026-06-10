"""健康分诊 mock case 数据集加载。

对应制品：``docs/cases/health_triage_cases.v1.json``。
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from xiaozhua_health_agent.paths import default_cases_path
from xiaozhua_health_agent.schemas.agent_input import AgentInput
from xiaozhua_health_agent.schemas.common_types import ConfidenceLiteral
from xiaozhua_health_agent.schemas.output_types import OutputRiskLevelLiteral

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

DEFAULT_DATASET_VERSION: str = "xiaozhua.health_triage_cases.v1"
"""V1 mock case 数据集版本标识。"""

EXPECTED_CASE_COUNT: int = 20
"""V1 固定 case 数量，用于加载时完整性检查。"""


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class CaseDatasetError(Exception):
    """Case 数据集加载失败。

    用于区分「文件/JSON 读取错误」与 Pydantic 字段校验错误。
    """


# ---------------------------------------------------------------------------
# Case 验收约束与数据集模型
# ---------------------------------------------------------------------------


class CaseExpected(BaseModel):
    """单条 case 的验收约束（测试专用，不属于 Agent output_schema）。"""

    model_config = ConfigDict(extra="forbid")

    risk_level: OutputRiskLevelLiteral = Field(
        alias="riskLevel",
        description="期望 Agent 输出的风险等级。",
    )
    confidence: ConfidenceLiteral = Field(description="期望置信度档位。")
    must_mention: list[str] = Field(
        alias="mustMention",
        default_factory=list,
        description="输出文案中应出现的关键词（语义评测用）。",
    )
    must_not_mention: list[str] = Field(
        alias="mustNotMention",
        default_factory=list,
        description="输出文案中不得出现的关键词。",
    )
    safety_notice_required: bool = Field(
        alias="safetyNoticeRequired",
        description="是否必须输出非空 safetyNotice。",
    )


class CaseRecord(BaseModel):
    """单条 mock case：入参快照 + 验收约束。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    case_id: str = Field(alias="caseId", description="case 唯一标识。")
    name: str = Field(description="case 中文名称，便于批跑报告阅读。")
    input: AgentInput = Field(description="App/mock adapter 提供的 Agent 入参。")
    expected: CaseExpected = Field(description="该 case 的验收约束。")

    @model_validator(mode="after")
    def _check_case_id_matches_input(self) -> Self:
        """校验 ``caseId`` 与 ``input.caseId`` 一致。"""
        if self.case_id != self.input.case_id:
            msg = (
                f"caseId 不一致：顶层为 {self.case_id!r}，"
                f"input 为 {self.input.case_id!r}"
            )
            raise ValueError(msg)
        return self


class HealthTriageDataset(BaseModel):
    """``health_triage_cases.v1.json`` 根对象。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    dataset_version: str = Field(
        alias="datasetVersion",
        description="数据集版本标识。",
    )
    created_at: date = Field(
        alias="createdAt",
        description="数据集创建日期。",
    )
    description: str = Field(description="数据集说明。")
    cases: list[CaseRecord] = Field(description="全部 mock case 列表。")

    @model_validator(mode="after")
    def _check_dataset_invariants(self) -> Self:
        """校验 V1 数据集级不变量。"""
        if self.dataset_version != DEFAULT_DATASET_VERSION:
            msg = (
                f"不支持的 datasetVersion：{self.dataset_version!r}，"
                f"期望 {DEFAULT_DATASET_VERSION!r}"
            )
            raise ValueError(msg)

        if len(self.cases) != EXPECTED_CASE_COUNT:
            msg = f"case 数量应为 {EXPECTED_CASE_COUNT}，实际为 {len(self.cases)}"
            raise ValueError(msg)

        case_ids = [case.case_id for case in self.cases]
        duplicates = {cid for cid in case_ids if case_ids.count(cid) > 1}
        if duplicates:
            msg = f"存在重复 caseId：{sorted(duplicates)!r}"
            raise ValueError(msg)

        return self

    def case_by_id(self, case_id: str) -> CaseRecord:
        """按 caseId 查找单条 case。"""
        for case in self.cases:
            if case.case_id == case_id:
                return case
        raise KeyError(f"未找到 caseId={case_id!r}")

    def iter_inputs(self) -> list[AgentInput]:
        """返回全部 case 的 Agent 入参列表（保持文件顺序）。"""
        return [case.input for case in self.cases]


# ---------------------------------------------------------------------------
# 加载函数
# ---------------------------------------------------------------------------


def load_health_triage_dataset_from_json(json_text: str) -> HealthTriageDataset:
    """从 JSON 字符串加载并校验数据集。"""
    try:
        payload: Any = json.loads(json_text)
    except json.JSONDecodeError as exc:
        msg = (
            f"case JSON 解析失败：{exc.msg}（位置 line={exc.lineno}, col={exc.colno}）"
        )
        raise CaseDatasetError(msg) from exc

    return HealthTriageDataset.model_validate(payload)


def load_health_triage_dataset(
    path: Path | str | None = None,
    *,
    encoding: str = "utf-8",
) -> HealthTriageDataset:
    """从文件加载并校验 ``health_triage_cases.v1.json``。"""
    resolved = Path(path) if path is not None else default_cases_path()

    if not resolved.is_file():
        msg = f"case 文件不存在：{resolved}"
        raise CaseDatasetError(msg)

    try:
        json_text = resolved.read_text(encoding=encoding)
    except OSError as exc:
        msg = f"读取 case 文件失败：{resolved}（{exc}）"
        raise CaseDatasetError(msg) from exc

    return load_health_triage_dataset_from_json(json_text)
