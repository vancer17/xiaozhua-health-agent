"""WP1 输入解析门面（L1-07 HealthTriageAdapterFacade 子集）。

串联契约校验（L1-01）、归一化（L1-02）与事实提取（L3-01 子集），产出 ``FactSheet``。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.eval import (
    INPUT_SCHEMA_VERSION,
    ValidationResult,
    Violation,
    validate_input,
)
from xiaozhua_health_agent.schemas import AgentInput

from xiaozhua_health_agent.parse.fact_extractor import extract_fact_sheet
from xiaozhua_health_agent.parse.normalizer import normalize_agent_input
from xiaozhua_health_agent.parse.parse_types import (
    DEFAULT_NORMALIZATION_PROFILE,
    FactSheet,
    NormalizationProfile,
)


class ParseResult(BaseModel):
    """单次输入解析结果（步骤 ① 出站边界）。"""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    passed: bool = Field(description="是否完成契约校验并成功构建 FactSheet。")
    schema_version: str = Field(
        default=INPUT_SCHEMA_VERSION,
        description="对照的 input schema 版本标识。",
    )
    violations: list[Violation] = Field(
        default_factory=list,
        description="契约校验失败时的违规项；通过时为空。",
    )
    schema_validation: ValidationResult[AgentInput] | None = Field(
        default=None,
        description="完整的契约校验结果（含 ``parsed`` 引用）。",
    )
    agent_input: AgentInput | None = Field(
        default=None,
        description="归一化后的强类型入参；仅 ``passed=True`` 时有值。",
    )
    fact_sheet: FactSheet | None = Field(
        default=None,
        description="客观事实清单；仅 ``passed=True`` 时有值。",
    )


class CaseParseRecord(BaseModel):
    """单条 case 的解析记录（批跑辅助）。"""

    model_config = ConfigDict(arbitrary_types_allowed=True, populate_by_name=True)

    case_id: str = Field(alias="caseId", description="case 唯一标识。")
    result: ParseResult = Field(description="该 case 的解析结果。")


def _build_failed_parse_result(
    schema_validation: ValidationResult[AgentInput],
) -> ParseResult:
    """由失败的契约校验结果构造 ``ParseResult``。

    :param schema_validation: 未通过的 ``validate_input`` 结果。
    :type schema_validation: ValidationResult[AgentInput]
    :returns: ``passed=False`` 的解析结果。
    :rtype: ParseResult
    """
    return ParseResult(
        passed=False,
        schema_version=schema_validation.schema_version,
        violations=list(schema_validation.violations),
        schema_validation=schema_validation,
        agent_input=None,
        fact_sheet=None,
    )


def _build_success_parse_result(
    *,
    schema_validation: ValidationResult[AgentInput],
    agent_input: AgentInput,
    fact_sheet: FactSheet,
) -> ParseResult:
    """由成功的解析链路构造 ``ParseResult``。

    :param schema_validation: 通过的契约校验结果。
    :type schema_validation: ValidationResult[AgentInput]
    :param agent_input: 归一化后的入参。
    :type agent_input: AgentInput
    :param fact_sheet: 提取的事实清单。
    :type fact_sheet: FactSheet
    :returns: ``passed=True`` 的解析结果。
    :rtype: ParseResult
    """
    return ParseResult(
        passed=True,
        schema_version=schema_validation.schema_version,
        violations=[],
        schema_validation=schema_validation,
        agent_input=agent_input,
        fact_sheet=fact_sheet,
    )


def parse_agent_input(
    agent_input: AgentInput,
    *,
    profile: NormalizationProfile = DEFAULT_NORMALIZATION_PROFILE,
    skip_schema_validation: bool = False,
) -> ParseResult:
    """对已构造的 ``AgentInput`` 执行归一化与事实提取。

    适用于 case 数据集等已强类型化的入参路径。

    :param agent_input: 待解析的入参实例。
    :type agent_input: AgentInput
    :param profile: 归一化配置。
    :type profile: NormalizationProfile
    :param skip_schema_validation: 为 ``True`` 时跳过 ``validate_input``（仅用于已通过校验的对象）。
    :type skip_schema_validation: bool
    :returns: 解析结果。
    :rtype: ParseResult
    """
    if skip_schema_validation:
        schema_validation = ValidationResult[AgentInput](
            passed=True,
            schema_kind="input",
            schema_version=INPUT_SCHEMA_VERSION,
            mode=None,
            violations=[],
            parsed=agent_input,
        )
    else:
        schema_validation = validate_input(agent_input)
        if not schema_validation.passed or schema_validation.parsed is None:
            return _build_failed_parse_result(schema_validation)

    normalized = normalize_agent_input(agent_input, profile=profile)
    fact_sheet = extract_fact_sheet(normalized, profile=profile)

    return _build_success_parse_result(
        schema_validation=schema_validation,
        agent_input=normalized,
        fact_sheet=fact_sheet,
    )


def parse_input(
    data: AgentInput | Mapping[str, Any],
    *,
    profile: NormalizationProfile = DEFAULT_NORMALIZATION_PROFILE,
) -> ParseResult:
    """解析原始 JSON 或强类型入参，产出 ``FactSheet``。

    管道步骤：

    1. ``validate_input`` — L1-01 契约校验
    2. ``normalize_agent_input`` — L1-02 表示归一化
    3. ``extract_fact_sheet`` — L3-01 事实提取

    :param data: App / case 原始 JSON 字典，或已构造的 ``AgentInput``。
    :type data: AgentInput | collections.abc.Mapping[str, Any]
    :param profile: 归一化配置。
    :type profile: NormalizationProfile
    :returns: 解析结果；失败时不进入后续医学步骤。
    :rtype: ParseResult
    """
    if isinstance(data, AgentInput):
        return parse_agent_input(data, profile=profile, skip_schema_validation=False)

    schema_validation = validate_input(data)
    if not schema_validation.passed or schema_validation.parsed is None:
        return _build_failed_parse_result(schema_validation)

    normalized = normalize_agent_input(schema_validation.parsed, profile=profile)
    fact_sheet = extract_fact_sheet(normalized, profile=profile)

    return _build_success_parse_result(
        schema_validation=schema_validation,
        agent_input=normalized,
        fact_sheet=fact_sheet,
    )


def parse_all_case_inputs(
    inputs: Sequence[AgentInput],
    *,
    profile: NormalizationProfile = DEFAULT_NORMALIZATION_PROFILE,
) -> list[CaseParseRecord]:
    """批量解析多条已加载的 case 入参。

    :param inputs: case 入参序列（通常来自 ``HealthTriageDataset``）。
    :type inputs: collections.abc.Sequence[AgentInput]
    :param profile: 归一化配置。
    :type profile: NormalizationProfile
    :returns: 每条 case 的解析记录列表，顺序与输入一致。
    :rtype: list[CaseParseRecord]
    """
    records: list[CaseParseRecord] = []
    for agent_input in inputs:
        result = parse_agent_input(
            agent_input,
            profile=profile,
            skip_schema_validation=True,
        )
        records.append(
            CaseParseRecord(caseId=agent_input.case_id, result=result),
        )
    return records


def assert_all_parse_passed(records: Sequence[CaseParseRecord]) -> None:
    """断言批解析全部通过；失败时抛出 ``AssertionError`` 并附带 caseId。

    :param records: ``parse_all_case_inputs`` 产出的记录列表。
    :type records: collections.abc.Sequence[CaseParseRecord]
    :raises AssertionError: 任一 case 解析未通过。
    :rtype: None
    """
    failures: list[str] = []
    for record in records:
        if record.result.passed:
            continue
        violation_summary = "; ".join(
            f"{v.path}: {v.message}" for v in record.result.violations[:3]
        )
        failures.append(f"{record.case_id} — {violation_summary or '未知错误'}")

    if failures:
        joined = "\n".join(failures)
        raise AssertionError(f"输入解析失败 {len(failures)} 条：\n{joined}")
