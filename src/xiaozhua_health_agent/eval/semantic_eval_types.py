"""语义评测专用结果类型与组装辅助函数（WP0 续项）。

本模块定义 ``SemanticEvalResult``、``SemanticEvalReport`` 等 DTO，供
``semantic_evaluator`` 与 ``full_evaluator`` 消费。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from xiaozhua_health_agent.eval.case_dataset import DEFAULT_DATASET_VERSION
from xiaozhua_health_agent.eval.schema_validator import OUTPUT_SCHEMA_VERSION
from xiaozhua_health_agent.eval.semantic_violation import (
    make_semantic_eval_skipped_violation,
)
from xiaozhua_health_agent.eval.validation_result import (
    SchemaKind,
    ValidationResult,
    Violation,
    ViolationCode,
)
from xiaozhua_health_agent.schemas import AgentOutput

# ---------------------------------------------------------------------------
# 枚举与 Literal
# ---------------------------------------------------------------------------


class SemanticEvalDimension(StrEnum):
    """语义评测中的单维度标识。"""

    MUST_MENTION = "must_mention"
    MUST_NOT_MENTION = "must_not_mention"
    FORBIDDEN_PATTERN = "forbidden_pattern"
    SAFETY_NOTICE = "safety_notice"


SemanticEvalDimensionLiteral = Literal[
    "must_mention",
    "must_not_mention",
    "forbidden_pattern",
    "safety_notice",
]


class SemanticEvalRunMode(StrEnum):
    """语义批跑模式标识（单模块报告）。"""

    SEMANTIC_ONLY = "semantic-only"


SemanticEvalRunModeLiteral = Literal["semantic-only"]


class MustMentionHardGateMode(StrEnum):
    """mustMention 不匹配是否拉低 ``SemanticEvalResult.passed``。"""

    SOFT = "soft"
    HARD = "hard"


MustMentionHardGateModeLiteral = Literal["soft", "hard"]

SemanticEvalParsedOutput = AgentOutput
"""语义评测中 ``schema_check.parsed`` 允许的强类型（FULL 模式）。"""

# ---------------------------------------------------------------------------
# 维度与单 case 结果
# ---------------------------------------------------------------------------


class SemanticDimensionResult(BaseModel):
    """语义评测中单个比对维度的结果。

    :param dimension: 维度标识。
    :param check_applied: 是否执行了本维度比对。
    :param passed: 比对结论；未执行时为 ``None``。
    :param missing_keywords: mustMention 未命中关键词（仅 must_mention 维度使用）。
    :param violations: 本维度产生的违规项列表。
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    dimension: SemanticEvalDimensionLiteral = Field(
        description="语义比对维度标识。",
    )
    check_applied: bool = Field(
        description="是否执行了本维度比对。",
    )
    passed: bool | None = Field(
        default=None,
        description="维度是否通过；未执行比对时为 null。",
    )
    missing_keywords: list[str] = Field(
        default_factory=list,
        description="mustMention 未命中的关键词列表。",
    )
    violations: list[Violation] = Field(
        default_factory=list,
        description="本维度产生的违规项；通过时为空列表。",
    )


class SemanticEvalResult(BaseModel):
    """单条 case 的语义评测完整结果。

    :param passed: 最终硬门槛是否通过（受 ``must_mention_hard_gate`` 影响）。
    :param hard_passed: 不含 mustMention 软门槛的硬通过标志。
    :param soft_passed: hard 通过且（未检查 mustMention 或 mustMention 通过）。
    :param skipped: 是否因前置条件未执行语义检查。
    :param schema_check: FULL output 结构校验结果。
    :param must_mention: mustMention 维度结果。
    :param must_not_mention: mustNotMention 维度结果。
    :param forbidden_pattern: 禁止 pattern 维度结果。
    :param safety_notice: safetyNotice 维度结果。
    :param violations: 扁平硬违规列表。
    :param warnings: 软门槛警告（默认 mustMention 不匹配）。
    :param must_mention_hard_gate: mustMention 软/硬门槛配置快照。
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    passed: bool = Field(
        description="语义评测硬门槛是否通过。",
    )
    hard_passed: bool = Field(
        description="schema + mustNotMention + forbidden + safetyNotice 硬维度是否通过。",
    )
    soft_passed: bool = Field(
        description="hard 通过且 mustMention 软门槛满足。",
    )
    skipped: bool = Field(
        description="是否因 schema 未通过或缺输出而跳过语义维度检查。",
    )
    schema_check: ValidationResult[SemanticEvalParsedOutput] = Field(
        description="对照完整 ``AgentOutput`` 的 FULL 结构校验结果。",
    )
    must_mention: SemanticDimensionResult = Field(
        description="mustMention 维度比对结果。",
    )
    must_not_mention: SemanticDimensionResult = Field(
        description="mustNotMention 维度比对结果。",
    )
    forbidden_pattern: SemanticDimensionResult = Field(
        description="禁止 pattern 维度比对结果。",
    )
    safety_notice: SemanticDimensionResult = Field(
        description="safetyNotice 维度比对结果。",
    )
    violations: list[Violation] = Field(
        default_factory=list,
        description="扁平汇总的硬违规列表。",
    )
    warnings: list[Violation] = Field(
        default_factory=list,
        description="软门槛警告（mustMention 不匹配且 hard_gate=soft）。",
    )
    must_mention_hard_gate: MustMentionHardGateModeLiteral = Field(
        default="soft",
        description="mustMention 不匹配是否拉低 passed。",
    )

    @model_validator(mode="after")
    def _sync_aggregate_fields(self) -> SemanticEvalResult:
        """校验扁平 ``violations`` / ``warnings`` 与分维度结果一致。

        :returns: 校验通过后的同一实例。
        :rtype: SemanticEvalResult
        """
        expected_violations = flatten_semantic_eval_violations(
            schema_check=self.schema_check,
            must_mention=self.must_mention,
            must_not_mention=self.must_not_mention,
            forbidden_pattern=self.forbidden_pattern,
            safety_notice=self.safety_notice,
            include_warnings_in_violations=self.must_mention_hard_gate == "hard",
        )
        if self.violations != expected_violations:
            msg = (
                "SemanticEvalResult.violations 与分维度结果不一致，"
                "请使用 build_semantic_eval_result 构造。"
            )
            raise ValueError(msg)
        return self


class SemanticEvalRecord(BaseModel):
    """单条 case 的语义评测记录（含报告元数据）。

    :param case_id: case 唯一标识。
    :param case_name: case 中文名称。
    :param result: 语义评测完整结果。
    :param primary_flag: 可选 Triage Core primaryFlag（同义词扩展用）。
    :param bundle_version: 可选 triage-core bundle 版本 pin。
    """

    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True,
        populate_by_name=True,
    )

    case_id: str = Field(alias="caseId", description="case 唯一标识。")
    case_name: str = Field(alias="caseName", description="case 中文名称。")
    result: SemanticEvalResult = Field(description="语义评测结果。")
    primary_flag: str | None = Field(
        default=None,
        alias="primaryFlag",
        description="可选 primaryFlag，供 KB-SYN 细粒度扩展。",
    )
    bundle_version: str | None = Field(
        default=None,
        alias="bundleVersion",
        description="可选 triage-core bundleVersion。",
    )


class SemanticEvalReport(BaseModel):
    """语义评测批跑汇总报告。

    :param mode: 固定 ``semantic-only``。
    :param dataset_version: mock case 数据集版本。
    :param total: 参与评测 case 总数。
    :param passed: 通过硬门槛数量。
    :param failed: 未通过硬门槛数量。
    :param records: 逐条评测记录。
    :param failed_case_ids: 失败 caseId 列表。
    :param schema_passed: FULL schema 通过数。
    :param must_mention_passed: mustMention 维度通过数。
    :param must_not_mention_passed: mustNotMention 维度通过数。
    :param forbidden_pattern_passed: 禁止 pattern 维度通过数。
    :param safety_notice_passed: safetyNotice 维度通过数（仅 required=true 的 case）。
    :param must_mention_hard_gate: mustMention 软/硬门槛配置。
    :param must_mention_batch_threshold: 全批 mustMention 软门槛建议线。
    :param generated_at: 报告生成 UTC 时间。
    :param bundle_version: 可选全局 bundle 版本 pin。
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mode: SemanticEvalRunModeLiteral = Field(
        default="semantic-only",
        description="批跑模式标识。",
    )
    dataset_version: str = Field(
        alias="datasetVersion",
        description="mock case 数据集版本。",
    )
    total: int = Field(description="参与评测的 case 总数。")
    passed: int = Field(description="``SemanticEvalResult.passed`` 为 true 的数量。")
    failed: int = Field(description="未通过硬门槛的 case 数量。")
    records: list[SemanticEvalRecord] = Field(
        description="逐条评测记录。",
    )
    failed_case_ids: list[str] = Field(
        alias="failedCaseIds",
        default_factory=list,
        description="未通过硬门槛的 caseId 列表。",
    )
    schema_passed: int = Field(
        alias="schemaPassed",
        description="FULL output schema 校验通过的数量。",
    )
    must_mention_passed: int = Field(
        alias="mustMentionPassed",
        description="mustMention 维度通过的数量。",
    )
    must_not_mention_passed: int = Field(
        alias="mustNotMentionPassed",
        description="mustNotMention 维度通过的数量。",
    )
    forbidden_pattern_passed: int = Field(
        alias="forbiddenPatternPassed",
        description="禁止 pattern 维度通过的数量。",
    )
    safety_notice_passed: int = Field(
        alias="safetyNoticePassed",
        description="safetyNotice 维度通过的数量（含 check_applied=false 计为通过）。",
    )
    must_mention_hard_gate: MustMentionHardGateModeLiteral = Field(
        alias="mustMentionHardGate",
        default="soft",
        description="mustMention 软/硬门槛配置。",
    )
    must_mention_batch_threshold: int = Field(
        alias="mustMentionBatchThreshold",
        default=18,
        description="全批 mustMention 软门槛建议通过数（里程碑 B）。",
    )
    generated_at: datetime = Field(
        alias="generatedAt",
        description="报告生成时间（UTC）。",
    )
    bundle_version: str | None = Field(
        default=None,
        alias="bundleVersion",
        description="可选全报告级 bundleVersion。",
    )


# ---------------------------------------------------------------------------
# 组装与汇总
# ---------------------------------------------------------------------------


def flatten_semantic_eval_violations(
    *,
    schema_check: ValidationResult[SemanticEvalParsedOutput],
    must_mention: SemanticDimensionResult,
    must_not_mention: SemanticDimensionResult,
    forbidden_pattern: SemanticDimensionResult,
    safety_notice: SemanticDimensionResult,
    include_warnings_in_violations: bool,
) -> list[Violation]:
    """将 schema 与各语义维度违规扁平合并。

    :param schema_check: FULL 结构校验结果。
    :type schema_check: ValidationResult[SemanticEvalParsedOutput]
    :param must_mention: mustMention 维度结果。
    :type must_mention: SemanticDimensionResult
    :param must_not_mention: mustNotMention 维度结果。
    :type must_not_mention: SemanticDimensionResult
    :param forbidden_pattern: 禁止 pattern 维度结果。
    :type forbidden_pattern: SemanticDimensionResult
    :param safety_notice: safetyNotice 维度结果。
    :type safety_notice: SemanticDimensionResult
    :param include_warnings_in_violations: 为 true 时将 mustMention 软警告并入 violations。
    :type include_warnings_in_violations: bool
    :returns: 按 schema → 各语义维度顺序拼接的违规列表。
    :rtype: list[Violation]
    """
    merged: list[Violation] = []
    merged.extend(schema_check.violations)
    if include_warnings_in_violations and must_mention.check_applied:
        merged.extend(must_mention.violations)
    elif must_mention.check_applied and must_mention.passed is False:
        merged.extend(must_mention.violations)
    merged.extend(must_not_mention.violations)
    merged.extend(forbidden_pattern.violations)
    merged.extend(safety_notice.violations)
    return merged


def extract_semantic_eval_warnings(
    must_mention: SemanticDimensionResult,
    *,
    must_mention_hard_gate: MustMentionHardGateModeLiteral,
) -> list[Violation]:
    """从 mustMention 维度提取软门槛警告列表。

    :param must_mention: mustMention 维度比对结果。
    :type must_mention: SemanticDimensionResult
    :param must_mention_hard_gate: mustMention 硬门槛模式。
    :type must_mention_hard_gate: MustMentionHardGateModeLiteral
    :returns: 软门槛下的 mustMention 违规副本；硬门槛或无违规时为空。
    :rtype: list[Violation]
    """
    if must_mention_hard_gate != "soft":
        return []
    if not must_mention.check_applied or must_mention.passed is not False:
        return []
    return list(must_mention.violations)


def compute_semantic_hard_passed(
    *,
    schema_check: ValidationResult[SemanticEvalParsedOutput],
    must_not_mention: SemanticDimensionResult,
    forbidden_pattern: SemanticDimensionResult,
    safety_notice: SemanticDimensionResult,
) -> bool:
    """计算语义硬门槛（不含 mustMention 软项）。

    :param schema_check: FULL 结构校验结果。
    :type schema_check: ValidationResult[SemanticEvalParsedOutput]
    :param must_not_mention: mustNotMention 维度结果。
    :type must_not_mention: SemanticDimensionResult
    :param forbidden_pattern: 禁止 pattern 维度结果。
    :type forbidden_pattern: SemanticDimensionResult
    :param safety_notice: safetyNotice 维度结果。
    :type safety_notice: SemanticDimensionResult
    :returns: schema 与各硬语义维度均通过时为 true。
    :rtype: bool
    """
    if not schema_check.passed:
        return False
    for dimension in (must_not_mention, forbidden_pattern, safety_notice):
        if dimension.check_applied and dimension.passed is not True:
            return False
    return True


def compute_semantic_soft_passed(
    *,
    hard_passed: bool,
    must_mention: SemanticDimensionResult,
) -> bool:
    """在 hard 门槛基础上计算语义软门槛（含 mustMention）。

    :param hard_passed: 语义硬门槛是否已通过。
    :type hard_passed: bool
    :param must_mention: mustMention 维度结果。
    :type must_mention: SemanticDimensionResult
    :returns: hard 为真且（未检查 mustMention 或 mustMention 通过）时为 true。
    :rtype: bool
    """
    if not hard_passed:
        return False
    if not must_mention.check_applied:
        return True
    return must_mention.passed is True


def compute_semantic_eval_passed(
    *,
    hard_passed: bool,
    must_mention: SemanticDimensionResult,
    must_mention_hard_gate: MustMentionHardGateModeLiteral,
) -> bool:
    """在 hard_passed 基础上应用 mustMention 硬门槛策略。

    :param hard_passed: 语义硬门槛是否已通过。
    :type hard_passed: bool
    :param must_mention: mustMention 维度结果。
    :type must_mention: SemanticDimensionResult
    :param must_mention_hard_gate: mustMention 不匹配是否拉低 passed。
    :type must_mention_hard_gate: MustMentionHardGateModeLiteral
    :returns: 最终语义 passed 标志。
    :rtype: bool
    """
    if not hard_passed:
        return False
    if (
        must_mention_hard_gate == "hard"
        and must_mention.check_applied
        and must_mention.passed is False
    ):
        return False
    return True


def build_semantic_eval_result(
    *,
    schema_check: ValidationResult[SemanticEvalParsedOutput],
    must_mention: SemanticDimensionResult,
    must_not_mention: SemanticDimensionResult,
    forbidden_pattern: SemanticDimensionResult,
    safety_notice: SemanticDimensionResult,
    must_mention_hard_gate: MustMentionHardGateMode | MustMentionHardGateModeLiteral = (
        MustMentionHardGateMode.SOFT
    ),
    skipped: bool = False,
) -> SemanticEvalResult:
    """组装单条 case 的 ``SemanticEvalResult`` 并同步扁平违规列表。

    :param schema_check: FULL 结构校验结果。
    :type schema_check: ValidationResult[SemanticEvalParsedOutput]
    :param must_mention: mustMention 维度结果。
    :type must_mention: SemanticDimensionResult
    :param must_not_mention: mustNotMention 维度结果。
    :type must_not_mention: SemanticDimensionResult
    :param forbidden_pattern: 禁止 pattern 维度结果。
    :type forbidden_pattern: SemanticDimensionResult
    :param safety_notice: safetyNotice 维度结果。
    :type safety_notice: SemanticDimensionResult
    :param must_mention_hard_gate: mustMention 软/硬门槛；默认 soft。
    :type must_mention_hard_gate: MustMentionHardGateMode | MustMentionHardGateModeLiteral
    :param skipped: 是否标记为跳过语义检查（schema 失败或缺输出）。
    :type skipped: bool
    :returns: 完整语义评测结果。
    :rtype: SemanticEvalResult
    """
    resolved_gate = _resolve_must_mention_hard_gate(must_mention_hard_gate)
    hard_passed = compute_semantic_hard_passed(
        schema_check=schema_check,
        must_not_mention=must_not_mention,
        forbidden_pattern=forbidden_pattern,
        safety_notice=safety_notice,
    )
    soft_passed = compute_semantic_soft_passed(
        hard_passed=hard_passed,
        must_mention=must_mention,
    )
    passed = compute_semantic_eval_passed(
        hard_passed=hard_passed,
        must_mention=must_mention,
        must_mention_hard_gate=resolved_gate,
    )
    include_mention_in_violations = resolved_gate == "hard"
    violations = flatten_semantic_eval_violations(
        schema_check=schema_check,
        must_mention=must_mention,
        must_not_mention=must_not_mention,
        forbidden_pattern=forbidden_pattern,
        safety_notice=safety_notice,
        include_warnings_in_violations=include_mention_in_violations,
    )
    warnings = extract_semantic_eval_warnings(
        must_mention,
        must_mention_hard_gate=resolved_gate,
    )
    return SemanticEvalResult(
        passed=passed,
        hard_passed=hard_passed,
        soft_passed=soft_passed,
        skipped=skipped,
        schema_check=schema_check,
        must_mention=must_mention,
        must_not_mention=must_not_mention,
        forbidden_pattern=forbidden_pattern,
        safety_notice=safety_notice,
        violations=violations,
        warnings=warnings,
        must_mention_hard_gate=resolved_gate,
    )


def build_semantic_eval_record(
    *,
    case_id: str,
    case_name: str,
    result: SemanticEvalResult,
    primary_flag: str | None = None,
    bundle_version: str | None = None,
) -> SemanticEvalRecord:
    """封装单条 case 语义评测记录。

    :param case_id: case 唯一标识。
    :type case_id: str
    :param case_name: case 中文名称。
    :type case_name: str
    :param result: 语义评测结果。
    :type result: SemanticEvalResult
    :param primary_flag: 可选 primaryFlag。
    :type primary_flag: str | None
    :param bundle_version: 可选 bundle 版本。
    :type bundle_version: str | None
    :returns: 带元数据的语义评测记录。
    :rtype: SemanticEvalRecord
    """
    return SemanticEvalRecord(
        caseId=case_id,
        caseName=case_name,
        result=result,
        primaryFlag=primary_flag,
        bundleVersion=bundle_version,
    )


def summarize_semantic_eval_records(
    records: Sequence[SemanticEvalRecord],
) -> tuple[int, int, int, int, int, int, int]:
    """统计一批 ``SemanticEvalRecord`` 的通过数与分维度匹配数。

    :param records: 评测记录序列。
    :type records: collections.abc.Sequence[SemanticEvalRecord]
    :returns: ``(passed, failed, schema_passed, must_mention_passed,
        must_not_mention_passed, forbidden_pattern_passed, safety_notice_passed)``。
    :rtype: tuple[int, int, int, int, int, int, int]
    """
    total = len(records)
    passed_count = sum(1 for item in records if item.result.passed)
    failed_count = total - passed_count
    schema_passed = sum(1 for item in records if item.result.schema_check.passed)
    must_mention_passed = sum(
        1
        for item in records
        if item.result.must_mention.check_applied
        and item.result.must_mention.passed is True
    )
    must_not_mention_passed = sum(
        1
        for item in records
        if not item.result.must_not_mention.check_applied
        or item.result.must_not_mention.passed is True
    )
    forbidden_pattern_passed = sum(
        1 for item in records if item.result.forbidden_pattern.passed is True
    )
    safety_notice_passed = sum(
        1
        for item in records
        if not item.result.safety_notice.check_applied
        or item.result.safety_notice.passed is True
    )
    return (
        passed_count,
        failed_count,
        schema_passed,
        must_mention_passed,
        must_not_mention_passed,
        forbidden_pattern_passed,
        safety_notice_passed,
    )


def build_semantic_eval_report(
    records: Sequence[SemanticEvalRecord],
    *,
    dataset_version: str = DEFAULT_DATASET_VERSION,
    must_mention_hard_gate: MustMentionHardGateMode | MustMentionHardGateModeLiteral = (
        MustMentionHardGateMode.SOFT
    ),
    must_mention_batch_threshold: int = 18,
    bundle_version: str | None = None,
    generated_at: datetime | None = None,
) -> SemanticEvalReport:
    """由逐条语义评测记录构建批跑汇总报告。

    :param records: 评测记录序列。
    :type records: collections.abc.Sequence[SemanticEvalRecord]
    :param dataset_version: mock case 数据集版本。
    :type dataset_version: str
    :param must_mention_hard_gate: mustMention 软/硬门槛。
    :type must_mention_hard_gate: MustMentionHardGateMode | MustMentionHardGateModeLiteral
    :param must_mention_batch_threshold: 全批 mustMention 软门槛建议线。
    :type must_mention_batch_threshold: int
    :param bundle_version: 可选全报告级 bundle 版本。
    :type bundle_version: str | None
    :param generated_at: 报告时间；省略时为当前 UTC。
    :type generated_at: datetime | None
    :returns: 完整语义批跑报告。
    :rtype: SemanticEvalReport
    """
    resolved_gate = _resolve_must_mention_hard_gate(must_mention_hard_gate)
    record_list = list(records)
    (
        passed_count,
        failed_count,
        schema_passed,
        must_mention_passed,
        must_not_mention_passed,
        forbidden_pattern_passed,
        safety_notice_passed,
    ) = summarize_semantic_eval_records(record_list)
    failed_case_ids = [item.case_id for item in record_list if not item.result.passed]
    timestamp = generated_at if generated_at is not None else datetime.now(tz=UTC)
    return SemanticEvalReport(
        mode=SemanticEvalRunMode.SEMANTIC_ONLY.value,
        datasetVersion=dataset_version,
        total=len(record_list),
        passed=passed_count,
        failed=failed_count,
        records=record_list,
        failedCaseIds=failed_case_ids,
        schemaPassed=schema_passed,
        mustMentionPassed=must_mention_passed,
        mustNotMentionPassed=must_not_mention_passed,
        forbiddenPatternPassed=forbidden_pattern_passed,
        safetyNoticePassed=safety_notice_passed,
        mustMentionHardGate=resolved_gate,
        mustMentionBatchThreshold=must_mention_batch_threshold,
        generatedAt=timestamp,
        bundleVersion=bundle_version,
    )


def make_skipped_semantic_dimensions() -> tuple[
    SemanticDimensionResult,
    SemanticDimensionResult,
    SemanticDimensionResult,
    SemanticDimensionResult,
]:
    """创建四个未执行比对的语义维度占位。

    :returns: ``(must_mention, must_not_mention, forbidden_pattern, safety_notice)`` 元组。
    :rtype: tuple[SemanticDimensionResult, SemanticDimensionResult, SemanticDimensionResult, SemanticDimensionResult]
    """

    def _placeholder(dimension: SemanticEvalDimension) -> SemanticDimensionResult:
        return SemanticDimensionResult(
            dimension=dimension.value,
            check_applied=False,
            passed=None,
            missing_keywords=[],
            violations=[],
        )

    return (
        _placeholder(SemanticEvalDimension.MUST_MENTION),
        _placeholder(SemanticEvalDimension.MUST_NOT_MENTION),
        _placeholder(SemanticEvalDimension.FORBIDDEN_PATTERN),
        _placeholder(SemanticEvalDimension.SAFETY_NOTICE),
    )


def build_schema_failed_semantic_eval_result(
    *,
    schema_check: ValidationResult[SemanticEvalParsedOutput],
    must_mention_hard_gate: MustMentionHardGateMode | MustMentionHardGateModeLiteral = (
        MustMentionHardGateMode.SOFT
    ),
    case_id: str | None = None,
) -> SemanticEvalResult:
    """在 FULL schema 未通过时构造完整失败语义评测结果。

    :param schema_check: 未通过的 FULL 结构校验结果。
    :type schema_check: ValidationResult[SemanticEvalParsedOutput]
    :param must_mention_hard_gate: mustMention 软/硬门槛配置快照。
    :type must_mention_hard_gate: MustMentionHardGateMode | MustMentionHardGateModeLiteral
    :param case_id: 可选 caseId。
    :type case_id: str | None
    :returns: ``skipped=True`` 的语义评测失败结果。
    :rtype: SemanticEvalResult
    """
    must_mention, must_not_mention, forbidden_pattern, safety_notice = (
        make_skipped_semantic_dimensions()
    )
    if not schema_check.passed:
        extended_violations = [
            *schema_check.violations,
            make_semantic_eval_skipped_violation(
                reason="output 未通过 full schema 校验",
                case_id=case_id,
            ),
        ]
        schema_check = schema_check.model_copy(
            update={"violations": extended_violations},
        )

    return build_semantic_eval_result(
        schema_check=schema_check,
        must_mention=must_mention,
        must_not_mention=must_not_mention,
        forbidden_pattern=forbidden_pattern,
        safety_notice=safety_notice,
        must_mention_hard_gate=must_mention_hard_gate,
        skipped=True,
    )


def build_missing_output_semantic_eval_result(
    *,
    must_mention_hard_gate: MustMentionHardGateMode | MustMentionHardGateModeLiteral = (
        MustMentionHardGateMode.SOFT
    ),
    case_id: str = "unknown",
) -> SemanticEvalResult:
    """在批跑缺输出时构造语义评测失败结果。

    :param must_mention_hard_gate: mustMention 软/硬门槛配置快照。
    :type must_mention_hard_gate: MustMentionHardGateMode | MustMentionHardGateModeLiteral
    :param case_id: case 标识，写入跳过说明。
    :type case_id: str
    :returns: ``skipped=True`` 的语义评测失败结果。
    :rtype: SemanticEvalResult
    """
    schema_check = ValidationResult[SemanticEvalParsedOutput](
        passed=False,
        schema_kind=SchemaKind.OUTPUT.value,
        schema_version=OUTPUT_SCHEMA_VERSION,
        mode="full",
        violations=[
            Violation(
                code=ViolationCode.CASE_OUTPUT_MISSING.value,
                domain="semantic_eval",
                path="$",
                field=None,
                message=f"批跑缺少 caseId={case_id!r} 的 Agent 完整输出。",
                severity="HIGH",
            ),
            make_semantic_eval_skipped_violation(
                reason="批跑缺少 Agent 完整输出",
                case_id=case_id,
            ),
        ],
        parsed=None,
    )

    must_mention, must_not_mention, forbidden_pattern, safety_notice = (
        make_skipped_semantic_dimensions()
    )
    return build_semantic_eval_result(
        schema_check=schema_check,
        must_mention=must_mention,
        must_not_mention=must_not_mention,
        forbidden_pattern=forbidden_pattern,
        safety_notice=safety_notice,
        must_mention_hard_gate=must_mention_hard_gate,
        skipped=True,
    )


def iter_semantic_record_violations(
    record: SemanticEvalRecord,
    *,
    include_warnings: bool = False,
) -> list[Violation]:
    """扁平合并单条语义评测记录的全部违规项。

    :param record: 语义评测记录。
    :type record: SemanticEvalRecord
    :param include_warnings: 是否包含软警告。
    :type include_warnings: bool
    :returns: 违规列表副本。
    :rtype: list[Violation]
    """
    items = list(record.result.violations)
    if include_warnings:
        items.extend(record.result.warnings)
    return items


def assert_must_mention_batch_threshold(
    report: SemanticEvalReport,
    *,
    threshold: int | None = None,
) -> None:
    """断言全批 mustMention 软门槛达到建议线（默认 18/20）。

    :param report: 语义或 full-output 批跑报告（读取 ``must_mention_passed``）。
    :type report: SemanticEvalReport
    :param threshold: 期望通过数；省略时使用报告内 ``must_mention_batch_threshold``。
    :type threshold: int | None
    :raises AssertionError: 未达到阈值时抛出。
    """
    resolved_threshold = (
        threshold if threshold is not None else report.must_mention_batch_threshold
    )
    if report.must_mention_passed < resolved_threshold:
        msg = (
            f"mustMention 软门槛未达标：{report.must_mention_passed}/"
            f"{report.total}（期望 >= {resolved_threshold}）"
        )
        raise AssertionError(msg)


def _resolve_must_mention_hard_gate(
    gate: MustMentionHardGateMode | MustMentionHardGateModeLiteral,
) -> MustMentionHardGateModeLiteral:
    """将 mustMention 硬门槛参数规范化为 Literal 字符串。

    :param gate: 枚举或字符串形式的硬门槛模式。
    :type gate: MustMentionHardGateMode | MustMentionHardGateModeLiteral
    :returns: 规范化后的硬门槛字符串。
    :rtype: MustMentionHardGateModeLiteral
    :raises ValueError: 传入未知模式时抛出。
    """
    if isinstance(gate, MustMentionHardGateMode):
        return gate.value
    if gate in ("soft", "hard"):
        return gate
    msg = f"不支持的 mustMention 硬门槛模式：{gate!r}，允许 soft / hard。"
    raise ValueError(msg)
