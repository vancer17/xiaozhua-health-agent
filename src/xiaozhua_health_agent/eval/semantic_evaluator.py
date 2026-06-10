"""语义评测编排器（WP0 续项）。

串联 FULL schema 校验 → 语料构建 → 四维度语义检查 → ``SemanticEvalResult`` /
``SemanticEvalRecord`` / ``SemanticEvalReport`` 组装。不参与医学裁决。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.eval.case_dataset import (
    DEFAULT_DATASET_VERSION,
    CaseExpected,
    CaseRecord,
    HealthTriageDataset,
)
from xiaozhua_health_agent.eval.forbidden_patterns import merge_forbidden_patterns
from xiaozhua_health_agent.eval.risk_evaluator import (
    ActualOutputPayload,
    OutputsByCaseId,
    TriageOutputProvider,
)
from xiaozhua_health_agent.eval.schema_validator import validate_output
from xiaozhua_health_agent.eval.semantic_checkers import (
    check_forbidden_patterns,
    check_must_mention,
    check_must_not_mention,
    check_safety_notice,
)
from xiaozhua_health_agent.eval.semantic_eval_types import (
    MustMentionHardGateMode,
    MustMentionHardGateModeLiteral,
    SemanticEvalParsedOutput,
    SemanticEvalRecord,
    SemanticEvalReport,
    SemanticEvalResult,
    build_missing_output_semantic_eval_result,
    build_schema_failed_semantic_eval_result,
    build_semantic_eval_record,
    build_semantic_eval_report,
    build_semantic_eval_result,
)
from xiaozhua_health_agent.eval.synonym_map import (
    EMPTY_SYNONYM_MAP,
    SynonymMap,
    load_synonym_map,
)
from xiaozhua_health_agent.eval.text_corpus import (
    CorpusBuildOptions,
    build_corpus_bundle,
)
from xiaozhua_health_agent.eval.validation_result import (
    OutputValidationMode,
    ValidationResult,
)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


class SemanticEvalOptions(BaseModel):
    """语义评测运行配置。

    :param must_mention_hard_gate: mustMention 不匹配是否拉低 ``passed``。
    :param safety_notice_min_length: ``safetyNoticeRequired=true`` 时最小有效长度。
    :param corpus_options: 语料构建配置；省略时使用默认。
    :param forbidden_patterns: 可选禁止 pattern 覆盖列表。
    :param synonym_map_path: 可选 KB-SYN JSON 路径。
    :param must_mention_batch_threshold: 全批 mustMention 软门槛建议线。
    :param bundle_version: 可选 triage-core bundleVersion pin。
    :param dataset_version: mock case 数据集版本。
    """

    model_config = ConfigDict(extra="forbid")

    must_mention_hard_gate: MustMentionHardGateModeLiteral = Field(
        default=MustMentionHardGateMode.SOFT.value,
        description="mustMention 软/硬门槛。",
    )
    safety_notice_min_length: int = Field(
        default=8,
        ge=1,
        description="safetyNotice 最小有效长度。",
    )
    corpus_options: CorpusBuildOptions | None = Field(
        default=None,
        description="语料构建配置；None 表示默认。",
    )
    forbidden_patterns: tuple[str, ...] | None = Field(
        default=None,
        description="可选禁止 pattern 列表；None 表示 schema+默认扩展合并。",
    )
    synonym_map_path: Path | None = Field(
        default=None,
        description="可选 KB-SYN JSON 文件路径。",
    )
    must_mention_batch_threshold: int = Field(
        default=18,
        ge=0,
        description="全批 mustMention 软门槛建议通过数。",
    )
    bundle_version: str | None = Field(
        default=None,
        description="可选 bundleVersion pin。",
    )
    dataset_version: str = Field(
        default=DEFAULT_DATASET_VERSION,
        description="mock case 数据集版本。",
    )


DEFAULT_SEMANTIC_EVAL_OPTIONS: SemanticEvalOptions = SemanticEvalOptions()
"""WP0 语义评测默认配置。"""


FullOutputPayload: TypeAlias = ActualOutputPayload
"""full-output 模式下的 Agent 输出载荷（与 risk 批跑共用别名）。"""


# ---------------------------------------------------------------------------
# 单条评测
# ---------------------------------------------------------------------------


def evaluate_semantic_output(
    *,
    expected: CaseExpected,
    actual_output: FullOutputPayload,
    case_id: str | None = None,
    options: SemanticEvalOptions | None = None,
    primary_flag: str | None = None,
    synonym_map: SynonymMap | None = None,
) -> SemanticEvalResult:
    """对单条输出执行语义评测（FULL schema → 语料 → 四维度检查）。

    :param expected: 来自 ``CaseRecord.expected`` 的验收约束。
    :type expected: CaseExpected
    :param actual_output: Agent 实际输出；``None`` 视为批跑缺输出。
    :type actual_output: FullOutputPayload
    :param case_id: 可选 caseId，写入违规 message。
    :type case_id: str | None
    :param options: 评测配置；省略时使用 ``DEFAULT_SEMANTIC_EVAL_OPTIONS``。
    :type options: SemanticEvalOptions | None
    :param primary_flag: 可选 primaryFlag，供 KB-SYN 细粒度扩展。
    :type primary_flag: str | None
    :param synonym_map: 可选同义词表；省略时按 ``options.synonym_map_path`` 加载。
    :type synonym_map: SynonymMap | None
    :returns: 单条 case 的完整语义评测结果。
    :rtype: SemanticEvalResult
    """
    resolved_options = options if options is not None else DEFAULT_SEMANTIC_EVAL_OPTIONS

    if actual_output is None:
        return build_missing_output_semantic_eval_result(
            must_mention_hard_gate=resolved_options.must_mention_hard_gate,
            case_id=case_id or "unknown",
        )

    schema_check = cast(
        ValidationResult[SemanticEvalParsedOutput],
        validate_output(
            actual_output,
            mode=OutputValidationMode.FULL,
        ),
    )

    if not schema_check.passed or schema_check.parsed is None:
        return build_schema_failed_semantic_eval_result(
            schema_check=schema_check,
            must_mention_hard_gate=resolved_options.must_mention_hard_gate,
            case_id=case_id,
        )

    parsed = schema_check.parsed
    resolved_synonyms = _resolve_synonym_map(
        synonym_map=synonym_map,
        options=resolved_options,
    )
    corpus = build_corpus_bundle(
        parsed,
        options=resolved_options.corpus_options,
    )
    patterns = (
        resolved_options.forbidden_patterns
        if resolved_options.forbidden_patterns is not None
        else merge_forbidden_patterns()
    )

    must_mention = check_must_mention(
        expected=expected,
        corpus=corpus,
        synonym_map=resolved_synonyms,
        primary_flag=primary_flag,
        case_id=case_id,
    )
    must_not_mention = check_must_not_mention(
        expected=expected,
        segments=corpus.segments,
        case_id=case_id,
    )
    forbidden_pattern = check_forbidden_patterns(
        segments=corpus.segments,
        patterns=patterns,
        case_id=case_id,
    )
    safety_notice = check_safety_notice(
        expected=expected,
        output=parsed,
        min_length=resolved_options.safety_notice_min_length,
        case_id=case_id,
    )

    return build_semantic_eval_result(
        schema_check=schema_check,
        must_mention=must_mention,
        must_not_mention=must_not_mention,
        forbidden_pattern=forbidden_pattern,
        safety_notice=safety_notice,
        must_mention_hard_gate=resolved_options.must_mention_hard_gate,
        skipped=False,
    )


def evaluate_semantic_for_case(
    case: CaseRecord,
    actual_output: FullOutputPayload,
    *,
    options: SemanticEvalOptions | None = None,
    primary_flag: str | None = None,
    synonym_map: SynonymMap | None = None,
) -> SemanticEvalRecord:
    """对单条 ``CaseRecord`` 执行语义评测并封装记录。

    :param case: mock case（含 ``input`` 与 ``expected``）。
    :type case: CaseRecord
    :param actual_output: 该 case 的 Agent 实际输出。
    :type actual_output: FullOutputPayload
    :param options: 评测配置。
    :type options: SemanticEvalOptions | None
    :param primary_flag: 可选 primaryFlag。
    :type primary_flag: str | None
    :param synonym_map: 可选同义词表。
    :type synonym_map: SynonymMap | None
    :returns: 带 case 元数据的语义评测记录。
    :rtype: SemanticEvalRecord
    """
    resolved_options = options if options is not None else DEFAULT_SEMANTIC_EVAL_OPTIONS
    result = evaluate_semantic_output(
        expected=case.expected,
        actual_output=actual_output,
        case_id=case.case_id,
        options=resolved_options,
        primary_flag=primary_flag,
        synonym_map=synonym_map,
    )
    return build_semantic_eval_record(
        case_id=case.case_id,
        case_name=case.name,
        result=result,
        primary_flag=primary_flag,
        bundle_version=resolved_options.bundle_version,
    )


def evaluate_all_cases_semantic(
    dataset: HealthTriageDataset,
    outputs_by_case_id: OutputsByCaseId,
    *,
    options: SemanticEvalOptions | None = None,
    primary_flags_by_case_id: Mapping[str, str] | None = None,
    synonym_map: SynonymMap | None = None,
) -> list[SemanticEvalRecord]:
    """对数据集中全部 case 执行语义评测。

    :param dataset: 已加载的 mock case 数据集。
    :type dataset: HealthTriageDataset
    :param outputs_by_case_id: caseId 到实际输出的映射。
    :type outputs_by_case_id: OutputsByCaseId
    :param options: 评测配置。
    :type options: SemanticEvalOptions | None
    :param primary_flags_by_case_id: 可选 caseId → primaryFlag 映射。
    :type primary_flags_by_case_id: collections.abc.Mapping[str, str] | None
    :param synonym_map: 可选同义词表。
    :type synonym_map: SynonymMap | None
    :returns: 与 ``dataset.cases`` 顺序一致的语义评测记录列表。
    :rtype: list[SemanticEvalRecord]
    """
    records: list[SemanticEvalRecord] = []
    for case in dataset.cases:
        actual = outputs_by_case_id.get(case.case_id)
        flag = (
            primary_flags_by_case_id.get(case.case_id)
            if primary_flags_by_case_id is not None
            else None
        )
        records.append(
            evaluate_semantic_for_case(
                case,
                actual,
                options=options,
                primary_flag=flag,
                synonym_map=synonym_map,
            )
        )
    return records


def evaluate_all_cases_semantic_with_provider(
    dataset: HealthTriageDataset,
    provider: TriageOutputProvider,
    *,
    options: SemanticEvalOptions | None = None,
    synonym_map: SynonymMap | None = None,
) -> list[SemanticEvalRecord]:
    """使用分诊回调对全部 case 生成输出并执行语义评测。

    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param provider: 接收 ``case.input``、返回该 case 输出的回调。
    :type provider: TriageOutputProvider
    :param options: 评测配置。
    :type options: SemanticEvalOptions | None
    :param synonym_map: 可选同义词表。
    :type synonym_map: SynonymMap | None
    :returns: 逐条语义评测记录列表。
    :rtype: list[SemanticEvalRecord]
    """
    outputs: dict[str, FullOutputPayload] = {}
    for case in dataset.cases:
        outputs[case.case_id] = provider(case.input)
    return evaluate_all_cases_semantic(
        dataset,
        outputs,
        options=options,
        synonym_map=synonym_map,
    )


def run_semantic_evaluation(
    dataset: HealthTriageDataset,
    outputs_by_case_id: OutputsByCaseId,
    *,
    options: SemanticEvalOptions | None = None,
    synonym_map: SynonymMap | None = None,
) -> SemanticEvalReport:
    """执行完整语义批跑并返回汇总报告。

    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param outputs_by_case_id: caseId → 实际输出映射。
    :type outputs_by_case_id: OutputsByCaseId
    :param options: 评测配置。
    :type options: SemanticEvalOptions | None
    :param synonym_map: 可选同义词表。
    :type synonym_map: SynonymMap | None
    :returns: 语义批跑汇总报告。
    :rtype: SemanticEvalReport
    """
    resolved_options = options if options is not None else DEFAULT_SEMANTIC_EVAL_OPTIONS
    records = evaluate_all_cases_semantic(
        dataset,
        outputs_by_case_id,
        options=resolved_options,
        synonym_map=synonym_map,
    )
    return build_semantic_eval_report(
        records,
        dataset_version=resolved_options.dataset_version,
        must_mention_hard_gate=resolved_options.must_mention_hard_gate,
        must_mention_batch_threshold=resolved_options.must_mention_batch_threshold,
        bundle_version=resolved_options.bundle_version,
    )


def run_semantic_evaluation_with_provider(
    dataset: HealthTriageDataset,
    provider: TriageOutputProvider,
    *,
    options: SemanticEvalOptions | None = None,
    synonym_map: SynonymMap | None = None,
) -> SemanticEvalReport:
    """使用分诊回调执行语义批跑。

    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param provider: 分诊输出提供回调。
    :type provider: TriageOutputProvider
    :param options: 评测配置。
    :type options: SemanticEvalOptions | None
    :param synonym_map: 可选同义词表。
    :type synonym_map: SynonymMap | None
    :returns: 语义批跑汇总报告。
    :rtype: SemanticEvalReport
    """
    resolved_options = options if options is not None else DEFAULT_SEMANTIC_EVAL_OPTIONS
    records = evaluate_all_cases_semantic_with_provider(
        dataset,
        provider,
        options=resolved_options,
        synonym_map=synonym_map,
    )
    return build_semantic_eval_report(
        records,
        dataset_version=resolved_options.dataset_version,
        must_mention_hard_gate=resolved_options.must_mention_hard_gate,
        must_mention_batch_threshold=resolved_options.must_mention_batch_threshold,
        bundle_version=resolved_options.bundle_version,
    )


def assert_semantic_hard_gate(
    report: SemanticEvalReport,
    *,
    expected_total: int | None = None,
) -> None:
    """断言语义评测硬门槛全绿（供 pytest / CI 使用）。

    :param report: 语义批跑报告。
    :type report: SemanticEvalReport
    :param expected_total: 期望 case 总数；省略时使用 ``report.total``。
    :type expected_total: int | None
    :raises AssertionError: ``passed`` 未达到 ``expected_total`` 时抛出。
    """
    total = expected_total if expected_total is not None else report.total
    if report.passed != total:
        failed_preview = ", ".join(report.failed_case_ids[:10])
        msg = (
            f"语义评测硬门槛未全绿：{report.passed}/{total} passed；"
            f"失败 caseId（前 10）：{failed_preview}"
        )
        raise AssertionError(msg)


def extract_primary_flag_from_payload(
    payload: Mapping[str, Any],
) -> str | None:
    """从输出 dict 抽取 ``primaryFlag``（Triage Core 调试字段）。

    :param payload: Agent 输出 JSON 对象。
    :type payload: collections.abc.Mapping[str, Any]
    :returns: primaryFlag 字符串；缺失或类型非法时返回 ``None``。
    :rtype: str | None
    """
    raw = payload.get("primaryFlag")
    if isinstance(raw, str) and raw.strip():
        return raw
    return None


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _resolve_synonym_map(
    *,
    synonym_map: SynonymMap | None,
    options: SemanticEvalOptions,
) -> SynonymMap:
    """解析本次评测使用的同义词表。

    :param synonym_map: 调用方显式传入的同义词表。
    :type synonym_map: SynonymMap | None
    :param options: 语义评测配置。
    :type options: SemanticEvalOptions
    :returns: 非空的 ``SynonymMap`` 实例。
    :rtype: SynonymMap
    """
    if synonym_map is not None:
        return synonym_map
    if options.synonym_map_path is not None:
        return load_synonym_map(options.synonym_map_path)
    return EMPTY_SYNONYM_MAP
