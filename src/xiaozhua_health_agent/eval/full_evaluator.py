"""full-output 评测编排器（risk + semantic 组合，WP0 续项）。

在单次批跑中同时执行 risk-only 与语义评测，产出 ``FullEvalReport``。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.eval.case_dataset import (
    DEFAULT_DATASET_VERSION,
    CaseRecord,
    HealthTriageDataset,
)
from xiaozhua_health_agent.eval.risk_eval_types import RiskEvalResult
from xiaozhua_health_agent.eval.risk_evaluator import (
    ActualOutputPayload,
    OutputsByCaseId,
    RiskEvalOptions,
    TriageOutputProvider,
    evaluate_risk_for_case,
    extract_rule_hits_from_payload,
)
from xiaozhua_health_agent.schemas import AgentOutput, RiskOnlyOutput
from xiaozhua_health_agent.eval.semantic_eval_types import SemanticEvalResult
from xiaozhua_health_agent.eval.semantic_evaluator import (
    SemanticEvalOptions,
    evaluate_semantic_for_case,
    extract_primary_flag_from_payload,
)
from xiaozhua_health_agent.eval.synonym_map import SynonymMap

# ---------------------------------------------------------------------------
# 枚举与配置
# ---------------------------------------------------------------------------


class FullEvalRunMode(StrEnum):
    """full-output 批跑模式标识。"""

    FULL_OUTPUT = "full-output"


FullEvalRunModeLiteral: TypeAlias = Literal["full-output"]


class FullEvalOptions(BaseModel):
    """full-output 批跑组合配置。

    :param risk: risk-only 评测配置。
    :param semantic: 语义评测配置。
    """

    model_config = ConfigDict(extra="forbid")

    risk: RiskEvalOptions = Field(
        default_factory=RiskEvalOptions,
        description="risk-only 评测配置。",
    )
    semantic: SemanticEvalOptions = Field(
        default_factory=SemanticEvalOptions,
        description="语义评测配置。",
    )


DEFAULT_FULL_EVAL_OPTIONS: FullEvalOptions = FullEvalOptions()
"""full-output 默认组合配置。"""


# ---------------------------------------------------------------------------
# 结果 DTO
# ---------------------------------------------------------------------------


class FullEvalRecord(BaseModel):
    """单条 case 的 full-output 评测记录。

    :param case_id: case 唯一标识。
    :param case_name: case 中文名称。
    :param risk: risk-only 评测结果。
    :param semantic: 语义评测结果。
    :param rule_hits: 可选 ruleHits 摘要。
    :param primary_flag: 可选 primaryFlag。
    :param bundle_version: 可选 bundle 版本 pin。
    """

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
        populate_by_name=True,
    )

    case_id: str = Field(alias="caseId", description="case 唯一标识。")
    case_name: str = Field(alias="caseName", description="case 中文名称。")
    risk: RiskEvalResult = Field(description="risk-only 评测结果。")
    semantic: SemanticEvalResult = Field(description="语义评测结果。")
    rule_hits: list[str] | None = Field(
        default=None,
        description="可选 Triage Core ruleHits 摘要。",
    )
    primary_flag: str | None = Field(
        default=None,
        alias="primaryFlag",
        description="可选 primaryFlag。",
    )
    bundle_version: str | None = Field(
        default=None,
        alias="bundleVersion",
        description="可选 bundleVersion。",
    )

    @property
    def passed(self) -> bool:
        """单条 case 的 full-output 硬门槛是否通过。

        :returns: risk 与 semantic 硬门槛均为 true 时为 true。
        :rtype: bool
        """
        return self.risk.passed and self.semantic.passed


class FullEvalReport(BaseModel):
    """full-output 批跑汇总报告。

    :param mode: 固定 ``full-output``。
    :param dataset_version: mock case 数据集版本。
    :param total: case 总数。
    :param passed: full-output 硬门槛通过数。
    :param failed: 未通过数。
    :param records: 逐条记录。
    :param failed_case_ids: 失败 caseId 列表。
    :param risk_passed: risk 硬门槛通过数。
    :param semantic_passed: 语义硬门槛通过数。
    :param must_mention_passed: mustMention 维度通过数。
    :param must_mention_batch_threshold: mustMention 软门槛建议线。
    :param generated_at: 报告生成 UTC 时间。
    :param bundle_version: 可选 bundle 版本 pin。
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mode: FullEvalRunModeLiteral = Field(
        default="full-output",
        description="批跑模式标识。",
    )
    dataset_version: str = Field(
        alias="datasetVersion",
        description="mock case 数据集版本。",
    )
    total: int = Field(description="参与评测的 case 总数。")
    passed: int = Field(description="risk 与 semantic 硬门槛均通过的数量。")
    failed: int = Field(description="未通过 full-output 硬门槛的数量。")
    records: list[FullEvalRecord] = Field(description="逐条评测记录。")
    failed_case_ids: list[str] = Field(
        alias="failedCaseIds",
        default_factory=list,
        description="未通过 full-output 硬门槛的 caseId 列表。",
    )
    risk_passed: int = Field(
        alias="riskPassed",
        description="risk-only 硬门槛通过数。",
    )
    semantic_passed: int = Field(
        alias="semanticPassed",
        description="语义硬门槛通过数。",
    )
    must_mention_passed: int = Field(
        alias="mustMentionPassed",
        description="mustMention 维度通过数。",
    )
    must_mention_batch_threshold: int = Field(
        alias="mustMentionBatchThreshold",
        default=18,
        description="mustMention 全批软门槛建议线。",
    )
    generated_at: datetime = Field(
        alias="generatedAt",
        description="报告生成时间（UTC）。",
    )
    bundle_version: str | None = Field(
        default=None,
        alias="bundleVersion",
        description="可选 bundleVersion。",
    )


# ---------------------------------------------------------------------------
# 单条与批量评测
# ---------------------------------------------------------------------------


def evaluate_full_for_case(
    case: CaseRecord,
    actual_output: ActualOutputPayload,
    *,
    options: FullEvalOptions | None = None,
    rule_hits: list[str] | None = None,
    primary_flag: str | None = None,
    synonym_map: SynonymMap | None = None,
) -> FullEvalRecord:
    """对单条 case 执行 full-output 评测（risk + semantic）。

    :param case: mock case。
    :type case: CaseRecord
    :param actual_output: Agent 实际输出。
    :type actual_output: ActualOutputPayload
    :param options: 组合评测配置。
    :type options: FullEvalOptions | None
    :param rule_hits: 可选 ruleHits。
    :type rule_hits: list[str] | None
    :param primary_flag: 可选 primaryFlag。
    :type primary_flag: str | None
    :param synonym_map: 可选同义词表。
    :type synonym_map: SynonymMap | None
    :returns: full-output 单条记录。
    :rtype: FullEvalRecord
    """
    resolved_options = options if options is not None else DEFAULT_FULL_EVAL_OPTIONS
    resolved_rule_hits = rule_hits
    resolved_primary_flag = primary_flag

    if isinstance(actual_output, Mapping):
        if resolved_rule_hits is None:
            resolved_rule_hits = extract_rule_hits_from_payload(actual_output)
        if resolved_primary_flag is None:
            resolved_primary_flag = extract_primary_flag_from_payload(actual_output)

    risk_record = evaluate_risk_for_case(
        case,
        _minimal_risk_payload_from_output(actual_output),
        options=resolved_options.risk,
        rule_hits=resolved_rule_hits,
    )
    semantic_record = evaluate_semantic_for_case(
        case,
        actual_output,
        options=resolved_options.semantic,
        primary_flag=resolved_primary_flag,
        synonym_map=synonym_map,
    )

    bundle_version = (
        resolved_options.risk.bundle_version or resolved_options.semantic.bundle_version
    )

    return FullEvalRecord(
        caseId=case.case_id,
        caseName=case.name,
        risk=risk_record.result,
        semantic=semantic_record.result,
        rule_hits=resolved_rule_hits,
        primaryFlag=resolved_primary_flag,
        bundleVersion=bundle_version,
    )


def evaluate_all_cases_full(
    dataset: HealthTriageDataset,
    outputs_by_case_id: OutputsByCaseId,
    *,
    options: FullEvalOptions | None = None,
    synonym_map: SynonymMap | None = None,
) -> list[FullEvalRecord]:
    """对数据集中全部 case 执行 full-output 评测。

    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param outputs_by_case_id: caseId → 输出映射。
    :type outputs_by_case_id: OutputsByCaseId
    :param options: 组合评测配置。
    :type options: FullEvalOptions | None
    :param synonym_map: 可选同义词表。
    :type synonym_map: SynonymMap | None
    :returns: 与数据集顺序一致的 full-output 记录列表。
    :rtype: list[FullEvalRecord]
    """
    records: list[FullEvalRecord] = []
    for case in dataset.cases:
        actual = outputs_by_case_id.get(case.case_id)
        records.append(
            evaluate_full_for_case(
                case,
                actual,
                options=options,
                synonym_map=synonym_map,
            )
        )
    return records


def evaluate_all_cases_full_with_provider(
    dataset: HealthTriageDataset,
    provider: TriageOutputProvider,
    *,
    options: FullEvalOptions | None = None,
    synonym_map: SynonymMap | None = None,
) -> list[FullEvalRecord]:
    """使用分诊回调对全部 case 生成输出并执行 full-output 评测。

    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param provider: 分诊输出回调。
    :type provider: TriageOutputProvider
    :param options: 组合评测配置。
    :type options: FullEvalOptions | None
    :param synonym_map: 可选同义词表。
    :type synonym_map: SynonymMap | None
    :returns: full-output 记录列表。
    :rtype: list[FullEvalRecord]
    """
    outputs: dict[str, ActualOutputPayload] = {}
    for case in dataset.cases:
        outputs[case.case_id] = provider(case.input)
    return evaluate_all_cases_full(
        dataset,
        outputs,
        options=options,
        synonym_map=synonym_map,
    )


def build_full_eval_report(
    records: Sequence[FullEvalRecord],
    *,
    dataset_version: str = DEFAULT_DATASET_VERSION,
    must_mention_batch_threshold: int = 18,
    bundle_version: str | None = None,
    generated_at: datetime | None = None,
) -> FullEvalReport:
    """由 full-output 记录列表构建汇总报告。

    :param records: 评测记录序列。
    :type records: collections.abc.Sequence[FullEvalRecord]
    :param dataset_version: mock case 数据集版本。
    :type dataset_version: str
    :param must_mention_batch_threshold: mustMention 软门槛建议线。
    :type must_mention_batch_threshold: int
    :param bundle_version: 可选 bundle 版本。
    :type bundle_version: str | None
    :param generated_at: 报告时间；省略时为当前 UTC。
    :type generated_at: datetime | None
    :returns: full-output 批跑汇总报告。
    :rtype: FullEvalReport
    """
    record_list = list(records)
    total = len(record_list)
    passed_count = sum(1 for item in record_list if item.passed)
    failed_count = total - passed_count
    risk_passed = sum(1 for item in record_list if item.risk.passed)
    semantic_passed = sum(1 for item in record_list if item.semantic.passed)
    must_mention_passed = sum(
        1
        for item in record_list
        if item.semantic.must_mention.check_applied
        and item.semantic.must_mention.passed is True
    )
    failed_case_ids = [item.case_id for item in record_list if not item.passed]
    timestamp = generated_at if generated_at is not None else datetime.now(tz=UTC)

    return FullEvalReport(
        mode=FullEvalRunMode.FULL_OUTPUT.value,
        datasetVersion=dataset_version,
        total=total,
        passed=passed_count,
        failed=failed_count,
        records=record_list,
        failedCaseIds=failed_case_ids,
        riskPassed=risk_passed,
        semanticPassed=semantic_passed,
        mustMentionPassed=must_mention_passed,
        mustMentionBatchThreshold=must_mention_batch_threshold,
        generatedAt=timestamp,
        bundleVersion=bundle_version,
    )


def run_full_output_evaluation(
    dataset: HealthTriageDataset,
    outputs_by_case_id: OutputsByCaseId,
    *,
    options: FullEvalOptions | None = None,
    synonym_map: SynonymMap | None = None,
) -> FullEvalReport:
    """执行 full-output 批跑（risk + semantic）。

    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param outputs_by_case_id: caseId → 输出映射。
    :type outputs_by_case_id: OutputsByCaseId
    :param options: 组合评测配置。
    :type options: FullEvalOptions | None
    :param synonym_map: 可选同义词表。
    :type synonym_map: SynonymMap | None
    :returns: full-output 汇总报告。
    :rtype: FullEvalReport
    """
    resolved_options = options if options is not None else DEFAULT_FULL_EVAL_OPTIONS
    records = evaluate_all_cases_full(
        dataset,
        outputs_by_case_id,
        options=resolved_options,
        synonym_map=synonym_map,
    )
    bundle_version = (
        resolved_options.risk.bundle_version or resolved_options.semantic.bundle_version
    )
    return build_full_eval_report(
        records,
        dataset_version=resolved_options.risk.dataset_version,
        must_mention_batch_threshold=(
            resolved_options.semantic.must_mention_batch_threshold
        ),
        bundle_version=bundle_version,
    )


def run_full_output_evaluation_with_provider(
    dataset: HealthTriageDataset,
    provider: TriageOutputProvider,
    *,
    options: FullEvalOptions | None = None,
    synonym_map: SynonymMap | None = None,
) -> FullEvalReport:
    """使用分诊回调执行 full-output 批跑。

    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param provider: 分诊输出回调。
    :type provider: TriageOutputProvider
    :param options: 组合评测配置。
    :type options: FullEvalOptions | None
    :param synonym_map: 可选同义词表。
    :type synonym_map: SynonymMap | None
    :returns: full-output 汇总报告。
    :rtype: FullEvalReport
    """
    resolved_options = options if options is not None else DEFAULT_FULL_EVAL_OPTIONS
    records = evaluate_all_cases_full_with_provider(
        dataset,
        provider,
        options=resolved_options,
        synonym_map=synonym_map,
    )
    bundle_version = (
        resolved_options.risk.bundle_version or resolved_options.semantic.bundle_version
    )
    return build_full_eval_report(
        records,
        dataset_version=resolved_options.risk.dataset_version,
        must_mention_batch_threshold=(
            resolved_options.semantic.must_mention_batch_threshold
        ),
        bundle_version=bundle_version,
    )


def assert_full_output_hard_gate(
    report: FullEvalReport,
    *,
    expected_total: int | None = None,
) -> None:
    """断言 full-output 硬门槛全绿（risk + semantic）。

    :param report: full-output 批跑报告。
    :type report: FullEvalReport
    :param expected_total: 期望 case 总数；省略时使用 ``report.total``。
    :type expected_total: int | None
    :raises AssertionError: 未达到全绿时抛出。
    """
    total = expected_total if expected_total is not None else report.total
    if report.passed != total:
        failed_preview = ", ".join(report.failed_case_ids[:10])
        msg = (
            f"full-output 硬门槛未全绿：{report.passed}/{total} passed；"
            f"失败 caseId（前 10）：{failed_preview}"
        )
        raise AssertionError(msg)


def assert_full_output_soft_gates(
    report: FullEvalReport,
    *,
    must_mention_threshold: int | None = None,
) -> None:
    """断言 full-output 软门槛（mustMention 批级建议线）。

    :param report: full-output 批跑报告。
    :type report: FullEvalReport
    :param must_mention_threshold: 期望 mustMention 通过数；省略时使用报告内阈值。
    :type must_mention_threshold: int | None
    :raises AssertionError: 软门槛未达标时抛出。
    """
    threshold = (
        must_mention_threshold
        if must_mention_threshold is not None
        else report.must_mention_batch_threshold
    )
    if report.must_mention_passed < threshold:
        msg = (
            f"mustMention 软门槛未达标：{report.must_mention_passed}/"
            f"{report.total}（期望 >= {threshold}）"
        )
        raise AssertionError(msg)


def _minimal_risk_payload_from_output(
    actual_output: ActualOutputPayload,
) -> ActualOutputPayload:
    """从 full ``AgentOutput`` 载荷提取 risk-only 评测用 minimal 子集。

    ``validate_output(MINIMAL)`` 对含文案字段的 dict 会报 ``EXTRA_FIELD``；
    full-output 路径在 risk 维度仅比对 ``riskLevel`` / ``confidence``。

    :param actual_output: 原始输出载荷。
    :type actual_output: ActualOutputPayload
    :returns: ``RiskOnlyOutput``、minimal dict 或原样返回。
    :rtype: ActualOutputPayload
    """
    if actual_output is None or isinstance(actual_output, RiskOnlyOutput):
        return actual_output

    if isinstance(actual_output, AgentOutput):
        return RiskOnlyOutput.model_validate(
            {
                "riskLevel": actual_output.risk_level,
                "confidence": actual_output.confidence,
                "scene": actual_output.scene,
            }
        )

    if isinstance(actual_output, Mapping):
        if "title" not in actual_output and "summary" not in actual_output:
            return actual_output
        minimal: dict[str, Any] = {
            "riskLevel": actual_output.get("riskLevel"),
        }
        if "confidence" in actual_output:
            minimal["confidence"] = actual_output.get("confidence")
        if "scene" in actual_output:
            minimal["scene"] = actual_output.get("scene")
        return minimal

    return actual_output


def make_golden_full_outputs_from_dataset(
    dataset: HealthTriageDataset,
) -> dict[str, dict[str, Any]]:
    """从 case ``expected`` 构造 full-output golden stub（评测器自检用）。

    产出满足 FULL ``AgentOutput`` 的最小合法 dict，并在 ``summary`` 中嵌入
    全部 ``mustMention`` 关键词；``mustNotMention`` 与禁止词不包含。

    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :returns: caseId → full output dict 映射。
    :rtype: dict[str, dict[str, Any]]
    """
    outputs: dict[str, dict[str, Any]] = {}
    for case in dataset.cases:
        expected = case.expected
        mention_text = " ".join(expected.must_mention)
        safety_notice = (
            "本内容仅供参考，不能替代兽医诊断与治疗方案，如有疑虑请及时联系兽医。"
            if expected.safety_notice_required
            else "本内容仅供参考，不能替代兽医诊断。"
        )
        outputs[case.case_id] = {
            "riskLevel": expected.risk_level,
            "scene": "health_triage",
            "title": f"{case.name}评估",
            "summary": f"基于当前观测，建议关注以下方面：{mention_text}。",
            "evidence": ["基于当次输入的可核对事实。"],
            "recommendation": "请按建议观察或联系兽医。",
            "whenToSeeVet": "若症状加重或出现新症状，请尽快就医。",
            "missingData": [],
            "confidence": expected.confidence,
            "safetyNotice": safety_notice,
            "primaryAction": {"label": "查看详情", "route": None},
        }
    return outputs
