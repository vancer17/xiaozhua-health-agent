"""Risk-only 评测专用结果类型与组装辅助函数（WP0）。

本模块定义 ``RiskEvalResult``、``RiskEvalReport`` 等 DTO，供 ``risk_evaluator``
（待实现）与批跑报告消费。评测语义（expected / actual）主要在
``RiskDimensionResult`` 表达；``Violation`` 仅承载可聚合的违规行。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from xiaozhua_health_agent.eval.case_dataset import DEFAULT_DATASET_VERSION
from xiaozhua_health_agent.eval.validation_result import (
    ValidationResult,
    Violation,
    ViolationCode,
    ViolationCodeLiteral,
    ViolationSeverityLiteral,
)
from xiaozhua_health_agent.schemas.agent_output import AgentOutput, RiskOnlyOutput
from xiaozhua_health_agent.schemas.common_types import ConfidenceLiteral
from xiaozhua_health_agent.schemas.output_types import OutputRiskLevelLiteral

# ---------------------------------------------------------------------------
# 枚举与 Literal 别名
# ---------------------------------------------------------------------------


class ConfidenceCheckMode(StrEnum):
    """confidence 比对策略（risk-only 评测可选维度）。"""

    OFF = "off"
    EXACT = "exact"
    TIER = "tier"


ConfidenceCheckModeLiteral = Literal["off", "exact", "tier"]


class RiskEvalDimension(StrEnum):
    """Risk-only 评测中的单维度标识。"""

    RISK = "risk"
    CONFIDENCE = "confidence"


RiskEvalDimensionLiteral = Literal["risk", "confidence"]


class RiskEvalRunMode(StrEnum):
    """批跑报告运行模式标识。"""

    RISK_ONLY = "risk-only"


RiskEvalRunModeLiteral = Literal["risk-only"]


class ConfidenceHardGateMode(StrEnum):
    """confidence 不匹配是否拉低 ``RiskEvalResult.passed``。"""

    SOFT = "soft"
    HARD = "hard"


ConfidenceHardGateModeLiteral = Literal["soft", "hard"]


# minimal 出站结构校验通过后的解析类型联合
RiskEvalParsedOutput = RiskOnlyOutput | AgentOutput
"""risk-only 评测中 ``schema_check.parsed`` 允许的强类型联合。"""

# 与早期设计文档命名对齐的别名
SchemaCheckParsed = RiskEvalParsedOutput
RiskDimensionKind = RiskEvalDimension
RiskDimensionKindLiteral = RiskEvalDimensionLiteral

# ---------------------------------------------------------------------------
# 维度与单 case 结果
# ---------------------------------------------------------------------------


class RiskDimensionResult(BaseModel):
    """Risk-only 评测中单个比对维度（risk 或 confidence）的结果。

    :param dimension: 维度标识，``risk`` 或 ``confidence``。
    :param check_applied: 是否执行了本维度比对。
    :param passed: 比对结论；未执行时为 ``None``。
    :param expected: 来自 ``CaseExpected`` 的期望值。
    :param actual: 从 Agent 输出抽取的实际值。
    :param violations: 本维度产生的违规项列表。
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    dimension: RiskEvalDimensionLiteral = Field(
        description="比对维度：risk 为风险等级，confidence 为置信度档位。",
    )
    check_applied: bool = Field(
        description="是否执行了本维度比对；confidence 在 OFF 策略下为 false。",
    )
    passed: bool | None = Field(
        default=None,
        description="维度是否通过；未执行比对时为 null。",
    )
    expected: OutputRiskLevelLiteral | ConfidenceLiteral | None = Field(
        default=None,
        description="来自 ``CaseExpected`` 的期望值；risk 维为 riskLevel，confidence 维为 confidence。",
    )
    actual: OutputRiskLevelLiteral | ConfidenceLiteral | None = Field(
        default=None,
        description="从 Agent 实际输出提取的值；结构未通过或字段缺失时为 null。",
    )
    violations: list[Violation] = Field(
        default_factory=list,
        description="本维度产生的违规项；通过时为空列表。",
    )


class RiskEvalResult(BaseModel):
    """单条 case 的 risk-only 评测完整结果。

    ``passed`` 默认仅由 **minimal schema 通过** 与 **risk 维度一致** 决定；
    confidence 在 ``confidence_hard_gate=soft`` 时不拉低 ``passed``。

    :param passed: 最终硬门槛是否通过（WP3 里程碑 A 门禁）。
    :param hard_passed: 仅 schema + risk 是否通过。
    :param soft_passed: hard 通过且（未检查 confidence 或 confidence 通过）。
    :param schema_check: minimal output 结构校验结果。
    :param risk: riskLevel 维度比对结果。
    :param confidence: confidence 维度比对结果。
    :param violations: 扁平硬违规列表。
    :param warnings: 软门槛警告（默认 confidence 不匹配）。
    :param check_confidence_mode: confidence 比对策略。
    :param confidence_hard_gate: confidence 不匹配是否拉低 ``passed``。
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    passed: bool = Field(
        description=(
            "硬门槛是否通过：schema（minimal）通过且 riskLevel 与 expected 一致；"
            "confidence 是否影响本字段由 ``confidence_hard_gate`` 决定。"
        ),
    )
    hard_passed: bool = Field(
        description="仅 schema + risk 维度是否通过（不受 confidence 软门槛影响）。",
    )
    soft_passed: bool = Field(
        description="hard 通过且（未检查 confidence 或 confidence 维度通过）。",
    )
    schema_check: ValidationResult[RiskEvalParsedOutput] = Field(
        description="对照 ``RiskOnlyOutput`` 的 minimal 结构校验结果。",
    )
    risk: RiskDimensionResult = Field(
        description="riskLevel 维度比对结果。",
    )
    confidence: RiskDimensionResult = Field(
        description="confidence 维度比对结果。",
    )
    violations: list[Violation] = Field(
        default_factory=list,
        description="扁平汇总的全部违规项（schema → risk → confidence 顺序）。",
    )
    warnings: list[Violation] = Field(
        default_factory=list,
        description=(
            "软门槛警告（如 confidence 不匹配且 hard_gate=soft）；"
            "不计入 ``passed`` 失败条件。"
        ),
    )
    check_confidence_mode: ConfidenceCheckModeLiteral = Field(
        description="本次评测使用的 confidence 比对策略。",
    )
    confidence_hard_gate: ConfidenceHardGateModeLiteral = Field(
        default="soft",
        description="confidence 不匹配时是否将 ``passed`` 置为 false。",
    )

    @model_validator(mode="after")
    def _sync_aggregate_fields(self) -> RiskEvalResult:
        """校验扁平 ``violations`` / ``warnings`` 与分维度结果一致。

        :returns: 校验通过后的同一实例。
        :rtype: RiskEvalResult
        """
        expected_violations = flatten_risk_eval_violations(
            schema_check=self.schema_check,
            risk=self.risk,
            confidence=self.confidence,
            include_warnings_in_violations=self.confidence_hard_gate == "hard",
        )
        if self.violations != expected_violations:
            msg = (
                "RiskEvalResult.violations 与分维度结果不一致，"
                "请使用 build_risk_eval_result 构造。"
            )
            raise ValueError(msg)
        return self


class RiskEvalRecord(BaseModel):
    """单条 case 的 risk-only 评测记录（含报告元数据）。

    :param case_id: case 唯一标识。
    :param case_name: case 中文名称。
    :param result: risk-only 评测完整结果。
    :param rule_hits: 可选 Triage Core 规则命中摘要。
    :param bundle_version: 可选 triage-core bundle 版本 pin。
    """

    model_config = ConfigDict(
        extra="forbid", arbitrary_types_allowed=True, populate_by_name=True
    )

    case_id: str = Field(alias="caseId", description="case 唯一标识。")
    case_name: str = Field(
        alias="caseName", description="case 中文名称，便于批跑报告阅读。"
    )
    result: RiskEvalResult = Field(description="该 case 的 risk-only 评测结果。")
    rule_hits: list[str] | None = Field(
        default=None,
        description="可选；WP3 接入 Triage Core 后的 ruleHits 摘要。",
    )
    bundle_version: str | None = Field(
        default=None,
        alias="bundleVersion",
        description="可选；本次评测 pin 的 triage-core bundleVersion。",
    )


class RiskEvalReport(BaseModel):
    """20 case risk-only 批跑汇总报告。

    :param mode: 固定 ``risk-only``，与 future ``full-output`` 区分。
    :param dataset_version: mock case 数据集版本。
    :param total: 参与评测 case 总数。
    :param passed: 通过硬门槛数量。
    :param failed: 未通过硬门槛数量。
    :param records: 逐条评测记录。
    :param failed_case_ids: 失败 caseId 列表。
    :param confidence_check_mode: 本次 confidence 策略。
    :param confidence_hard_gate: confidence 软/硬门槛配置。
    :param schema_passed: minimal schema 通过数。
    :param risk_matched: riskLevel 一致数。
    :param confidence_matched: confidence 一致数；OFF 策略时为 null。
    :param generated_at: 报告生成 UTC 时间。
    :param bundle_version: 可选全局 bundle 版本 pin。
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mode: RiskEvalRunModeLiteral = Field(
        default="risk-only",
        description="批跑模式标识，固定为 risk-only。",
    )
    dataset_version: str = Field(
        alias="datasetVersion",
        description="mock case 数据集版本标识。",
    )
    total: int = Field(description="参与评测的 case 总数。")
    passed: int = Field(description="``RiskEvalResult.passed`` 为 true 的数量。")
    failed: int = Field(description="未通过硬门槛的 case 数量。")
    records: list[RiskEvalRecord] = Field(
        description="逐条评测记录，顺序与数据集 cases 一致。",
    )
    failed_case_ids: list[str] = Field(
        alias="failedCaseIds",
        default_factory=list,
        description="未通过硬门槛的 caseId 列表，便于 CI 快速定位。",
    )
    confidence_check_mode: ConfidenceCheckModeLiteral = Field(
        alias="confidenceCheckMode",
        description="本次批跑使用的 confidence 比对策略。",
    )
    confidence_hard_gate: ConfidenceHardGateModeLiteral = Field(
        alias="confidenceHardGate",
        default="soft",
        description="confidence 不匹配是否计为硬失败。",
    )
    schema_passed: int = Field(
        alias="schemaPassed",
        description="minimal output schema 校验通过的数量。",
    )
    risk_matched: int = Field(
        alias="riskMatched",
        description="riskLevel 与 expected 一致的数量（含 schema 未通过时未比对）。",
    )
    confidence_matched: int | None = Field(
        default=None,
        alias="confidenceMatched",
        description="confidence 一致数量；策略为 OFF 时为 null。",
    )
    generated_at: datetime = Field(
        alias="generatedAt",
        description="报告生成时间（UTC）。",
    )
    bundle_version: str | None = Field(
        default=None,
        alias="bundleVersion",
        description="可选；全报告级别的 triage-core bundleVersion。",
    )


# ---------------------------------------------------------------------------
# 组装与汇总函数
# ---------------------------------------------------------------------------


def flatten_risk_eval_violations(
    *,
    schema_check: ValidationResult[RiskEvalParsedOutput],
    risk: RiskDimensionResult,
    confidence: RiskDimensionResult,
    include_warnings_in_violations: bool,
) -> list[Violation]:
    """将 schema、risk、confidence 分维度违规扁平合并为单一列表。

    :param schema_check: minimal 结构校验结果。
    :type schema_check: ValidationResult[RiskEvalParsedOutput]
    :param risk: riskLevel 维度比对结果。
    :type risk: RiskDimensionResult
    :param confidence: confidence 维度比对结果。
    :type confidence: RiskDimensionResult
    :param include_warnings_in_violations: 为 true 时将 confidence 软警告并入 violations。
    :type include_warnings_in_violations: bool
    :returns: 按 schema → risk → confidence 顺序拼接的违规列表。
    :rtype: list[Violation]
    """
    merged: list[Violation] = []
    merged.extend(schema_check.violations)
    merged.extend(risk.violations)
    if include_warnings_in_violations:
        merged.extend(confidence.violations)
    elif confidence.check_applied:
        merged.extend(confidence.violations)
    return merged


def extract_risk_eval_warnings(
    confidence: RiskDimensionResult,
    *,
    confidence_hard_gate: ConfidenceHardGateModeLiteral,
) -> list[Violation]:
    """从 confidence 维度提取软门槛警告列表。

    :param confidence: confidence 维度比对结果。
    :type confidence: RiskDimensionResult
    :param confidence_hard_gate: confidence 硬门槛模式。
    :type confidence_hard_gate: ConfidenceHardGateModeLiteral
    :returns: 软门槛下的 confidence 违规副本列表；硬门槛或无违规时为空。
    :rtype: list[Violation]
    """
    if confidence_hard_gate != "soft":
        return []
    if not confidence.check_applied or confidence.passed is not False:
        return []
    return list(confidence.violations)


def compute_hard_passed(
    *,
    schema_check: ValidationResult[RiskEvalParsedOutput],
    risk: RiskDimensionResult,
) -> bool:
    """计算仅 schema + risk 维度的硬通过标志。

    :param schema_check: minimal 结构校验结果。
    :type schema_check: ValidationResult[RiskEvalParsedOutput]
    :param risk: riskLevel 维度比对结果。
    :type risk: RiskDimensionResult
    :returns: schema 通过且 risk 维度通过时为 true。
    :rtype: bool
    """
    if not schema_check.passed:
        return False
    return risk.passed is True


def compute_soft_passed(
    *,
    hard_passed: bool,
    confidence: RiskDimensionResult,
    check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral,
) -> bool:
    """在 hard 门槛基础上计算软门槛（含 confidence）。

    :param hard_passed: schema + risk 是否已通过。
    :type hard_passed: bool
    :param confidence: confidence 维度比对结果。
    :type confidence: RiskDimensionResult
    :param check_confidence_mode: confidence 比对策略；``off`` 时视为通过。
    :type check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral
    :returns: hard 为真且（未检查 confidence 或 confidence 通过）时为 ``True``。
    :rtype: bool
    """
    if not hard_passed:
        return False
    resolved_mode = _resolve_confidence_check_mode(check_confidence_mode)
    if resolved_mode == "off" or not confidence.check_applied:
        return True
    return confidence.passed is True


def compute_risk_eval_passed(
    *,
    hard_passed: bool,
    confidence: RiskDimensionResult,
    confidence_hard_gate: ConfidenceHardGateModeLiteral,
) -> bool:
    """在 hard_passed 基础上应用 confidence 硬门槛策略。

    :param hard_passed: schema + risk 是否已通过。
    :type hard_passed: bool
    :param confidence: confidence 维度比对结果。
    :type confidence: RiskDimensionResult
    :param confidence_hard_gate: confidence 不匹配是否拉低 passed。
    :type confidence_hard_gate: ConfidenceHardGateModeLiteral
    :returns: 最终硬门槛 passed 标志。
    :rtype: bool
    """
    if not hard_passed:
        return False
    if (
        confidence_hard_gate == "hard"
        and confidence.check_applied
        and confidence.passed is False
    ):
        return False
    return True


def build_risk_eval_result(
    *,
    schema_check: ValidationResult[RiskEvalParsedOutput],
    risk: RiskDimensionResult,
    confidence: RiskDimensionResult,
    check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral,
    confidence_hard_gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral = (
        ConfidenceHardGateMode.SOFT
    ),
) -> RiskEvalResult:
    """组装单条 case 的 ``RiskEvalResult`` 并同步扁平违规列表。

    :param schema_check: minimal 结构校验结果。
    :type schema_check: ValidationResult[RiskEvalParsedOutput]
    :param risk: riskLevel 维度比对结果。
    :type risk: RiskDimensionResult
    :param confidence: confidence 维度比对结果。
    :type confidence: RiskDimensionResult
    :param check_confidence_mode: confidence 比对策略。
    :type check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral
    :param confidence_hard_gate: confidence 软/硬门槛；默认 soft。
    :type confidence_hard_gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral
    :returns: 完整 risk-only 评测结果。
    :rtype: RiskEvalResult
    """
    resolved_mode = _resolve_confidence_check_mode(check_confidence_mode)
    resolved_gate = _resolve_confidence_hard_gate(confidence_hard_gate)
    hard_passed = compute_hard_passed(schema_check=schema_check, risk=risk)
    soft_passed = compute_soft_passed(
        hard_passed=hard_passed,
        confidence=confidence,
        check_confidence_mode=resolved_mode,
    )
    passed = compute_risk_eval_passed(
        hard_passed=hard_passed,
        confidence=confidence,
        confidence_hard_gate=resolved_gate,
    )
    include_confidence_in_violations = resolved_gate == "hard"
    violations = flatten_risk_eval_violations(
        schema_check=schema_check,
        risk=risk,
        confidence=confidence,
        include_warnings_in_violations=include_confidence_in_violations,
    )
    warnings = extract_risk_eval_warnings(
        confidence,
        confidence_hard_gate=resolved_gate,
    )
    return RiskEvalResult(
        passed=passed,
        hard_passed=hard_passed,
        soft_passed=soft_passed,
        schema_check=schema_check,
        risk=risk,
        confidence=confidence,
        violations=violations,
        warnings=warnings,
        check_confidence_mode=resolved_mode,
        confidence_hard_gate=resolved_gate,
    )


def build_risk_eval_record(
    *,
    case_id: str,
    case_name: str,
    result: RiskEvalResult,
    rule_hits: list[str] | None = None,
    bundle_version: str | None = None,
) -> RiskEvalRecord:
    """封装单条 case 评测记录。

    :param case_id: case 唯一标识。
    :type case_id: str
    :param case_name: case 中文名称。
    :type case_name: str
    :param result: risk-only 评测结果。
    :type result: RiskEvalResult
    :param rule_hits: 可选 ruleHits 摘要。
    :type rule_hits: list[str] | None
    :param bundle_version: 可选 triage-core 版本。
    :type bundle_version: str | None
    :returns: 带元数据的评测记录。
    :rtype: RiskEvalRecord
    """
    return RiskEvalRecord(
        caseId=case_id,
        caseName=case_name,
        result=result,
        rule_hits=rule_hits,
        bundleVersion=bundle_version,
    )


def summarize_risk_eval_records(
    records: Sequence[RiskEvalRecord],
    *,
    confidence_check_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral,
) -> tuple[int, int, int, int, int | None]:
    """统计一批 ``RiskEvalRecord`` 的通过数与分维度匹配数。

    :param records: 评测记录序列。
    :type records: collections.abc.Sequence[RiskEvalRecord]
    :param confidence_check_mode: confidence 比对策略（OFF 时不统计 confidence_matched）。
    :type confidence_check_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral
    :returns: ``(passed, failed, schema_passed, risk_matched, confidence_matched)``；
        ``confidence_matched`` 在策略 OFF 时为 null。
    :rtype: tuple[int, int, int, int, int | None]
    """
    resolved_mode = _resolve_confidence_check_mode(confidence_check_mode)
    total = len(records)
    passed_count = sum(1 for item in records if item.result.passed)
    failed_count = total - passed_count
    schema_passed = sum(1 for item in records if item.result.schema_check.passed)
    risk_matched = sum(1 for item in records if item.result.risk.passed is True)
    confidence_matched: int | None
    if resolved_mode == "off":
        confidence_matched = None
    else:
        confidence_matched = sum(
            1
            for item in records
            if item.result.confidence.check_applied
            and item.result.confidence.passed is True
        )
    return passed_count, failed_count, schema_passed, risk_matched, confidence_matched


def build_risk_eval_report(
    records: Sequence[RiskEvalRecord],
    *,
    dataset_version: str = DEFAULT_DATASET_VERSION,
    confidence_check_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral = (
        ConfidenceCheckMode.OFF
    ),
    confidence_hard_gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral = (
        ConfidenceHardGateMode.SOFT
    ),
    bundle_version: str | None = None,
    generated_at: datetime | None = None,
) -> RiskEvalReport:
    """由逐条评测记录构建批跑汇总报告。

    :param records: 评测记录序列，通常与 ``dataset.cases`` 顺序一致。
    :type records: collections.abc.Sequence[RiskEvalRecord]
    :param dataset_version: mock case 数据集版本。
    :type dataset_version: str
    :param confidence_check_mode: confidence 比对策略。
    :type confidence_check_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral
    :param confidence_hard_gate: confidence 软/硬门槛。
    :type confidence_hard_gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral
    :param bundle_version: 可选全报告级 bundle 版本。
    :type bundle_version: str | None
    :param generated_at: 报告时间；省略时为当前 UTC 时间。
    :type generated_at: datetime | None
    :returns: 完整 risk-only 批跑报告。
    :rtype: RiskEvalReport
    """
    resolved_mode = _resolve_confidence_check_mode(confidence_check_mode)
    resolved_gate = _resolve_confidence_hard_gate(confidence_hard_gate)
    record_list = list(records)
    passed_count, failed_count, schema_passed, risk_matched, confidence_matched = (
        summarize_risk_eval_records(
            record_list,
            confidence_check_mode=resolved_mode,
        )
    )
    failed_case_ids = [item.case_id for item in record_list if not item.result.passed]
    timestamp = generated_at if generated_at is not None else datetime.now(tz=UTC)
    return RiskEvalReport(
        mode=RiskEvalRunMode.RISK_ONLY.value,
        datasetVersion=dataset_version,
        total=len(record_list),
        passed=passed_count,
        failed=failed_count,
        records=record_list,
        failedCaseIds=failed_case_ids,
        confidenceCheckMode=resolved_mode,
        confidenceHardGate=resolved_gate,
        schemaPassed=schema_passed,
        riskMatched=risk_matched,
        confidenceMatched=confidence_matched,
        generatedAt=timestamp,
        bundleVersion=bundle_version,
    )


def make_initial_risk_dimension(
    dimension: RiskEvalDimension | RiskEvalDimensionLiteral,
    *,
    check_applied: bool,
    expected: OutputRiskLevelLiteral | ConfidenceLiteral | None = None,
) -> RiskDimensionResult:
    """创建尚未完成比对的 ``RiskDimensionResult`` 占位。

    :param dimension: 维度种类，``risk`` 或 ``confidence``。
    :type dimension: RiskEvalDimension | RiskEvalDimensionLiteral
    :param check_applied: 是否将执行 expected vs actual 比对。
    :type check_applied: bool
    :param expected: 可选，来自 ``CaseExpected`` 的期望值。
    :type expected: OutputRiskLevelLiteral | ConfidenceLiteral | None
    :returns: ``passed`` 与 ``actual`` 为 ``None`` 的初始维度结果。
    :rtype: RiskDimensionResult
    """
    dim_value = (
        dimension.value if isinstance(dimension, RiskEvalDimension) else dimension
    )
    return RiskDimensionResult(
        dimension=dim_value,
        check_applied=check_applied,
        passed=None,
        expected=expected,
        actual=None,
        violations=[],
    )


def partition_risk_eval_violations(
    schema_check: ValidationResult[RiskEvalParsedOutput],
    risk: RiskDimensionResult,
    confidence: RiskDimensionResult,
    check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral,
    *,
    confidence_hard_gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral = (
        ConfidenceHardGateMode.SOFT
    ),
) -> tuple[list[Violation], list[Violation]]:
    """将评测违规拆分为硬违规与软警告。

    :param schema_check: minimal 结构校验结果。
    :type schema_check: ValidationResult[RiskEvalParsedOutput]
    :param risk: riskLevel 维度结果。
    :type risk: RiskDimensionResult
    :param confidence: confidence 维度结果。
    :type confidence: RiskDimensionResult
    :param check_confidence_mode: confidence 比对策略。
    :type check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral
    :param confidence_hard_gate: confidence 软/硬门槛；``soft`` 时不将 confidence 并入硬违规。
    :type confidence_hard_gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral
    :returns: ``(硬违规列表, 软警告列表)`` 元组。
    :rtype: tuple[list[Violation], list[Violation]]
    """
    resolved_gate = _resolve_confidence_hard_gate(confidence_hard_gate)
    hard = flatten_risk_eval_violations(
        schema_check=schema_check,
        risk=risk,
        confidence=confidence,
        include_warnings_in_violations=resolved_gate == "hard",
    )
    warnings = extract_risk_eval_warnings(
        confidence,
        confidence_hard_gate=resolved_gate,
    )
    return hard, warnings


def collect_flat_violations(
    schema_check: ValidationResult[RiskEvalParsedOutput],
    risk: RiskDimensionResult,
    confidence: RiskDimensionResult,
    check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral,
    *,
    confidence_hard_gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral = (
        ConfidenceHardGateMode.SOFT
    ),
) -> list[Violation]:
    """合并 schema、risk、confidence 的硬违规为扁平列表。

    :param schema_check: 结构校验结果。
    :type schema_check: ValidationResult[RiskEvalParsedOutput]
    :param risk: risk 维度结果。
    :type risk: RiskDimensionResult
    :param confidence: confidence 维度结果。
    :type confidence: RiskDimensionResult
    :param check_confidence_mode: confidence 策略（保留供 API 对称，当前由 hard_gate 决定拆分）。
    :type check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral
    :param confidence_hard_gate: confidence 软/硬门槛。
    :type confidence_hard_gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral
    :returns: 硬违规扁平列表。
    :rtype: list[Violation]
    """
    hard, _warnings = partition_risk_eval_violations(
        schema_check,
        risk,
        confidence,
        check_confidence_mode,
        confidence_hard_gate=confidence_hard_gate,
    )
    return hard


def minimal_output_validation_mode() -> Literal["minimal"]:
    """返回 risk-only 评测固定的 output schema 校验模式。

    :returns: 字面量 ``\"minimal\"``。
    :rtype: Literal['minimal']
    """
    return "minimal"


def make_risk_mismatch_violation(
    *,
    expected: OutputRiskLevelLiteral,
    actual: OutputRiskLevelLiteral | None,
    case_id: str | None = None,
) -> Violation:
    """构造 riskLevel 不一致的 ``Violation``。

    :param expected: 期望风险等级。
    :type expected: OutputRiskLevelLiteral
    :param actual: 实际风险等级；未提取时为 null。
    :type actual: OutputRiskLevelLiteral | None
    :param case_id: 可选 caseId，写入 message 便于报告定位。
    :type case_id: str | None
    :returns: ``domain=risk_eval`` 的 HIGH 严重度违规记录。
    :rtype: Violation
    """
    case_suffix = f"（case: {case_id}）" if case_id is not None else ""
    actual_text = actual if actual is not None else "（未提取）"
    return Violation(
        code=ViolationCode.RISK_MISMATCH.value,
        domain="risk_eval",
        path="riskLevel",
        field="riskLevel",
        message=(
            f"riskLevel 与期望不一致：期望 {expected!r}，实际 {actual_text!r}{case_suffix}"
        ),
        severity="HIGH",
    )


def make_confidence_mismatch_violation(
    *,
    expected: ConfidenceLiteral,
    actual: ConfidenceLiteral | None,
    case_id: str | None = None,
    severity: ViolationSeverityLiteral = "MEDIUM",
) -> Violation:
    """构造 confidence 不一致的 ``Violation``。

    :param expected: 期望置信度档位。
    :type expected: ConfidenceLiteral
    :param actual: 实际置信度；未提取时为 null。
    :type actual: ConfidenceLiteral | None
    :param case_id: 可选 caseId。
    :type case_id: str | None
    :param severity: 违规严重度；软门槛默认 MEDIUM。
    :type severity: ViolationSeverityLiteral
    :returns: ``domain=risk_eval`` 的违规记录。
    :rtype: Violation
    """
    case_suffix = f"（case: {case_id}）" if case_id is not None else ""
    actual_text = actual if actual is not None else "（未提取）"
    return Violation(
        code=ViolationCode.CONFIDENCE_MISMATCH.value,
        domain="risk_eval",
        path="confidence",
        field="confidence",
        message=(
            f"confidence 与期望不一致：期望 {expected!r}，实际 {actual_text!r}{case_suffix}"
        ),
        severity=severity,
    )


def make_eval_skipped_violation(
    *,
    reason: str,
    case_id: str | None = None,
) -> Violation:
    """构造因前置步骤失败而跳过比对的 ``Violation``。

    :param reason: 跳过原因（如结构校验未通过）。
    :type reason: str
    :param case_id: 可选 caseId。
    :type case_id: str | None
    :returns: domain 为 ``risk_eval``、严重度 LOW 的违规记录。
    :rtype: Violation
    """
    case_suffix = f"（case: {case_id}）" if case_id is not None else ""
    return Violation(
        code=ViolationCode.EVAL_SKIPPED.value,
        domain="risk_eval",
        path="$",
        field=None,
        message=f"跳过 risk/confidence 比对：{reason}{case_suffix}",
        severity="LOW",
    )


def make_case_output_missing_violation(*, case_id: str) -> Violation:
    """构造批跑时缺少某 case 输出的 ``Violation``。

    :param case_id: 缺失输出的 caseId。
    :type case_id: str
    :returns: domain 为 ``risk_eval`` 的违规记录。
    :rtype: Violation
    """
    return Violation(
        code=ViolationCode.CASE_OUTPUT_MISSING.value,
        domain="risk_eval",
        path="$",
        field=None,
        message=f"批跑缺少 caseId={case_id!r} 的 Agent 输出。",
        severity="HIGH",
    )


def _resolve_confidence_check_mode(
    mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral,
) -> ConfidenceCheckModeLiteral:
    """将 confidence 策略参数规范化为 Literal 字符串。

    :param mode: 枚举或字符串形式的策略。
    :type mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral
    :returns: 规范化后的策略字符串。
    :rtype: ConfidenceCheckModeLiteral
    :raises ValueError: 传入未知策略时抛出。
    """
    if isinstance(mode, ConfidenceCheckMode):
        return mode.value
    if mode in ("off", "exact", "tier"):
        return mode
    msg = f"不支持的 confidence 比对策略：{mode!r}，允许 off / exact / tier。"
    raise ValueError(msg)


def _resolve_confidence_hard_gate(
    gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral,
) -> ConfidenceHardGateModeLiteral:
    """将 confidence 硬门槛参数规范化为 Literal 字符串。

    :param gate: 枚举或字符串形式的硬门槛模式。
    :type gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral
    :returns: 规范化后的硬门槛字符串。
    :rtype: ConfidenceHardGateModeLiteral
    :raises ValueError: 传入未知模式时抛出。
    """
    if isinstance(gate, ConfidenceHardGateMode):
        return gate.value
    if gate in ("soft", "hard"):
        return gate
    msg = f"不支持的 confidence 硬门槛模式：{gate!r}，允许 soft / hard。"
    raise ValueError(msg)


# ---------------------------------------------------------------------------
# 解析抽取与维度比对完成（risk_evaluator 消费）
# ---------------------------------------------------------------------------


def extract_risk_level_from_parsed(
    parsed: RiskEvalParsedOutput,
) -> OutputRiskLevelLiteral:
    """从 minimal/full 解析结果抽取 ``riskLevel``。

    :param parsed: ``validate_output(..., MINIMAL)`` 通过后的强类型对象。
    :type parsed: RiskEvalParsedOutput
    :returns: 输出风险等级字符串。
    :rtype: OutputRiskLevelLiteral
    """
    return parsed.risk_level


def extract_confidence_from_parsed(
    parsed: RiskEvalParsedOutput,
) -> ConfidenceLiteral | None:
    """从解析结果抽取 ``confidence``；minimal 模式下允许缺失。

    :param parsed: 结构校验通过后的输出模型。
    :type parsed: RiskEvalParsedOutput
    :returns: 置信度档位；模型字段为 ``None`` 时返回 ``None``。
    :rtype: ConfidenceLiteral | None
    """
    return parsed.confidence


def compare_risk_levels(
    *,
    expected: OutputRiskLevelLiteral,
    actual: OutputRiskLevelLiteral | None,
    case_id: str | None = None,
) -> RiskDimensionResult:
    """完成 risk 维度的 expected vs actual 比对并返回 ``RiskDimensionResult``。

    :param expected: 来自 ``CaseExpected.risk_level`` 的期望风险等级。
    :type expected: OutputRiskLevelLiteral
    :param actual: 从 Agent 输出抽取的实际风险等级；未提取时为 ``None``。
    :type actual: OutputRiskLevelLiteral | None
    :param case_id: 可选 caseId，写入违规 message 便于批跑定位。
    :type case_id: str | None
    :returns: ``check_applied=True`` 的 risk 维度完整比对结果。
    :rtype: RiskDimensionResult
    """
    passed: bool | None
    violations: list[Violation]

    if actual is None:
        passed = False
        violations = [
            make_eval_skipped_violation(
                reason="未能从输出中提取 riskLevel",
                case_id=case_id,
            )
        ]
    elif actual == expected:
        passed = True
        violations = []
    else:
        passed = False
        violations = [
            make_risk_mismatch_violation(
                expected=expected,
                actual=actual,
                case_id=case_id,
            )
        ]

    return RiskDimensionResult(
        dimension=RiskEvalDimension.RISK.value,
        check_applied=True,
        passed=passed,
        expected=expected,
        actual=actual,
        violations=violations,
    )


def compare_confidence_levels(
    *,
    expected: ConfidenceLiteral,
    actual: ConfidenceLiteral | None,
    check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral,
    case_id: str | None = None,
) -> RiskDimensionResult:
    """完成 confidence 维度的 expected vs actual 比对。

    策略为 ``off`` 时返回 ``check_applied=False`` 的占位结果；``exact`` 与 ``tier``
      在 V1 三档 Literal 下行为相同（字符串精确相等）。

      :param expected: 来自 ``CaseExpected.confidence`` 的期望置信度。
      :type expected: ConfidenceLiteral
      :param actual: 从 Agent 输出抽取的实际置信度。
      :type actual: ConfidenceLiteral | None
      :param check_confidence_mode: confidence 比对策略。
      :type check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral
      :param case_id: 可选 caseId。
      :type case_id: str | None
      :returns: confidence 维度比对结果。
      :rtype: RiskDimensionResult
    """
    resolved_mode = _resolve_confidence_check_mode(check_confidence_mode)

    if resolved_mode == "off":
        return make_initial_risk_dimension(
            RiskEvalDimension.CONFIDENCE,
            check_applied=False,
            expected=expected,
        )

    passed: bool | None
    violations: list[Violation]

    if actual is None:
        passed = False
        violations = [
            make_eval_skipped_violation(
                reason="未能从输出中提取 confidence",
                case_id=case_id,
            )
        ]
    elif _confidence_values_match(
        expected=expected,
        actual=actual,
        mode=resolved_mode,
    ):
        passed = True
        violations = []
    else:
        passed = False
        violations = [
            make_confidence_mismatch_violation(
                expected=expected,
                actual=actual,
                case_id=case_id,
                severity="MEDIUM",
            )
        ]

    return RiskDimensionResult(
        dimension=RiskEvalDimension.CONFIDENCE.value,
        check_applied=True,
        passed=passed,
        expected=expected,
        actual=actual,
        violations=violations,
    )


def build_schema_failed_risk_eval_result(
    *,
    schema_check: ValidationResult[RiskEvalParsedOutput],
    expected_risk_level: OutputRiskLevelLiteral,
    expected_confidence: ConfidenceLiteral,
    check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral,
    confidence_hard_gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral = (
        ConfidenceHardGateMode.SOFT
    ),
    case_id: str | None = None,
) -> RiskEvalResult:
    """在 minimal schema 未通过时组装完整的 ``RiskEvalResult``。

    risk / confidence 维度标记为已尝试但因结构失败而跳过实际比对；
    ``actual`` 保持 ``None``，并附加 ``EVAL_SKIPPED`` 说明。

    :param schema_check: 未通过的 minimal 结构校验结果。
    :type schema_check: ValidationResult[RiskEvalParsedOutput]
    :param expected_risk_level: 期望风险等级（仅填入 ``expected`` 字段供报告展示）。
    :type expected_risk_level: OutputRiskLevelLiteral
    :param expected_confidence: 期望置信度。
    :type expected_confidence: ConfidenceLiteral
    :param check_confidence_mode: confidence 比对策略。
    :type check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral
    :param confidence_hard_gate: confidence 软/硬门槛。
    :type confidence_hard_gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral
    :param case_id: 可选 caseId。
    :type case_id: str | None
    :returns: ``passed=False`` 的完整评测结果。
    :rtype: RiskEvalResult
    """
    skip_reason = "output 未通过 minimal schema 校验"
    skip_violation = make_eval_skipped_violation(reason=skip_reason, case_id=case_id)

    risk = RiskDimensionResult(
        dimension=RiskEvalDimension.RISK.value,
        check_applied=True,
        passed=False,
        expected=expected_risk_level,
        actual=None,
        violations=[skip_violation],
    )

    resolved_mode = _resolve_confidence_check_mode(check_confidence_mode)
    if resolved_mode == "off":
        confidence = make_initial_risk_dimension(
            RiskEvalDimension.CONFIDENCE,
            check_applied=False,
            expected=expected_confidence,
        )
    else:
        confidence = RiskDimensionResult(
            dimension=RiskEvalDimension.CONFIDENCE.value,
            check_applied=True,
            passed=False,
            expected=expected_confidence,
            actual=None,
            violations=[skip_violation],
        )

    return build_risk_eval_result(
        schema_check=schema_check,
        risk=risk,
        confidence=confidence,
        check_confidence_mode=resolved_mode,
        confidence_hard_gate=confidence_hard_gate,
    )


def build_missing_output_risk_eval_result(
    *,
    expected_risk_level: OutputRiskLevelLiteral,
    expected_confidence: ConfidenceLiteral,
    check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral = (
        ConfidenceCheckMode.OFF
    ),
    confidence_hard_gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral = (
        ConfidenceHardGateMode.SOFT
    ),
    case_id: str,
) -> RiskEvalResult:
    """批跑时某 case 无 Agent 输出时构造失败结果。

    不执行 schema 校验；合成未通过的 ``ValidationResult`` 与
    ``CASE_OUTPUT_MISSING`` 违规。

    :param expected_risk_level: 期望风险等级（报告展示用）。
    :type expected_risk_level: OutputRiskLevelLiteral
    :param expected_confidence: 期望置信度。
    :type expected_confidence: ConfidenceLiteral
    :param check_confidence_mode: confidence 比对策略。
    :type check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral
    :param confidence_hard_gate: confidence 软/硬门槛。
    :type confidence_hard_gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral
    :param case_id: 缺失输出的 caseId。
    :type case_id: str
    :returns: ``passed=False`` 的评测结果。
    :rtype: RiskEvalResult
    """
    from xiaozhua_health_agent.eval.schema_validator import OUTPUT_SCHEMA_VERSION

    missing_violation = make_case_output_missing_violation(case_id=case_id)

    schema_check: ValidationResult[RiskEvalParsedOutput] = ValidationResult(
        passed=False,
        schema_kind="output",
        schema_version=OUTPUT_SCHEMA_VERSION,
        mode=minimal_output_validation_mode(),
        violations=[missing_violation],
        parsed=None,
    )

    risk = RiskDimensionResult(
        dimension=RiskEvalDimension.RISK.value,
        check_applied=True,
        passed=False,
        expected=expected_risk_level,
        actual=None,
        violations=[missing_violation],
    )

    resolved_mode = _resolve_confidence_check_mode(check_confidence_mode)
    if resolved_mode == "off":
        confidence = make_initial_risk_dimension(
            RiskEvalDimension.CONFIDENCE,
            check_applied=False,
            expected=expected_confidence,
        )
    else:
        confidence = RiskDimensionResult(
            dimension=RiskEvalDimension.CONFIDENCE.value,
            check_applied=True,
            passed=False,
            expected=expected_confidence,
            actual=None,
            violations=[missing_violation],
        )

    return build_risk_eval_result(
        schema_check=schema_check,
        risk=risk,
        confidence=confidence,
        check_confidence_mode=resolved_mode,
        confidence_hard_gate=confidence_hard_gate,
    )


def build_missing_output_risk_eval_record(
    *,
    case_id: str,
    case_name: str,
    expected_risk_level: OutputRiskLevelLiteral,
    expected_confidence: ConfidenceLiteral,
    check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral = (
        ConfidenceCheckMode.OFF
    ),
    confidence_hard_gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral = (
        ConfidenceHardGateMode.SOFT
    ),
    bundle_version: str | None = None,
) -> RiskEvalRecord:
    """批跑缺输出时封装 ``RiskEvalRecord``。

    :param case_id: case 唯一标识。
    :type case_id: str
    :param case_name: case 中文名称。
    :type case_name: str
    :param expected_risk_level: 期望风险等级。
    :type expected_risk_level: OutputRiskLevelLiteral
    :param expected_confidence: 期望置信度。
    :type expected_confidence: ConfidenceLiteral
    :param check_confidence_mode: confidence 比对策略。
    :type check_confidence_mode: ConfidenceCheckMode | ConfidenceCheckModeLiteral
    :param confidence_hard_gate: confidence 软/硬门槛。
    :type confidence_hard_gate: ConfidenceHardGateMode | ConfidenceHardGateModeLiteral
    :param bundle_version: 可选 triage-core 版本 pin。
    :type bundle_version: str | None
    :returns: 带元数据的失败评测记录。
    :rtype: RiskEvalRecord
    """
    result = build_missing_output_risk_eval_result(
        expected_risk_level=expected_risk_level,
        expected_confidence=expected_confidence,
        check_confidence_mode=check_confidence_mode,
        confidence_hard_gate=confidence_hard_gate,
        case_id=case_id,
    )
    return build_risk_eval_record(
        case_id=case_id,
        case_name=case_name,
        result=result,
        bundle_version=bundle_version,
    )


def count_violations_by_code(
    violations: Sequence[Violation],
) -> dict[ViolationCodeLiteral, int]:
    """按 ``Violation.code`` 聚合违规数量（批跑报告统计用）。

    :param violations: 违规项序列。
    :type violations: collections.abc.Sequence[Violation]
    :returns: 违规码到出现次数的映射。
    :rtype: dict[str, int]
    """
    counts: dict[ViolationCodeLiteral, int] = {}
    for item in violations:
        counts[item.code] = counts.get(item.code, 0) + 1
    return counts


def iter_all_record_violations(
    records: Sequence[RiskEvalRecord],
    *,
    include_warnings: bool = False,
) -> list[Violation]:
    """扁平收集一批 ``RiskEvalRecord`` 的全部违规项。

    :param records: 评测记录序列。
    :type records: collections.abc.Sequence[RiskEvalRecord]
    :param include_warnings: 为 ``True`` 时追加各记录的 ``warnings``。
    :type include_warnings: bool
    :returns: 按记录顺序拼接的违规列表。
    :rtype: list[Violation]
    """
    merged: list[Violation] = []
    for record in records:
        merged.extend(record.result.violations)
        if include_warnings:
            merged.extend(record.result.warnings)
    return merged


def _confidence_values_match(
    *,
    expected: ConfidenceLiteral,
    actual: ConfidenceLiteral,
    mode: ConfidenceCheckModeLiteral,
) -> bool:
    """判断 confidence 期望值与实际值是否在给定策略下匹配。

    :param expected: 期望置信度档位。
    :type expected: ConfidenceLiteral
    :param actual: 实际置信度档位。
    :type actual: ConfidenceLiteral
    :param mode: 比对策略；``exact`` 与 ``tier`` 在 V1 均为字符串相等。
    :type mode: ConfidenceCheckModeLiteral
    :returns: 匹配时为 ``True``。
    :rtype: bool
    :raises ValueError: ``mode`` 为 ``off`` 时调用（调用方不应传入 off）。
    """
    if mode == "off":
        msg = "confidence 策略为 off 时不应调用 _confidence_values_match。"
        raise ValueError(msg)
    return actual == expected
