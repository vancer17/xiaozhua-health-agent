"""Risk-only 评测编排器（WP0）。

串联 minimal schema 校验 → risk/confidence 维度比对 → ``RiskEvalResult`` /
``RiskEvalRecord`` / ``RiskEvalReport`` 组装。不参与医学裁决，不调用分诊管道。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.eval.case_dataset import (
    DEFAULT_DATASET_VERSION,
    CaseExpected,
    CaseRecord,
    HealthTriageDataset,
)
from xiaozhua_health_agent.eval.risk_eval_types import (
    ConfidenceCheckMode,
    ConfidenceCheckModeLiteral,
    ConfidenceHardGateMode,
    ConfidenceHardGateModeLiteral,
    RiskEvalParsedOutput,
    RiskEvalRecord,
    RiskEvalReport,
    RiskEvalResult,
    build_missing_output_risk_eval_result,
    build_risk_eval_record,
    build_risk_eval_report,
    build_risk_eval_result,
    build_schema_failed_risk_eval_result,
    compare_confidence_levels,
    compare_risk_levels,
    extract_confidence_from_parsed,
    extract_risk_level_from_parsed,
)
from xiaozhua_health_agent.eval.schema_validator import validate_output
from xiaozhua_health_agent.eval.validation_result import (
    OutputValidationMode,
    ValidationResult,
)
from xiaozhua_health_agent.schemas import (
    AgentInput,
    AgentOutput,
    RiskOnlyOutput,
)

# ---------------------------------------------------------------------------
# 类型别名
# ---------------------------------------------------------------------------

ActualOutputPayload: TypeAlias = Mapping[str, Any] | AgentOutput | RiskOnlyOutput | None
"""单条 case 的 Agent 实际输出载荷（dict、强类型模型或缺失）。"""

OutputsByCaseId: TypeAlias = Mapping[str, ActualOutputPayload]
"""caseId → 实际输出 的映射，供批跑使用。"""

TriageOutputProvider: TypeAlias = Callable[[AgentInput], ActualOutputPayload]
"""分诊管道回调：入参为 ``AgentInput``，返回该 case 的结构化输出（或 ``None``）。"""

# ---------------------------------------------------------------------------
# 评测配置
# ---------------------------------------------------------------------------


class RiskEvalOptions(BaseModel):
    """Risk-only 评测运行配置。

    :param confidence_check_mode: confidence 比对策略；WP3 里程碑 A 默认 ``off``。
    :param confidence_hard_gate: confidence 不匹配是否拉低 ``passed``；默认 ``soft``。
    :param bundle_version: 可选 triage-core ``bundleVersion`` pin，写入记录与报告。
    :param dataset_version: mock case 数据集版本，写入报告元数据。
    """

    model_config = ConfigDict(extra="forbid")

    confidence_check_mode: ConfidenceCheckModeLiteral = Field(
        default=ConfidenceCheckMode.OFF.value,
        description="confidence 比对策略：off / exact / tier。",
    )
    confidence_hard_gate: ConfidenceHardGateModeLiteral = Field(
        default=ConfidenceHardGateMode.SOFT.value,
        description="confidence 软门槛（warnings）或硬门槛（拉低 passed）。",
    )
    bundle_version: str | None = Field(
        default=None,
        description="可选；本次评测 pin 的 triage-core bundleVersion。",
    )
    dataset_version: str = Field(
        default=DEFAULT_DATASET_VERSION,
        description="mock case 数据集版本标识，写入 ``RiskEvalReport``。",
    )


DEFAULT_RISK_EVAL_OPTIONS: RiskEvalOptions = RiskEvalOptions()
"""WP3 risk-only 默认配置：仅比 riskLevel，confidence 不检查。"""


# ---------------------------------------------------------------------------
# 单条评测
# ---------------------------------------------------------------------------


def evaluate_risk_output(
    *,
    expected: CaseExpected,
    actual_output: ActualOutputPayload,
    case_id: str | None = None,
    options: RiskEvalOptions | None = None,
    rule_hits: list[str] | None = None,
) -> RiskEvalResult:
    """对单条输出执行 risk-only 评测（schema → 比对 → 组装结果）。

    固定使用 ``validate_output(..., mode=MINIMAL)`` 做结构门禁；通过后再比对
    ``riskLevel`` 与可选 ``confidence``。

    :param expected: 来自 ``CaseRecord.expected`` 的验收约束。
    :type expected: CaseExpected
    :param actual_output: Agent 实际输出；``None`` 视为批跑缺输出。
    :type actual_output: ActualOutputPayload
    :param case_id: 可选 caseId，写入违规 message 与跳过说明。
    :type case_id: str | None
    :param options: 评测配置；省略时使用 ``DEFAULT_RISK_EVAL_OPTIONS``。
    :type options: RiskEvalOptions | None
    :param rule_hits: 可选；若省略且 ``actual_output`` 为含 ``ruleHits`` 的 dict，
        将自动抽取（供 WP3 调试报告使用，不参与 passed 计算）。
    :type rule_hits: list[str] | None
    :returns: 单条 case 的完整 risk-only 评测结果。
    :rtype: RiskEvalResult
    """
    resolved_options = options if options is not None else DEFAULT_RISK_EVAL_OPTIONS

    if actual_output is None:
        return build_missing_output_risk_eval_result(
            expected_risk_level=expected.risk_level,
            expected_confidence=expected.confidence,
            check_confidence_mode=resolved_options.confidence_check_mode,
            confidence_hard_gate=resolved_options.confidence_hard_gate,
            case_id=case_id or "unknown",
        )

    schema_check = cast(
        ValidationResult[RiskEvalParsedOutput],
        validate_output(
            actual_output,
            mode=OutputValidationMode.MINIMAL,
        ),
    )

    if not schema_check.passed or schema_check.parsed is None:
        return build_schema_failed_risk_eval_result(
            schema_check=schema_check,
            expected_risk_level=expected.risk_level,
            expected_confidence=expected.confidence,
            check_confidence_mode=resolved_options.confidence_check_mode,
            confidence_hard_gate=resolved_options.confidence_hard_gate,
            case_id=case_id,
        )

    parsed = schema_check.parsed
    actual_risk = extract_risk_level_from_parsed(parsed)
    actual_confidence = extract_confidence_from_parsed(parsed)

    risk_dimension = compare_risk_levels(
        expected=expected.risk_level,
        actual=actual_risk,
        case_id=case_id,
    )
    confidence_dimension = compare_confidence_levels(
        expected=expected.confidence,
        actual=actual_confidence,
        check_confidence_mode=resolved_options.confidence_check_mode,
        case_id=case_id,
    )

    return build_risk_eval_result(
        schema_check=schema_check,
        risk=risk_dimension,
        confidence=confidence_dimension,
        check_confidence_mode=resolved_options.confidence_check_mode,
        confidence_hard_gate=resolved_options.confidence_hard_gate,
    )


def evaluate_risk_for_case(
    case: CaseRecord,
    actual_output: ActualOutputPayload,
    *,
    options: RiskEvalOptions | None = None,
    rule_hits: list[str] | None = None,
) -> RiskEvalRecord:
    """对单条 ``CaseRecord`` 执行 risk-only 评测并封装记录。

    :param case: mock case（含 ``input`` 与 ``expected``）。
    :type case: CaseRecord
    :param actual_output: 该 case 的 Agent 实际输出。
    :type actual_output: ActualOutputPayload
    :param options: 评测配置。
    :type options: RiskEvalOptions | None
    :param rule_hits: 可选 ruleHits；省略时尝试从 dict 输出抽取。
    :type rule_hits: list[str] | None
    :returns: 带 case 元数据的评测记录。
    :rtype: RiskEvalRecord
    """
    resolved_options = options if options is not None else DEFAULT_RISK_EVAL_OPTIONS
    resolved_rule_hits = rule_hits
    if resolved_rule_hits is None and isinstance(actual_output, Mapping):
        resolved_rule_hits = extract_rule_hits_from_payload(actual_output)

    result = evaluate_risk_output(
        expected=case.expected,
        actual_output=actual_output,
        case_id=case.case_id,
        options=resolved_options,
        rule_hits=resolved_rule_hits,
    )
    return build_risk_eval_record(
        case_id=case.case_id,
        case_name=case.name,
        result=result,
        rule_hits=resolved_rule_hits,
        bundle_version=resolved_options.bundle_version,
    )


def evaluate_all_cases(
    dataset: HealthTriageDataset,
    outputs_by_case_id: OutputsByCaseId,
    *,
    options: RiskEvalOptions | None = None,
) -> list[RiskEvalRecord]:
    """对数据集中全部 case 执行 risk-only 评测。

    ``outputs_by_case_id`` 中缺失的 caseId 视为无输出（``CASE_OUTPUT_MISSING``）。
    记录顺序与 ``dataset.cases`` 文件顺序一致。

    :param dataset: 已加载的 mock case 数据集。
    :type dataset: HealthTriageDataset
    :param outputs_by_case_id: caseId 到实际输出的映射。
    :type outputs_by_case_id: OutputsByCaseId
    :param options: 评测配置。
    :type options: RiskEvalOptions | None
    :returns: 与 ``dataset.cases`` 顺序一致的评测记录列表。
    :rtype: list[RiskEvalRecord]
    """
    records: list[RiskEvalRecord] = []
    for case in dataset.cases:
        actual = outputs_by_case_id.get(case.case_id)
        records.append(
            evaluate_risk_for_case(
                case,
                actual,
                options=options,
            )
        )
    return records


def evaluate_all_cases_with_provider(
    dataset: HealthTriageDataset,
    provider: TriageOutputProvider,
    *,
    options: RiskEvalOptions | None = None,
) -> list[RiskEvalRecord]:
    """使用分诊回调对全部 case 生成输出并评测。

    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param provider: 接收 ``case.input``、返回该 case 输出的回调（如 Triage Core stub）。
    :type provider: TriageOutputProvider
    :param options: 评测配置。
    :type options: RiskEvalOptions | None
    :returns: 逐条评测记录列表。
    :rtype: list[RiskEvalRecord]
    """
    outputs: dict[str, ActualOutputPayload] = {}
    for case in dataset.cases:
        outputs[case.case_id] = provider(case.input)
    return evaluate_all_cases(dataset, outputs, options=options)


def run_risk_only_evaluation(
    dataset: HealthTriageDataset,
    outputs_by_case_id: OutputsByCaseId,
    *,
    options: RiskEvalOptions | None = None,
) -> RiskEvalReport:
    """执行完整 risk-only 批跑并返回汇总报告。

    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param outputs_by_case_id: caseId → 实际输出映射。
    :type outputs_by_case_id: OutputsByCaseId
    :param options: 评测配置（含 ``dataset_version``、``bundle_version``）。
    :type options: RiskEvalOptions | None
    :returns: 20 case risk-only 批跑汇总报告。
    :rtype: RiskEvalReport
    """
    resolved_options = options if options is not None else DEFAULT_RISK_EVAL_OPTIONS
    records = evaluate_all_cases(
        dataset,
        outputs_by_case_id,
        options=resolved_options,
    )
    return build_risk_eval_report(
        records,
        dataset_version=resolved_options.dataset_version,
        confidence_check_mode=resolved_options.confidence_check_mode,
        confidence_hard_gate=resolved_options.confidence_hard_gate,
        bundle_version=resolved_options.bundle_version,
    )


def run_risk_only_evaluation_with_provider(
    dataset: HealthTriageDataset,
    provider: TriageOutputProvider,
    *,
    options: RiskEvalOptions | None = None,
) -> RiskEvalReport:
    """使用分诊回调执行 risk-only 批跑。

    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param provider: 分诊输出提供回调。
    :type provider: TriageOutputProvider
    :param options: 评测配置。
    :type options: RiskEvalOptions | None
    :returns: risk-only 批跑汇总报告。
    :rtype: RiskEvalReport
    """
    resolved_options = options if options is not None else DEFAULT_RISK_EVAL_OPTIONS
    records = evaluate_all_cases_with_provider(
        dataset,
        provider,
        options=resolved_options,
    )
    return build_risk_eval_report(
        records,
        dataset_version=resolved_options.dataset_version,
        confidence_check_mode=resolved_options.confidence_check_mode,
        confidence_hard_gate=resolved_options.confidence_hard_gate,
        bundle_version=resolved_options.bundle_version,
    )


# ---------------------------------------------------------------------------
# 测试 / 自检辅助
# ---------------------------------------------------------------------------


def make_golden_outputs_from_dataset(
    dataset: HealthTriageDataset,
    *,
    include_confidence: bool = True,
) -> dict[str, dict[str, str]]:
    """从 case ``expected`` 构造 golden stub 输出（用于评测器自检）。

    产出 ``{caseId: {"riskLevel": ..., "confidence": ...?}}``，传入
    ``run_risk_only_evaluation`` 应得到 20/20 passed（在 confidence 策略匹配时）。

    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param include_confidence: 是否在 stub 中包含 ``confidence`` 字段。
    :type include_confidence: bool
    :returns: caseId 到 minimal 输出 dict 的映射。
    :rtype: dict[str, dict[str, str]]
    """
    outputs: dict[str, dict[str, str]] = {}
    for case in dataset.cases:
        payload: dict[str, str] = {"riskLevel": case.expected.risk_level}
        if include_confidence:
            payload["confidence"] = case.expected.confidence
        outputs[case.case_id] = payload
    return outputs


def assert_risk_only_hard_gate(
    report: RiskEvalReport,
    *,
    expected_total: int | None = None,
) -> None:
    """断言 risk-only 硬门槛全绿（供 pytest / CI 使用）。

    :param report: risk-only 批跑报告。
    :type report: RiskEvalReport
    :param expected_total: 期望 case 总数；省略时使用 ``report.total``。
    :type expected_total: int | None
    :raises AssertionError: ``passed`` 未达到 ``expected_total`` 时抛出。
    """
    total = expected_total if expected_total is not None else report.total
    if report.passed != total:
        failed_preview = ", ".join(report.failed_case_ids[:10])
        msg = (
            f"risk-only 硬门槛未全绿：{report.passed}/{total} passed；"
            f"失败 caseId（前 10）：{failed_preview}"
        )
        raise AssertionError(msg)


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def extract_rule_hits_from_payload(
    payload: Mapping[str, Any],
) -> list[str] | None:
    """从输出 dict 抽取 ``ruleHits``（Triage Core 调试字段，非 output_schema 必填）。

    :param payload: Agent 输出 JSON 对象。
    :type payload: collections.abc.Mapping[str, Any]
    :returns: 规则 id 列表；字段缺失或类型非法时返回 ``None``。
    :rtype: list[str] | None
    """
    raw = payload.get("ruleHits")
    if raw is None:
        return None
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return None
    hits: list[str] = []
    for item in raw:
        if isinstance(item, str):
            hits.append(item)
        else:
            return None
    return hits
