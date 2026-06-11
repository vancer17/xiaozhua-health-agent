"""WP5 里程碑 B — 机械管道 full-output 批跑与闭环验收。

对 20 mock case 并发执行机械健康分诊管道（①→⑤），再运行 L7 full-output 评测
（risk + semantic 硬门槛 + mustMention 软门槛），产出可观测的
``MilestoneBBatchReport``。

IO 密集步骤（数据集 / 知识包 / 同义词表加载、并发管道执行）使用 ``async``；
包外请通过 ``xiaozhua_health_agent.pipeline`` 门面导入公开符号。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, Literal, TextIO, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.copy import (
    CopyKnowledgeBundle,
    load_default_copy_knowledge_bundle,
)
from xiaozhua_health_agent.eval import (
    EXPECTED_CASE_COUNT,
    FullEvalOptions,
    FullEvalRecord,
    FullEvalReport,
    HealthTriageDataset,
    SynonymMap,
    assert_full_output_hard_gate,
    assert_full_output_soft_gates,
    build_full_eval_report,
    evaluate_full_for_case,
    load_health_triage_dataset,
    load_synonym_map,
)
from xiaozhua_health_agent.pipeline.health_triage import run_health_triage_async
from xiaozhua_health_agent.pipeline.pipeline_types import (
    DEFAULT_HEALTH_TRIAGE_PIPELINE_OPTIONS,
    HealthTriagePipelineOptions,
    HealthTriagePipelineResult,
)
from xiaozhua_health_agent.schemas import AgentInput, AgentOutput
from xiaozhua_health_agent.paths import default_synonym_map_path
from xiaozhua_health_agent.triage import BUNDLE_VERSION

__all__ = [
    "DEFAULT_MILESTONE_B_BATCH_CONFIG",
    "DEFAULT_MUST_MENTION_SOFT_THRESHOLD",
    "MILESTONE_B_SCHEMA_VERSION",
    "MilestoneBBatchConfig",
    "MilestoneBBatchMode",
    "MilestoneBBatchModeLiteral",
    "MilestoneBBatchReport",
    "PipelineBatchCaseRecord",
    "assert_milestone_b_hard_gate",
    "assert_milestone_b_pipeline_hard_gate",
    "assert_milestone_b_soft_gates",
    "format_milestone_b_pipeline_failure_summary",
    "format_milestone_b_record_line",
    "format_milestone_b_report",
    "format_milestone_b_report_summary",
    "milestone_b_report_to_dict",
    "run_milestone_b_batch",
    "run_milestone_b_batch_async",
    "write_milestone_b_json_report",
    "write_milestone_b_report",
]

MILESTONE_B_SCHEMA_VERSION: Final[str] = "xiaozhua.health_agent.milestone_b_batch.v1"
"""里程碑 B 批跑报告 schema 版本。"""

DEFAULT_MUST_MENTION_SOFT_THRESHOLD: Final[int] = 18
"""开发计划 WP5 建议的 mustMention 软门槛（20 case 中 ≥ 18）。"""

MilestoneBBatchModeLiteral: TypeAlias = Literal["milestone-b"]
"""里程碑 B 批跑模式标识。"""


class MilestoneBBatchMode(StrEnum):
    """里程碑 B 批跑模式常量。"""

    MILESTONE_B = "milestone-b"


class MilestoneBBatchConfig(BaseModel):
    """里程碑 B 批跑运行配置。

    :param cases_path: mock case JSON 路径；省略时使用默认 ``docs/cases``。
    :param max_concurrency: 并发执行管道的上限（``asyncio.Semaphore``）。
    :param synonym_map_path: 可选 KB-SYN JSON；用于 mustMention 同义词扩展。
    :param must_mention_soft_threshold: mustMention 软门槛通过数（默认 18/20）。
    :param load_default_copy_bundle: 未注入 ``copy_bundle`` 时是否加载默认 KB-TPL。
    :param skip_final_schema_check: 为 true 时管道跳过出站 FULL 校验（仅调试）。
    :param load_default_synonym_map: 未注入 ``synonym_map`` 时是否加载默认 KB-SYN。
    :param skip_content_guard: 为 true 时管道跳过 ValidateContent（仅调试）。
    """

    model_config = ConfigDict(extra="forbid")

    cases_path: Path | None = Field(
        default=None,
        description="mock case JSON 路径；None 表示默认 docs/cases。",
    )
    max_concurrency: int = Field(
        default=4,
        ge=1,
        le=20,
        description="并发管道执行上限。",
    )
    synonym_map_path: Path | None = Field(
        default=None,
        description="可选 KB-SYN JSON 路径。",
    )
    must_mention_soft_threshold: int = Field(
        default=DEFAULT_MUST_MENTION_SOFT_THRESHOLD,
        ge=0,
        description="mustMention 软门槛建议通过数。",
    )
    load_default_copy_bundle: bool = Field(
        default=True,
        description="未注入 copy_bundle 时是否加载默认知识包。",
    )
    skip_final_schema_check: bool = Field(
        default=False,
        description="调试：跳过管道出站 output_schema FULL 校验。",
    )
    load_default_synonym_map: bool = Field(
        default=True,
        description="未注入 synonym_map 时是否加载默认 KB-SYN。",
    )
    skip_content_guard: bool = Field(
        default=False,
        description="调试：跳过 ValidateContent。",
    )


DEFAULT_MILESTONE_B_BATCH_CONFIG: MilestoneBBatchConfig = MilestoneBBatchConfig()
"""里程碑 B 默认批跑配置（20 case 全量 + 默认软门槛 18）。"""


@dataclass(frozen=True, slots=True)
class PipelineBatchCaseRecord:
    """单条 case 的管道执行与 full-output 评测快照。

    :ivar case_id: 用例唯一标识。
    :vartype case_id: str
    :ivar case_name: 用例中文名称。
    :vartype case_name: str
    :ivar pipeline_passed: 机械管道是否成功产出 ``AgentOutput``。
    :vartype pipeline_passed: bool
    :ivar pipeline_result: 完整管道执行结果（含 stage / violations / trace）。
    :vartype pipeline_result: HealthTriagePipelineResult
    :ivar full_eval: full-output 评测记录；管道失败时仍可能含 semantic/risk 失败项。
    :vartype full_eval: FullEvalRecord
    """

    case_id: str
    case_name: str
    pipeline_passed: bool
    pipeline_result: HealthTriagePipelineResult
    full_eval: FullEvalRecord


@dataclass(frozen=True, slots=True)
class MilestoneBBatchReport:
    """里程碑 B 批跑汇总报告（管道 + full-output 评测）。

    :ivar mode: 固定 ``milestone-b``。
    :vartype mode: MilestoneBBatchModeLiteral
    :ivar schema_version: 报告 schema 版本。
    :vartype schema_version: str
    :ivar dataset_version: mock case 数据集版本。
    :vartype dataset_version: str
    :ivar total: 参与批跑的 case 总数（期望 20）。
    :vartype total: int
    :ivar pipeline_passed: 管道成功产出 ``AgentOutput`` 的数量。
    :vartype pipeline_passed: int
    :ivar pipeline_failed: 管道失败数量。
    :vartype pipeline_failed: int
    :ivar pipeline_failed_case_ids: 管道失败 caseId 列表（保序）。
    :vartype pipeline_failed_case_ids: tuple[str, ...]
    :ivar pipeline_failures_by_stage: 管道失败按 ``stage`` 分组（caseId 列表）。
    :vartype pipeline_failures_by_stage: dict[str, tuple[str, ...]]
    :ivar full_eval: L7 full-output 评测报告（risk + semantic）。
    :vartype full_eval: FullEvalReport
    :ivar records: 逐 case 管道 + 评测记录。
    :vartype records: tuple[PipelineBatchCaseRecord, ...]
    :ivar must_mention_soft_threshold: mustMention 软门槛线。
    :vartype must_mention_soft_threshold: int
    :ivar generated_at: 报告生成 UTC 时间。
    :vartype generated_at: datetime
    :ivar bundle_version: 可选 triage-core ``bundleVersion`` pin。
    :vartype bundle_version: str | None
    """

    mode: MilestoneBBatchModeLiteral
    schema_version: str
    dataset_version: str
    total: int
    pipeline_passed: int
    pipeline_failed: int
    pipeline_failed_case_ids: tuple[str, ...]
    pipeline_failures_by_stage: dict[str, tuple[str, ...]]
    full_eval: FullEvalReport
    records: tuple[PipelineBatchCaseRecord, ...]
    must_mention_soft_threshold: int
    generated_at: datetime
    bundle_version: str | None = None

    @property
    def full_output_hard_passed(self) -> int:
        """full-output 硬门槛（risk + semantic）通过数。

        :returns: ``full_eval.passed``。
        :rtype: int
        """
        return self.full_eval.passed

    @property
    def must_mention_passed(self) -> int:
        """mustMention 维度通过数。

        :returns: ``full_eval.must_mention_passed``。
        :rtype: int
        """
        return self.full_eval.must_mention_passed


def run_milestone_b_batch(
    dataset: HealthTriageDataset | None = None,
    *,
    config: MilestoneBBatchConfig | None = None,
    pipeline_options: HealthTriagePipelineOptions | None = None,
    copy_bundle: CopyKnowledgeBundle | None = None,
    full_eval_options: FullEvalOptions | None = None,
    synonym_map: SynonymMap | None = None,
) -> MilestoneBBatchReport:
    """执行里程碑 B 批跑（同步入口）。

    内部通过 ``asyncio.run`` 委托 :func:`run_milestone_b_batch_async`；
    在已有事件循环的上下文请直接调用异步版本。

    :param dataset: mock case 数据集；省略时按 ``config.cases_path`` 加载。
    :type dataset: HealthTriageDataset | None
    :param config: 批跑配置；省略时使用 ``DEFAULT_MILESTONE_B_BATCH_CONFIG``。
    :type config: MilestoneBBatchConfig | None
    :param pipeline_options: 机械管道配置；省略时由 ``config`` 派生默认值。
    :type pipeline_options: HealthTriagePipelineOptions | None
    :param copy_bundle: 可选预加载 KB-TPL 知识包。
    :type copy_bundle: CopyKnowledgeBundle | None
    :param full_eval_options: full-output 评测配置；省略时注入 ``bundleVersion``。
    :type full_eval_options: FullEvalOptions | None
    :param synonym_map: 可选预加载同义词表；省略时按 ``config.synonym_map_path`` 加载。
    :type synonym_map: SynonymMap | None
    :returns: 里程碑 B 批跑报告。
    :rtype: MilestoneBBatchReport
    """
    return _run_async_from_sync(
        run_milestone_b_batch_async(
            dataset,
            config=config,
            pipeline_options=pipeline_options,
            copy_bundle=copy_bundle,
            full_eval_options=full_eval_options,
            synonym_map=synonym_map,
        ),
    )


async def run_milestone_b_batch_async(
    dataset: HealthTriageDataset | None = None,
    *,
    config: MilestoneBBatchConfig | None = None,
    pipeline_options: HealthTriagePipelineOptions | None = None,
    copy_bundle: CopyKnowledgeBundle | None = None,
    full_eval_options: FullEvalOptions | None = None,
    synonym_map: SynonymMap | None = None,
) -> MilestoneBBatchReport:
    """执行里程碑 B 批跑（异步核心）。

    流程：

    1. 加载 dataset / copy_bundle / synonym_map（IO → ``asyncio.to_thread``）
    2. 并发执行 ``run_health_triage_async``（受 ``max_concurrency`` 限制）
    3. 对每条管道结果运行 ``evaluate_full_for_case``
    4. 组装 ``MilestoneBBatchReport`` 与 ``FullEvalReport``

    :param dataset: mock case 数据集；省略时异步加载。
    :type dataset: HealthTriageDataset | None
    :param config: 批跑配置。
    :type config: MilestoneBBatchConfig | None
    :param pipeline_options: 机械管道配置。
    :type pipeline_options: HealthTriagePipelineOptions | None
    :param copy_bundle: 可选预加载知识包。
    :type copy_bundle: CopyKnowledgeBundle | None
    :param full_eval_options: full-output 评测配置。
    :type full_eval_options: FullEvalOptions | None
    :param synonym_map: 可选预加载同义词表。
    :type synonym_map: SynonymMap | None
    :returns: 里程碑 B 批跑报告。
    :rtype: MilestoneBBatchReport
    """
    effective_config = (
        config if config is not None else DEFAULT_MILESTONE_B_BATCH_CONFIG
    )
    resolved_dataset = await _resolve_dataset_async(
        dataset=dataset,
        cases_path=effective_config.cases_path,
    )
    resolved_bundle = await _resolve_copy_bundle_async(
        copy_bundle=copy_bundle,
        load_default=effective_config.load_default_copy_bundle,
    )
    resolved_synonym_map = await _resolve_synonym_map_async(
        synonym_map=synonym_map,
        synonym_map_path=effective_config.synonym_map_path,
        load_default=effective_config.load_default_synonym_map,
    )
    effective_pipeline_options = _resolve_pipeline_options(
        pipeline_options=pipeline_options,
        config=effective_config,
        copy_bundle=resolved_bundle,
    )
    effective_full_eval_options = _resolve_full_eval_options(
        full_eval_options=full_eval_options,
        must_mention_soft_threshold=effective_config.must_mention_soft_threshold,
    )

    pipeline_results = await _run_all_pipelines_async(
        resolved_dataset,
        pipeline_options=effective_pipeline_options,
        copy_bundle=resolved_bundle,
        max_concurrency=effective_config.max_concurrency,
    )

    records = _build_pipeline_batch_records(
        resolved_dataset,
        pipeline_results=pipeline_results,
        full_eval_options=effective_full_eval_options,
        synonym_map=resolved_synonym_map,
    )

    full_eval_records = tuple(record.full_eval for record in records)
    bundle_version = (
        effective_full_eval_options.risk.bundle_version
        or effective_full_eval_options.semantic.bundle_version
    )
    full_eval_report = build_full_eval_report(
        list(full_eval_records),
        dataset_version=resolved_dataset.dataset_version,
        must_mention_batch_threshold=effective_config.must_mention_soft_threshold,
        bundle_version=bundle_version,
    )

    pipeline_passed, pipeline_failed_ids, failures_by_stage = (
        _summarize_pipeline_outcomes(records)
    )

    return MilestoneBBatchReport(
        mode=MilestoneBBatchMode.MILESTONE_B.value,
        schema_version=MILESTONE_B_SCHEMA_VERSION,
        dataset_version=resolved_dataset.dataset_version,
        total=len(records),
        pipeline_passed=pipeline_passed,
        pipeline_failed=len(pipeline_failed_ids),
        pipeline_failed_case_ids=pipeline_failed_ids,
        pipeline_failures_by_stage=failures_by_stage,
        full_eval=full_eval_report,
        records=records,
        must_mention_soft_threshold=effective_config.must_mention_soft_threshold,
        generated_at=datetime.now(tz=UTC),
        bundle_version=bundle_version,
    )


def assert_milestone_b_pipeline_hard_gate(
    report: MilestoneBBatchReport,
    *,
    expected_total: int | None = None,
) -> None:
    """断言里程碑 B 管道硬门槛：全部 case 成功产出 ``AgentOutput``。

    :param report: 里程碑 B 批跑报告。
    :type report: MilestoneBBatchReport
    :param expected_total: 期望 case 总数；省略时使用 ``report.total``。
    :type expected_total: int | None
    :raises AssertionError: 存在管道失败时抛出。
    """
    total = expected_total if expected_total is not None else report.total
    if report.pipeline_passed != total:
        failure_summary = format_milestone_b_pipeline_failure_summary(report)
        msg = (
            f"里程碑 B 管道硬门槛未全绿：{report.pipeline_passed}/{total} "
            f"pipeline passed。\n{failure_summary}"
        )
        raise AssertionError(msg)


def assert_milestone_b_hard_gate(
    report: MilestoneBBatchReport,
    *,
    expected_total: int | None = None,
) -> None:
    """断言里程碑 B 完整硬门槛：管道全绿 + full-output 硬门槛全绿。

    硬门槛包含：20/20 管道成功、riskLevel 一致、禁止词、mustNotMention、
    ``safetyNoticeRequired``、FULL ``output_schema`` 结构等（见 L7 semantic）。

    :param report: 里程碑 B 批跑报告。
    :type report: MilestoneBBatchReport
    :param expected_total: 期望 case 总数；省略时使用 ``report.total``。
    :type expected_total: int | None
    :raises AssertionError: 任一层硬门槛未达标时抛出。
    """
    assert_milestone_b_pipeline_hard_gate(report, expected_total=expected_total)
    assert_full_output_hard_gate(report.full_eval, expected_total=expected_total)


def assert_milestone_b_soft_gates(
    report: MilestoneBBatchReport,
    *,
    must_mention_threshold: int | None = None,
) -> None:
    """断言里程碑 B 软门槛（mustMention 批级建议线）。

    :param report: 里程碑 B 批跑报告。
    :type report: MilestoneBBatchReport
    :param must_mention_threshold: 期望 mustMention 通过数；省略时使用报告内阈值。
    :type must_mention_threshold: int | None
    :raises AssertionError: 软门槛未达标时抛出。
    """
    threshold = (
        must_mention_threshold
        if must_mention_threshold is not None
        else report.must_mention_soft_threshold
    )
    assert_full_output_soft_gates(
        report.full_eval,
        must_mention_threshold=threshold,
    )


def format_milestone_b_pipeline_failure_summary(
    report: MilestoneBBatchReport,
) -> str:
    """格式化管道失败按 stage 分组的摘要文本。

    :param report: 里程碑 B 批跑报告。
    :type report: MilestoneBBatchReport
    :returns: 多行人类可读摘要。
    :rtype: str
    """
    if report.pipeline_failed == 0:
        return "管道失败：无"

    lines: list[str] = [
        f"管道失败 caseId（{report.pipeline_failed}）："
        f"{', '.join(report.pipeline_failed_case_ids)}",
    ]
    for stage, case_ids in sorted(report.pipeline_failures_by_stage.items()):
        lines.append(f"  stage={stage}: {', '.join(case_ids)}")
    return "\n".join(lines)


def format_milestone_b_record_line(record: PipelineBatchCaseRecord) -> str:
    """格式化单条里程碑 B 记录为一行摘要。

    :param record: 单条管道 + 评测记录。
    :type record: PipelineBatchCaseRecord
    :returns: 单行摘要文本。
    :rtype: str
    """
    pipeline_flag = "PIPELINE=PASS" if record.pipeline_passed else "PIPELINE=FAIL"
    full_flag = "FULL=PASS" if record.full_eval.passed else "FULL=FAIL"
    stage = record.pipeline_result.stage
    merge_fb = " merge_fb" if record.pipeline_result.used_merge_fallback else ""
    fs_rec = " fs_rec" if record.pipeline_result.used_final_schema_recovery else ""
    return (
        f"{record.case_id} ({record.case_name}): "
        f"{pipeline_flag} stage={stage}{merge_fb}{fs_rec} | "
        f"{full_flag} risk={'PASS' if record.full_eval.risk.passed else 'FAIL'} "
        f"semantic={'PASS' if record.full_eval.semantic.passed else 'FAIL'}"
    )


def format_milestone_b_report_summary(report: MilestoneBBatchReport) -> str:
    """格式化里程碑 B 批跑报告头部汇总段。

    :param report: 里程碑 B 批跑报告。
    :type report: MilestoneBBatchReport
    :returns: 多行汇总文本。
    :rtype: str
    """
    lines = [
        f"模式: {report.mode} ({report.schema_version})",
        f"数据集: {report.dataset_version} | 总数: {report.total}",
        (
            f"管道: {report.pipeline_passed}/{report.total} passed "
            f"({report.pipeline_failed} failed)"
        ),
        (
            f"full-output 硬门槛: {report.full_output_hard_passed}/{report.total} "
            f"passed ({report.full_eval.failed} failed)"
        ),
        (
            f"risk: {report.full_eval.risk_passed}/{report.total} | "
            f"semantic: {report.full_eval.semantic_passed}/{report.total}"
        ),
        (
            f"mustMention: {report.must_mention_passed}/{report.total} "
            f"(soft threshold>={report.must_mention_soft_threshold})"
        ),
    ]
    if report.bundle_version is not None:
        lines.append(f"bundleVersion: {report.bundle_version}")
    lines.append(f"生成时间 (UTC): {report.generated_at.isoformat()}")
    if report.pipeline_failed > 0:
        lines.append("")
        lines.append(format_milestone_b_pipeline_failure_summary(report))
    return "\n".join(lines)


def format_milestone_b_report(
    report: MilestoneBBatchReport,
    *,
    include_per_case: bool = True,
) -> str:
    """格式化完整里程碑 B 文本报告。

    :param report: 里程碑 B 批跑报告。
    :type report: MilestoneBBatchReport
    :param include_per_case: 是否包含逐 case 行。
    :type include_per_case: bool
    :returns: 多行文本报告。
    :rtype: str
    """
    sections: list[str] = [format_milestone_b_report_summary(report)]
    if include_per_case:
        sections.append("")
        sections.append("逐 case：")
        for record in report.records:
            sections.append(format_milestone_b_record_line(record))
    return "\n".join(sections)


def write_milestone_b_report(
    report: MilestoneBBatchReport,
    *,
    stream: TextIO | None = None,
    include_per_case: bool = True,
) -> None:
    """将里程碑 B 文本报告写入流（默认 stdout）。

    :param report: 里程碑 B 批跑报告。
    :type report: MilestoneBBatchReport
    :param stream: 目标文本流；省略时使用 ``sys.stdout``。
    :type stream: TextIO | None
    :param include_per_case: 是否输出逐 case 段。
    :type include_per_case: bool
    :returns: ``None``。
    :rtype: None
    """
    import sys

    target = stream if stream is not None else sys.stdout
    text = format_milestone_b_report(report, include_per_case=include_per_case)
    target.write(text)
    if not text.endswith("\n"):
        target.write("\n")


def milestone_b_report_to_dict(report: MilestoneBBatchReport) -> dict[str, Any]:
    """将里程碑 B 报告序列化为 JSON 友好字典。

    :param report: 里程碑 B 批跑报告。
    :type report: MilestoneBBatchReport
    :returns: 可 ``json.dumps`` 的字典。
    :rtype: dict[str, Any]
    """
    return {
        "mode": report.mode,
        "schemaVersion": report.schema_version,
        "datasetVersion": report.dataset_version,
        "total": report.total,
        "pipelinePassed": report.pipeline_passed,
        "pipelineFailed": report.pipeline_failed,
        "pipelineFailedCaseIds": list(report.pipeline_failed_case_ids),
        "pipelineFailuresByStage": {
            stage: list(case_ids)
            for stage, case_ids in report.pipeline_failures_by_stage.items()
        },
        "mustMentionSoftThreshold": report.must_mention_soft_threshold,
        "mustMentionPassed": report.must_mention_passed,
        "bundleVersion": report.bundle_version,
        "generatedAt": report.generated_at.isoformat(),
        "fullEval": report.full_eval.model_dump(by_alias=True, mode="json"),
        "records": [
            _pipeline_batch_case_record_to_dict(record) for record in report.records
        ],
    }


def _run_async_from_sync(
    coroutine: Coroutine[Any, Any, MilestoneBBatchReport],
) -> MilestoneBBatchReport:
    """在同步上下文中执行异步批跑协程（内部辅助）。

    :param coroutine: 待执行的批跑协程。
    :type coroutine: collections.abc.Coroutine[Any, Any, MilestoneBBatchReport]
    :returns: 批跑报告。
    :rtype: MilestoneBBatchReport
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    def _run_in_isolated_loop() -> MilestoneBBatchReport:
        """在子线程新事件循环中运行批跑协程（闭包）。

        :returns: 批跑报告。
        :rtype: MilestoneBBatchReport
        """
        return asyncio.run(coroutine)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_in_isolated_loop)
        return future.result()


async def _resolve_dataset_async(
    *,
    dataset: HealthTriageDataset | None,
    cases_path: Path | None,
) -> HealthTriageDataset:
    """解析或异步加载 mock case 数据集（内部辅助）。

    :param dataset: 调用方已加载的数据集；非空时直接返回。
    :type dataset: HealthTriageDataset | None
    :param cases_path: 可选 case 文件路径。
    :type cases_path: Path | None
    :returns: 校验后的数据集。
    :rtype: HealthTriageDataset
    :raises ValueError: 加载后 case 数量不等于 ``EXPECTED_CASE_COUNT`` 时抛出。
    """
    if dataset is not None:
        resolved = dataset
    else:

        async def _load() -> HealthTriageDataset:
            """在线程池加载 case JSON（闭包）。

            :returns: 解析后的数据集。
            :rtype: HealthTriageDataset
            """
            return await asyncio.to_thread(load_health_triage_dataset, cases_path)

        resolved = await _load()

    if len(resolved.cases) != EXPECTED_CASE_COUNT:
        msg = (
            f"里程碑 B 期望 {EXPECTED_CASE_COUNT} 条 case，"
            f"实际 {len(resolved.cases)} 条。"
        )
        raise ValueError(msg)
    return resolved


async def _resolve_copy_bundle_async(
    *,
    copy_bundle: CopyKnowledgeBundle | None,
    load_default: bool,
) -> CopyKnowledgeBundle | None:
    """解析或异步加载 KB-TPL 知识包（内部辅助）。

    :param copy_bundle: 调用方预加载的知识包。
    :type copy_bundle: CopyKnowledgeBundle | None
    :param load_default: 是否在未注入时加载默认包。
    :type load_default: bool
    :returns: 知识包或 ``None``。
    :rtype: CopyKnowledgeBundle | None
    """
    if copy_bundle is not None:
        return copy_bundle
    if not load_default:
        return None

    async def _load_default() -> CopyKnowledgeBundle:
        """在线程池加载默认 copy 知识包（闭包）。

        :returns: 默认 KB-TPL 聚合包。
        :rtype: CopyKnowledgeBundle
        """
        return await asyncio.to_thread(load_default_copy_knowledge_bundle)

    return await _load_default()


async def _resolve_synonym_map_async(
    *,
    synonym_map: SynonymMap | None,
    synonym_map_path: Path | None,
    load_default: bool,
) -> SynonymMap | None:
    """解析或异步加载 KB-SYN 同义词表（内部辅助）。

    :param synonym_map: 调用方预加载的同义词表。
    :type synonym_map: SynonymMap | None
    :param synonym_map_path: 可选 JSON 路径。
    :type synonym_map_path: Path | None
    :param load_default: 是否在未注入时加载默认 KB-SYN。
    :type load_default: bool
    :returns: 同义词表或 ``None``（仅字面匹配）。
    :rtype: SynonymMap | None
    """
    if synonym_map is not None:
        return synonym_map

    resolved_path = (
        synonym_map_path
        if synonym_map_path is not None
        else (default_synonym_map_path() if load_default else None)
    )
    if resolved_path is None:
        return None

    async def _load() -> SynonymMap:
        """在线程池加载同义词 JSON（闭包）。

        :returns: 解析后的同义词表。
        :rtype: SynonymMap
        """
        return await asyncio.to_thread(load_synonym_map, resolved_path)

    return await _load()


def _resolve_pipeline_options(
    *,
    pipeline_options: HealthTriagePipelineOptions | None,
    config: MilestoneBBatchConfig,
    copy_bundle: CopyKnowledgeBundle | None,
) -> HealthTriagePipelineOptions:
    """将批跑配置与调用方选项合并为有效管道配置（内部辅助）。

    :param pipeline_options: 调用方管道配置；省略时使用默认并叠加 ``config`` 调试旗标。
    :type pipeline_options: HealthTriagePipelineOptions | None
    :param config: 里程碑 B 批跑配置。
    :type config: MilestoneBBatchConfig
    :param copy_bundle: 已解析的知识包。
    :type copy_bundle: CopyKnowledgeBundle | None
    :returns: 有效管道运行配置。
    :rtype: HealthTriagePipelineOptions
    """
    base = (
        pipeline_options
        if pipeline_options is not None
        else DEFAULT_HEALTH_TRIAGE_PIPELINE_OPTIONS
    )
    effective = HealthTriagePipelineOptions(
        mode=base.mode,
        copy_bundle=copy_bundle if copy_bundle is not None else base.copy_bundle,
        load_default_copy_bundle=(
            False if copy_bundle is not None else base.load_default_copy_bundle
        ),
        mechanical_options=base.mechanical_options,
        skip_final_schema_check=(
            config.skip_final_schema_check or base.skip_final_schema_check
        ),
        guard_mode=base.guard_mode,
        guard_options=base.guard_options,
        skip_content_guard=config.skip_content_guard or base.skip_content_guard,
        retry_options=base.retry_options,
        enable_merge_fallback=base.enable_merge_fallback,
        enable_final_schema_recovery=base.enable_final_schema_recovery,
        skip_merge_ready_check=base.skip_merge_ready_check,
        merge_ready_options=base.merge_ready_options,
    )
    if copy_bundle is not None:
        return effective.with_copy_bundle(copy_bundle)
    return effective


def _resolve_full_eval_options(
    *,
    full_eval_options: FullEvalOptions | None,
    must_mention_soft_threshold: int,
) -> FullEvalOptions:
    """解析 full-output 评测配置并注入 ``bundleVersion`` 与软门槛（内部辅助）。

    :param full_eval_options: 调用方配置；省略时使用 L7 默认。
    :type full_eval_options: FullEvalOptions | None
    :param must_mention_soft_threshold: mustMention 软门槛通过数。
    :type must_mention_soft_threshold: int
    :returns: 有效 full-output 评测配置。
    :rtype: FullEvalOptions
    """
    base = full_eval_options if full_eval_options is not None else FullEvalOptions()
    risk_options = base.risk
    if risk_options.bundle_version is None:
        risk_options = risk_options.model_copy(
            update={"bundle_version": BUNDLE_VERSION}
        )
    semantic_options = base.semantic.model_copy(
        update={
            "must_mention_batch_threshold": must_mention_soft_threshold,
            "bundle_version": base.semantic.bundle_version or BUNDLE_VERSION,
        },
    )
    return base.model_copy(
        update={"risk": risk_options, "semantic": semantic_options},
    )


async def _run_all_pipelines_async(
    dataset: HealthTriageDataset,
    *,
    pipeline_options: HealthTriagePipelineOptions,
    copy_bundle: CopyKnowledgeBundle | None,
    max_concurrency: int,
) -> tuple[HealthTriagePipelineResult, ...]:
    """并发执行全部 case 的机械健康分诊管道（内部辅助）。

    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param pipeline_options: 管道运行配置。
    :type pipeline_options: HealthTriagePipelineOptions
    :param copy_bundle: 可选预加载知识包。
    :type copy_bundle: CopyKnowledgeBundle | None
    :param max_concurrency: 并发上限。
    :type max_concurrency: int
    :returns: 与 ``dataset.cases`` 顺序一致的管道结果元组。
    :rtype: tuple[HealthTriagePipelineResult, ...]
    """
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _run_one(
        agent_input: AgentInput | Mapping[str, Any],
    ) -> HealthTriagePipelineResult:
        """在信号量限制下执行单 case 管道（闭包）。

        :param agent_input: case 输入 JSON。
        :type agent_input: AgentInput | collections.abc.Mapping[str, Any]
        :returns: 管道执行结果。
        :rtype: HealthTriagePipelineResult
        """
        async with semaphore:
            return await run_health_triage_async(
                agent_input,
                options=pipeline_options,
                copy_bundle=copy_bundle,
            )

    tasks = [_run_one(case.input) for case in dataset.cases]
    results = await asyncio.gather(*tasks)
    return tuple(results)


def _build_pipeline_batch_records(
    dataset: HealthTriageDataset,
    *,
    pipeline_results: Sequence[HealthTriagePipelineResult],
    full_eval_options: FullEvalOptions,
    synonym_map: SynonymMap | None,
) -> tuple[PipelineBatchCaseRecord, ...]:
    """将管道结果与 full-output 评测组装为逐 case 记录（内部辅助）。

    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :param pipeline_results: 与 ``dataset.cases`` 对齐的管道结果序列。
    :type pipeline_results: collections.abc.Sequence[HealthTriagePipelineResult]
    :param full_eval_options: full-output 评测配置。
    :type full_eval_options: FullEvalOptions
    :param synonym_map: 可选同义词表。
    :type synonym_map: SynonymMap | None
    :returns: 逐 case 记录元组。
    :rtype: tuple[PipelineBatchCaseRecord, ...]
    :raises ValueError: 管道结果数量与 case 数量不一致时抛出。
    """
    if len(pipeline_results) != len(dataset.cases):
        msg = f"管道结果数 {len(pipeline_results)} 与 case 数 {len(dataset.cases)} 不一致。"
        raise ValueError(msg)

    records: list[PipelineBatchCaseRecord] = []
    for case, pipeline_result in zip(dataset.cases, pipeline_results, strict=True):
        actual_output: AgentOutput | None = (
            pipeline_result.output if pipeline_result.passed else None
        )
        full_eval = evaluate_full_for_case(
            case,
            actual_output,
            options=full_eval_options,
            rule_hits=list(pipeline_result.rule_hits),
            primary_flag=pipeline_result.primary_flag,
            synonym_map=synonym_map,
        )
        records.append(
            PipelineBatchCaseRecord(
                case_id=case.case_id,
                case_name=case.name,
                pipeline_passed=pipeline_result.passed,
                pipeline_result=pipeline_result,
                full_eval=full_eval,
            ),
        )
    return tuple(records)


def _summarize_pipeline_outcomes(
    records: Sequence[PipelineBatchCaseRecord],
) -> tuple[int, tuple[str, ...], dict[str, tuple[str, ...]]]:
    """统计管道通过数、失败 caseId 与按 stage 分组（内部辅助）。

    :param records: 逐 case 批跑记录。
    :type records: collections.abc.Sequence[PipelineBatchCaseRecord]
    :returns: ``(pipeline_passed, failed_case_ids, failures_by_stage)`` 三元组。
    :rtype: tuple[int, tuple[str, ...], dict[str, tuple[str, ...]]]
    """
    passed_count = 0
    failed_ids: list[str] = []
    by_stage: dict[str, list[str]] = {}

    for record in records:
        if record.pipeline_passed:
            passed_count += 1
            continue
        failed_ids.append(record.case_id)
        stage = record.pipeline_result.stage
        by_stage.setdefault(stage, []).append(record.case_id)

    frozen_by_stage = {
        stage: tuple(case_ids) for stage, case_ids in sorted(by_stage.items())
    }
    return passed_count, tuple(failed_ids), frozen_by_stage


def _pipeline_batch_case_record_to_dict(
    record: PipelineBatchCaseRecord,
) -> dict[str, Any]:
    """将单条 ``PipelineBatchCaseRecord`` 转为 JSON 友好字典（内部辅助）。

    :param record: 单条批跑记录。
    :type record: PipelineBatchCaseRecord
    :returns: 可序列化字典。
    :rtype: dict[str, Any]
    """
    pipeline = record.pipeline_result
    return {
        "caseId": record.case_id,
        "caseName": record.case_name,
        "pipelinePassed": record.pipeline_passed,
        "pipelineStage": pipeline.stage,
        "pipelineErrorMessage": pipeline.error_message,
        "usedMechanicalFallback": pipeline.used_mechanical_fallback,
        "usedMergeFallback": pipeline.used_merge_fallback,
        "usedFinalSchemaRecovery": pipeline.used_final_schema_recovery,
        "attemptCount": pipeline.attempt_count,
        "primaryFlag": pipeline.primary_flag,
        "ruleHits": list(pipeline.rule_hits),
        "violations": [
            v.model_dump(by_alias=True, mode="json") for v in pipeline.violations
        ],
        "fullEvalPassed": record.full_eval.passed,
        "fullEval": record.full_eval.model_dump(by_alias=True, mode="json"),
    }


def _serialize_milestone_b_json(report: MilestoneBBatchReport) -> str:
    """序列化里程碑 B 报告为 JSON 字符串（内部辅助）。

    :param report: 里程碑 B 批跑报告。
    :type report: MilestoneBBatchReport
    :returns: 缩进 JSON 文本。
    :rtype: str
    """
    return json.dumps(
        milestone_b_report_to_dict(report),
        ensure_ascii=False,
        indent=2,
    )


def write_milestone_b_json_report(
    report: MilestoneBBatchReport,
    path: Path,
) -> None:
    """将里程碑 B 报告写入 JSON 文件。

    :param report: 里程碑 B 批跑报告。
    :type report: MilestoneBBatchReport
    :param path: 目标文件路径。
    :type path: Path
    :returns: ``None``。
    :rtype: None
    """
    path.write_text(_serialize_milestone_b_json(report), encoding="utf-8")
