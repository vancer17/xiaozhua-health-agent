"""批跑入口与文本报告格式化（WP0）。

支持 ``risk-only`` 与 ``full-output`` 两种运行模式及可选 CLI。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, TextIO, TypeAlias, cast

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.eval.case_dataset import (
    HealthTriageDataset,
    load_health_triage_dataset,
)
from xiaozhua_health_agent.eval.risk_eval_types import (
    RiskEvalRecord,
    RiskEvalReport,
    count_violations_by_code,
    iter_all_record_violations,
)
from xiaozhua_health_agent.eval.full_evaluator import (
    FullEvalOptions,
    FullEvalRecord,
    FullEvalReport,
    assert_full_output_hard_gate,
    make_golden_full_outputs_from_dataset,
    run_full_output_evaluation,
    run_full_output_evaluation_with_provider,
)
from xiaozhua_health_agent.eval.risk_evaluator import (
    ActualOutputPayload,
    OutputsByCaseId,
    RiskEvalOptions,
    TriageOutputProvider,
    assert_risk_only_hard_gate,
    make_golden_outputs_from_dataset,
    run_risk_only_evaluation,
)
from xiaozhua_health_agent.eval.copy_llm_batch import (
    CopyLlmBatchConfig,
    CopyLlmBatchReport,
    assert_copy_llm_hard_gate,
    copy_llm_report_to_dict,
    run_copy_llm_batch,
    write_copy_llm_batch_report,
)
from xiaozhua_health_agent.eval.semantic_evaluator import SemanticEvalOptions
from xiaozhua_health_agent.paths import default_cases_path

# ---------------------------------------------------------------------------
# 运行模式
# ---------------------------------------------------------------------------


class BatchRunMode(StrEnum):
    """批跑运行模式。"""

    RISK_ONLY = "risk-only"
    FULL_OUTPUT = "full-output"
    COPY_LLM = "copy-llm"


BatchRunModeLiteral: TypeAlias = Literal["risk-only", "full-output", "copy-llm"]


class BatchRunConfig(BaseModel):
    """批跑 CLI / 脚本配置。

    :param mode: 运行模式（``risk-only`` / ``full-output`` / ``copy-llm``）。
    :param cases_path: mock case JSON 文件路径。
    :param outputs_json_path: 可选；预置输出映射 JSON（caseId → output dict）。
    :param use_golden_outputs: 为 true 时用 expected 构造 golden stub（评测器自检）。
    :param eval_options: risk-only 评测细项配置（``risk-only`` 模式使用）。
    :param full_eval_options: full-output 组合评测配置（``full-output`` 模式使用）。
    :param include_warnings_in_report: 文本报告是否列出软警告段。
    """

    model_config = ConfigDict(extra="forbid")

    mode: BatchRunModeLiteral = Field(
        default=BatchRunMode.RISK_ONLY.value,
        description="批跑模式：risk-only、full-output 或 copy-llm。",
    )
    cases_path: Path | None = Field(
        default=None,
        description="case 文件路径；省略时使用 ``default_cases_path()``。",
    )
    outputs_json_path: Path | None = Field(
        default=None,
        description="可选；caseId → output 的 JSON 文件路径。",
    )
    use_golden_outputs: bool = Field(
        default=False,
        description="为 true 时忽略 outputs 文件，用 expected 构造 golden stub。",
    )
    eval_options: RiskEvalOptions = Field(
        default_factory=RiskEvalOptions,
        description="risk-only 评测配置。",
    )
    full_eval_options: FullEvalOptions = Field(
        default_factory=FullEvalOptions,
        description="full-output 组合评测配置。",
    )
    include_warnings_in_report: bool = Field(
        default=True,
        description="文本报告是否附加软警告段（confidence / mustMention）。",
    )
    copy_llm_scope: Literal["smoke", "full"] = Field(
        default="smoke",
        description="copy-llm 模式范围：smoke（5 边界 case）或 full（20 case）。",
    )
    copy_llm_skip_llm: bool = Field(
        default=False,
        description="copy-llm 模式是否跳过通义调用（仅管道自检）。",
    )
    copy_llm_max_concurrency: int = Field(
        default=3,
        ge=1,
        le=20,
        description="copy-llm 并发上限。",
    )


# ---------------------------------------------------------------------------
# 输出加载
# ---------------------------------------------------------------------------


def load_outputs_from_json(
    path: Path, *, encoding: str = "utf-8"
) -> dict[str, ActualOutputPayload]:
    """从 JSON 文件加载 caseId → 输出映射。

    文件顶层必须为 JSON 对象，键为 caseId，值为 output 对象或 ``null``。

    :param path: JSON 文件路径。
    :type path: pathlib.Path
    :param encoding: 文件编码。
    :type encoding: str
    :returns: caseId 到输出载荷的映射。
    :rtype: dict[str, ActualOutputPayload]
    :raises ValueError: 根节点非对象或值类型非法时抛出。
    :raises OSError: 文件读取失败时抛出。
    """
    text = path.read_text(encoding=encoding)
    payload: Any = json.loads(text)
    if not isinstance(payload, Mapping):
        msg = f"outputs JSON 根节点必须为对象，实际为 {type(payload).__name__}"
        raise ValueError(msg)

    outputs: dict[str, ActualOutputPayload] = {}
    for case_id, value in payload.items():
        if not isinstance(case_id, str):
            msg = f"outputs JSON 键必须为字符串 caseId，实际为 {type(case_id).__name__}"
            raise ValueError(msg)
        if value is None:
            outputs[case_id] = None
        elif isinstance(value, Mapping):
            outputs[case_id] = dict(value)
        else:
            msg = (
                f"caseId={case_id!r} 的输出必须为对象或 null，"
                f"实际为 {type(value).__name__}"
            )
            raise ValueError(msg)
    return outputs


# ---------------------------------------------------------------------------
# 批跑编排
# ---------------------------------------------------------------------------


def run_batch(
    config: BatchRunConfig,
    *,
    provider: TriageOutputProvider | None = None,
    dataset: HealthTriageDataset | None = None,
    outputs_by_case_id: OutputsByCaseId | None = None,
) -> RiskEvalReport | FullEvalReport | CopyLlmBatchReport:
    """按配置执行批跑（``risk-only`` / ``full-output`` / ``copy-llm``）。

    输出来源优先级：

    1. 显式传入 ``outputs_by_case_id``
    2. 显式传入 ``provider``（对每个 ``case.input`` 调用）
    3. ``config.outputs_json_path``
    4. ``config.use_golden_outputs=True``
    5. 否则视为全部缺输出

    :param config: 批跑配置。
    :type config: BatchRunConfig
    :param provider: 可选分诊输出回调。
    :type provider: TriageOutputProvider | None
    :param dataset: 可选已加载数据集；省略时从 ``config.cases_path`` 加载。
    :type dataset: HealthTriageDataset | None
    :param outputs_by_case_id: 可选显式输出映射。
    :type outputs_by_case_id: OutputsByCaseId | None
    :returns: risk-only、full-output 或 copy-llm 批跑报告。
    :rtype: RiskEvalReport | FullEvalReport | CopyLlmBatchReport
    """
    resolved_dataset = _resolve_batch_dataset(config, dataset)

    if config.mode == BatchRunMode.COPY_LLM.value:
        return _run_copy_llm_batch(config, resolved_dataset)

    if config.mode == BatchRunMode.FULL_OUTPUT.value:
        return _run_full_output_batch(
            config,
            resolved_dataset,
            provider=provider,
            outputs_by_case_id=outputs_by_case_id,
        )

    return _run_risk_only_batch(
        config,
        resolved_dataset,
        provider=provider,
        outputs_by_case_id=outputs_by_case_id,
    )


def _resolve_batch_dataset(
    config: BatchRunConfig,
    dataset: HealthTriageDataset | None,
) -> HealthTriageDataset:
    """解析批跑使用的 mock case 数据集。

    :param config: 批跑配置。
    :type config: BatchRunConfig
    :param dataset: 可选已加载数据集。
    :type dataset: HealthTriageDataset | None
    :returns: 非空数据集实例。
    :rtype: HealthTriageDataset
    """
    if dataset is not None:
        return dataset
    cases_path = (
        config.cases_path if config.cases_path is not None else default_cases_path()
    )
    return load_health_triage_dataset(cases_path)


def _run_copy_llm_batch(
    config: BatchRunConfig,
    dataset: HealthTriageDataset,
) -> CopyLlmBatchReport:
    """执行 ``copy-llm`` 批跑分支。

    :param config: 批跑配置。
    :type config: BatchRunConfig
    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :returns: copy-llm 批跑报告。
    :rtype: CopyLlmBatchReport
    """
    copy_config = CopyLlmBatchConfig(
        mode=config.copy_llm_scope,
        cases_path=config.cases_path,
        skip_llm=config.copy_llm_skip_llm,
        max_concurrency=config.copy_llm_max_concurrency,
    )
    return run_copy_llm_batch(copy_config, dataset=dataset)


def _run_risk_only_batch(
    config: BatchRunConfig,
    dataset: HealthTriageDataset,
    *,
    provider: TriageOutputProvider | None,
    outputs_by_case_id: OutputsByCaseId | None,
) -> RiskEvalReport:
    """执行 ``risk-only`` 批跑分支。

    :param config: 批跑配置。
    :type config: BatchRunConfig
    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param provider: 可选分诊输出回调。
    :type provider: TriageOutputProvider | None
    :param outputs_by_case_id: 可选显式输出映射。
    :type outputs_by_case_id: OutputsByCaseId | None
    :returns: risk-only 批跑报告。
    :rtype: RiskEvalReport
    """
    resolved_outputs = _resolve_batch_outputs(
        config,
        dataset,
        provider=provider,
        outputs_by_case_id=outputs_by_case_id,
        golden_mode="risk",
        include_confidence_for_golden=(
            config.eval_options.confidence_check_mode != "off"
        ),
    )
    return run_risk_only_evaluation(
        dataset,
        resolved_outputs,
        options=config.eval_options,
    )


def _run_full_output_batch(
    config: BatchRunConfig,
    dataset: HealthTriageDataset,
    *,
    provider: TriageOutputProvider | None,
    outputs_by_case_id: OutputsByCaseId | None,
) -> FullEvalReport:
    """执行 ``full-output`` 批跑分支。

    :param config: 批跑配置。
    :type config: BatchRunConfig
    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param provider: 可选分诊输出回调。
    :type provider: TriageOutputProvider | None
    :param outputs_by_case_id: 可选显式输出映射。
    :type outputs_by_case_id: OutputsByCaseId | None
    :returns: full-output 批跑报告。
    :rtype: FullEvalReport
    """
    if provider is not None:
        return run_full_output_evaluation_with_provider(
            dataset,
            provider,
            options=config.full_eval_options,
        )

    resolved_outputs = _resolve_batch_outputs(
        config,
        dataset,
        provider=None,
        outputs_by_case_id=outputs_by_case_id,
        golden_mode="full",
        include_confidence_for_golden=True,
    )
    return run_full_output_evaluation(
        dataset,
        resolved_outputs,
        options=config.full_eval_options,
    )


def _resolve_batch_outputs(
    config: BatchRunConfig,
    dataset: HealthTriageDataset,
    *,
    provider: TriageOutputProvider | None,
    outputs_by_case_id: OutputsByCaseId | None,
    golden_mode: Literal["risk", "full"],
    include_confidence_for_golden: bool,
) -> dict[str, ActualOutputPayload]:
    """按优先级解析批跑输出来源。

    :param config: 批跑配置。
    :type config: BatchRunConfig
    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param provider: 可选分诊输出回调。
    :type provider: TriageOutputProvider | None
    :param outputs_by_case_id: 可选显式输出映射。
    :type outputs_by_case_id: OutputsByCaseId | None
    :param golden_mode: golden stub 类型（risk minimal / full output）。
    :type golden_mode: Literal['risk', 'full']
    :param include_confidence_for_golden: risk-only golden 是否包含 confidence。
    :type include_confidence_for_golden: bool
    :returns: caseId → 输出载荷映射。
    :rtype: dict[str, ActualOutputPayload]
    """
    if outputs_by_case_id is not None:
        return dict(outputs_by_case_id)

    if provider is not None:
        generated: dict[str, ActualOutputPayload] = {}
        for case in dataset.cases:
            generated[case.case_id] = provider(case.input)
        return generated

    if config.use_golden_outputs:
        if golden_mode == "full":
            return cast(
                dict[str, ActualOutputPayload],
                make_golden_full_outputs_from_dataset(dataset),
            )
        return cast(
            dict[str, ActualOutputPayload],
            make_golden_outputs_from_dataset(
                dataset,
                include_confidence=include_confidence_for_golden,
            ),
        )

    if config.outputs_json_path is not None:
        return load_outputs_from_json(config.outputs_json_path)

    return {}


# ---------------------------------------------------------------------------
# 文本报告
# ---------------------------------------------------------------------------


def format_risk_eval_record_line(record: RiskEvalRecord) -> str:
    """格式化单条 case 评测为一行摘要。

    :param record: 单条评测记录。
    :type record: RiskEvalRecord
    :returns: 人类可读一行文本。
    :rtype: str
    """
    status = "PASS" if record.result.passed else "FAIL"
    expected_risk = record.result.risk.expected
    actual_risk = record.result.risk.actual
    parts = [
        f"[{status}]",
        record.case_id,
        f"({record.case_name})",
        f"risk: expected={expected_risk!r} actual={actual_risk!r}",
    ]
    if record.result.confidence.check_applied:
        parts.append(
            "confidence: "
            f"expected={record.result.confidence.expected!r} "
            f"actual={record.result.confidence.actual!r}"
        )
    if record.rule_hits:
        hits_preview = ",".join(record.rule_hits[:5])
        parts.append(f"ruleHits=[{hits_preview}]")
    if not record.result.passed and record.result.violations:
        first = record.result.violations[0]
        parts.append(f"reason={first.code}: {first.message}")
    return " ".join(parts)


def format_risk_eval_report_summary(report: RiskEvalReport) -> str:
    """格式化批跑报告头部汇总段。

    :param report: risk-only 批跑报告。
    :type report: RiskEvalReport
    :returns: 多行汇总文本。
    :rtype: str
    """
    lines = [
        f"mode={report.mode}",
        f"datasetVersion={report.dataset_version}",
        f"total={report.total} passed={report.passed} failed={report.failed}",
        f"schemaPassed={report.schema_passed} riskMatched={report.risk_matched}",
    ]
    if report.confidence_matched is not None:
        lines.append(f"confidenceMatched={report.confidence_matched}")
    lines.append(f"confidenceCheckMode={report.confidence_check_mode}")
    lines.append(f"confidenceHardGate={report.confidence_hard_gate}")
    if report.bundle_version is not None:
        lines.append(f"bundleVersion={report.bundle_version}")
    if report.failed_case_ids:
        lines.append(f"failedCaseIds={report.failed_case_ids}")
    violation_counts = count_violations_by_code(
        iter_all_record_violations(report.records, include_warnings=False),
    )
    if violation_counts:
        codes = ", ".join(
            f"{code}={count}" for code, count in sorted(violation_counts.items())
        )
        lines.append(f"violationCounts: {codes}")
    return "\n".join(lines)


def format_risk_eval_report(
    report: RiskEvalReport,
    *,
    include_per_case: bool = True,
    include_warnings: bool = True,
) -> str:
    """格式化完整 risk-only 文本报告。

    :param report: 批跑报告。
    :type report: RiskEvalReport
    :param include_per_case: 是否包含逐 case 行。
    :type include_per_case: bool
    :param include_warnings: 是否附加 confidence 软警告段。
    :type include_warnings: bool
    :returns: 完整多行报告文本。
    :rtype: str
    """
    sections: list[str] = [format_risk_eval_report_summary(report), ""]

    if include_per_case:
        sections.append("--- per case ---")
        for record in report.records:
            sections.append(format_risk_eval_record_line(record))
        sections.append("")

    if include_warnings:
        warning_lines: list[str] = []
        for record in report.records:
            for warning in record.result.warnings:
                warning_lines.append(
                    f"{record.case_id}: [{warning.code}] {warning.message}"
                )
        if warning_lines:
            sections.append("--- warnings (soft) ---")
            sections.extend(warning_lines)
            sections.append("")

    return "\n".join(sections).rstrip() + "\n"


def format_full_eval_record_line(record: FullEvalRecord) -> str:
    """格式化单条 full-output 评测为一行摘要。

    :param record: 单条 full-output 记录。
    :type record: FullEvalRecord
    :returns: 人类可读一行文本。
    :rtype: str
    """
    status = "PASS" if record.passed else "FAIL"
    parts = [
        f"[{status}]",
        record.case_id,
        f"({record.case_name})",
        f"risk={'PASS' if record.risk.passed else 'FAIL'}",
        f"semantic={'PASS' if record.semantic.passed else 'FAIL'}",
        (f"mustMention={'PASS' if record.semantic.must_mention.passed else 'FAIL'}"),
    ]
    if not record.passed:
        combined = [*record.risk.violations, *record.semantic.violations]
        if combined:
            first = combined[0]
            parts.append(f"reason={first.code}: {first.message}")
    return " ".join(parts)


def format_full_eval_report_summary(report: FullEvalReport) -> str:
    """格式化 full-output 批跑报告头部汇总段。

    :param report: full-output 批跑报告。
    :type report: FullEvalReport
    :returns: 多行汇总文本。
    :rtype: str
    """
    lines = [
        f"mode={report.mode}",
        f"datasetVersion={report.dataset_version}",
        f"total={report.total} passed={report.passed} failed={report.failed}",
        f"riskPassed={report.risk_passed} semanticPassed={report.semantic_passed}",
        (
            "mustMentionPassed="
            f"{report.must_mention_passed} "
            f"(threshold>={report.must_mention_batch_threshold})"
        ),
    ]
    if report.bundle_version is not None:
        lines.append(f"bundleVersion={report.bundle_version}")
    if report.failed_case_ids:
        lines.append(f"failedCaseIds={report.failed_case_ids}")
    return "\n".join(lines)


def format_full_eval_report(
    report: FullEvalReport,
    *,
    include_per_case: bool = True,
    include_warnings: bool = True,
) -> str:
    """格式化完整 full-output 文本报告。

    :param report: full-output 批跑报告。
    :type report: FullEvalReport
    :param include_per_case: 是否包含逐 case 行。
    :type include_per_case: bool
    :param include_warnings: 是否附加 mustMention 软警告段。
    :type include_warnings: bool
    :returns: 完整多行报告文本。
    :rtype: str
    """
    sections: list[str] = [format_full_eval_report_summary(report), ""]

    if include_per_case:
        sections.append("--- per case ---")
        for record in report.records:
            sections.append(format_full_eval_record_line(record))
        sections.append("")

    if include_warnings:
        warning_lines: list[str] = []
        for record in report.records:
            for warning in record.semantic.warnings:
                warning_lines.append(
                    f"{record.case_id}: [{warning.code}] {warning.message}"
                )
        if warning_lines:
            sections.append("--- warnings (soft) ---")
            sections.extend(warning_lines)
            sections.append("")

    return "\n".join(sections).rstrip() + "\n"


def write_full_eval_report(
    report: FullEvalReport,
    stream: TextIO | None = None,
    *,
    include_per_case: bool = True,
    include_warnings: bool = True,
) -> None:
    """将 full-output 文本报告写入流（默认 stdout）。

    :param report: full-output 批跑报告。
    :type report: FullEvalReport
    :param stream: 输出流；省略时为 ``sys.stdout``。
    :type stream: typing.TextIO | None
    :param include_per_case: 是否包含逐 case 段。
    :type include_per_case: bool
    :param include_warnings: 是否包含软警告段。
    :type include_warnings: bool
    """
    target = stream if stream is not None else sys.stdout
    target.write(
        format_full_eval_report(
            report,
            include_per_case=include_per_case,
            include_warnings=include_warnings,
        )
    )


def write_risk_eval_report(
    report: RiskEvalReport,
    stream: TextIO | None = None,
    *,
    include_per_case: bool = True,
    include_warnings: bool = True,
) -> None:
    """将文本报告写入流（默认 stdout）。

    :param report: 批跑报告。
    :type report: RiskEvalReport
    :param stream: 输出流；省略时为 ``sys.stdout``。
    :type stream: typing.TextIO | None
    :param include_per_case: 是否包含逐 case 段。
    :type include_per_case: bool
    :param include_warnings: 是否包含软警告段。
    :type include_warnings: bool
    """
    target = stream if stream is not None else sys.stdout
    target.write(
        format_risk_eval_report(
            report,
            include_per_case=include_per_case,
            include_warnings=include_warnings,
        )
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    """构建批跑 CLI 参数解析器。

    :returns: 配置完成的 ``ArgumentParser``。
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="xiaozhua-eval-batch",
        description="小爪健康分诊 Agent — 20 case 批跑（risk-only / full-output / copy-llm）。",
    )
    parser.add_argument(
        "--mode",
        choices=["risk-only", "full-output", "copy-llm"],
        default="risk-only",
        help="批跑模式（默认 risk-only）。",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=None,
        help="case JSON 路径（默认 docs/cases/health_triage_cases.v1.json）。",
    )
    parser.add_argument(
        "--outputs",
        type=Path,
        default=None,
        help="caseId → output 的 JSON 映射文件。",
    )
    parser.add_argument(
        "--golden",
        action="store_true",
        help="使用 expected 构造 golden stub（risk minimal 或 full output）。",
    )
    parser.add_argument(
        "--must-mention-hard-gate",
        choices=["soft", "hard"],
        default="soft",
        help="mustMention 不匹配是否拉低 passed（full-output，默认 soft）。",
    )
    parser.add_argument(
        "--synonyms",
        type=Path,
        default=None,
        help="可选 KB-SYN JSON 路径（full-output mustMention 扩展）。",
    )
    parser.add_argument(
        "--confidence",
        choices=["off", "exact", "tier"],
        default="off",
        help="confidence 比对策略（默认 off）。",
    )
    parser.add_argument(
        "--confidence-hard-gate",
        choices=["soft", "hard"],
        default="soft",
        help="confidence 不匹配是否拉低 passed（默认 soft）。",
    )
    parser.add_argument(
        "--bundle-version",
        type=str,
        default=None,
        help="可选 triage-core bundleVersion pin。",
    )
    parser.add_argument(
        "--json-report",
        type=Path,
        default=None,
        help="将 ``RiskEvalReport`` 序列化为 JSON 写入该路径。",
    )
    parser.add_argument(
        "--no-per-case",
        action="store_true",
        help="文本报告不输出逐 case 段。",
    )
    parser.add_argument(
        "--no-warnings",
        action="store_true",
        help="文本报告不输出软警告段。",
    )
    parser.add_argument(
        "--copy-llm-scope",
        choices=["smoke", "full"],
        default="smoke",
        help="copy-llm 范围：smoke（5 边界 case）或 full（20 case）。",
    )
    parser.add_argument(
        "--copy-llm-skip",
        action="store_true",
        help="copy-llm 模式跳过通义千问调用（管道自检）。",
    )
    parser.add_argument(
        "--copy-llm-concurrency",
        type=int,
        default=3,
        help="copy-llm 并发上限（默认 3）。",
    )
    return parser


def config_from_namespace(namespace: argparse.Namespace) -> BatchRunConfig:
    """将 CLI 命名空间转为 ``BatchRunConfig``。

    :param namespace: ``parse_args()`` 结果。
    :type namespace: argparse.Namespace
    :returns: 批跑配置对象。
    :rtype: BatchRunConfig
    """
    eval_options = RiskEvalOptions(
        confidence_check_mode=namespace.confidence,
        confidence_hard_gate=namespace.confidence_hard_gate,
        bundle_version=namespace.bundle_version,
    )
    semantic_options = SemanticEvalOptions(
        must_mention_hard_gate=namespace.must_mention_hard_gate,
        synonym_map_path=namespace.synonyms,
        bundle_version=namespace.bundle_version,
    )
    full_eval_options = FullEvalOptions(
        risk=eval_options,
        semantic=semantic_options,
    )
    return BatchRunConfig(
        mode=namespace.mode,
        cases_path=namespace.cases,
        outputs_json_path=namespace.outputs,
        use_golden_outputs=namespace.golden,
        eval_options=eval_options,
        full_eval_options=full_eval_options,
        include_warnings_in_report=not namespace.no_warnings,
        copy_llm_scope=namespace.copy_llm_scope,
        copy_llm_skip_llm=namespace.copy_llm_skip,
        copy_llm_max_concurrency=namespace.copy_llm_concurrency,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """批跑 CLI 入口（``risk-only`` / ``full-output``）。

    退出码：硬门槛全绿为 0，否则为 1。

    :param argv: 命令行参数；省略时使用 ``sys.argv[1:]``。
    :type argv: collections.abc.Sequence[str] | None
    :returns: 进程退出码。
    :rtype: int
    """
    parser = build_arg_parser()
    namespace = parser.parse_args(list(argv) if argv is not None else None)
    config = config_from_namespace(namespace)

    report = run_batch(config)

    if isinstance(report, CopyLlmBatchReport):
        write_copy_llm_batch_report(
            report,
            include_per_case=not namespace.no_per_case,
        )
    elif isinstance(report, FullEvalReport):
        write_full_eval_report(
            report,
            include_per_case=not namespace.no_per_case,
            include_warnings=config.include_warnings_in_report,
        )
    else:
        write_risk_eval_report(
            report,
            include_per_case=not namespace.no_per_case,
            include_warnings=config.include_warnings_in_report,
        )

    if namespace.json_report is not None:
        if isinstance(report, CopyLlmBatchReport):
            namespace.json_report.write_text(
                json.dumps(
                    copy_llm_report_to_dict(report),
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        else:
            namespace.json_report.write_text(
                report.model_dump(by_alias=True, mode="json"),
                encoding="utf-8",
            )

    try:
        if isinstance(report, CopyLlmBatchReport):
            assert_copy_llm_hard_gate(report)
        elif isinstance(report, FullEvalReport):
            assert_full_output_hard_gate(report)
        else:
            assert_risk_only_hard_gate(report)
    except AssertionError:
        return 1
    return 0


# 供 ``python -m xiaozhua_health_agent.eval.batch_runner`` 或 scripts 绑定
cli_main: Callable[[Sequence[str] | None], int] = main
