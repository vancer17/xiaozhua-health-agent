"""``copy-llm`` 批跑模式（WP4 ③-2 通义千问文案生成验收）。

对 mock case 执行 ①→②→③-1→通义千问→``draft_parser``，校验 ``DraftCopyJSON`` 结构。
支持 5 个边界 case 冒烟子集与 20 case 全量；IO 路径为 ``async``。

包外请通过 ``xiaozhua_health_agent.eval`` 门面导入本模块公开符号。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal, TextIO, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.eval.case_dataset import (
    EXPECTED_CASE_COUNT,
    CaseRecord,
    HealthTriageDataset,
    load_health_triage_dataset,
)
from xiaozhua_health_agent.eval.validation_result import (
    Violation,
    ViolationCode,
    ViolationSeverity,
)
from xiaozhua_health_agent.paths import default_cases_path

if TYPE_CHECKING:
    from xiaozhua_health_agent.copy import AsyncQwenClient, CopyLlmCaseResult

__all__ = [
    "COPY_LLM_SMOKE_CASE_IDS",
    "CopyLlmBatchConfig",
    "CopyLlmBatchMode",
    "CopyLlmBatchModeLiteral",
    "CopyLlmBatchRecord",
    "CopyLlmBatchReport",
    "assert_copy_llm_hard_gate",
    "copy_llm_report_to_dict",
    "format_copy_llm_batch_report",
    "format_copy_llm_record_line",
    "format_copy_llm_report_summary",
    "run_copy_llm_batch",
    "run_copy_llm_batch_async",
    "write_copy_llm_batch_report",
]

CopyLlmBatchModeLiteral: TypeAlias = Literal["smoke", "full"]

COPY_LLM_SMOKE_CASE_IDS: Final[tuple[str, ...]] = (
    "respiratory_rate_high_resting",
    "emergency_breathing_difficulty",
    "missing_vitals",
    "conflict_user_normal_sensor_fever",
    "mild_fever_after_exercise",
)
"""copy-llm 冒烟子集（#4 / #12 / #10 / #11 / #2），见开发计划 §5.3。"""


class CopyLlmBatchMode(StrEnum):
    """copy-llm 批跑范围。"""

    SMOKE = "smoke"
    FULL = "full"


class CopyLlmBatchConfig(BaseModel):
    """copy-llm 批跑配置。

    :param mode: ``smoke`` 仅跑边界子集；``full`` 跑数据集全部 case。
    :param cases_path: mock case JSON 路径。
    :param skip_llm: 为 true 时不调用通义（仅验证 ③-1 与管道编排）。
    :param case_ids: 可选显式 caseId 列表；设置时覆盖 ``mode`` 默认子集。
    :param max_concurrency: 并发请求上限（asyncio Semaphore）。
    """

    model_config = ConfigDict(extra="forbid")

    mode: CopyLlmBatchModeLiteral = Field(
        default=CopyLlmBatchMode.SMOKE.value,
        description="smoke 或 full。",
    )
    cases_path: Path | None = Field(
        default=None,
        description="case 文件路径；省略时使用默认 docs/cases。",
    )
    skip_llm: bool = Field(
        default=False,
        description="跳过文案生成（仅 ③-1）；与 use_mechanical 互斥时 use_mechanical 优先。",
    )
    use_mechanical: bool = Field(
        default=False,
        description="使用机械文案路径（无 API Key 可跑通 DraftCopyJSON 结构验收）。",
    )
    case_ids: list[str] | None = Field(
        default=None,
        description="显式指定 caseId 列表；非空时覆盖 mode 默认范围。",
    )
    max_concurrency: int = Field(
        default=3,
        ge=1,
        le=20,
        description="并发调用通义千问的上限。",
    )


@dataclass(frozen=True, slots=True)
class CopyLlmBatchRecord:
    """单条 copy-llm 批跑记录。

    :ivar case_id: 用例 id。
    :vartype case_id: str
    :ivar case_name: 用例中文名。
    :vartype case_name: str
    :ivar passed: 是否通过（DraftCopyJSON 解析成功）。
    :vartype passed: bool
    :ivar result: ③-2 管道原始结果。
    :vartype result: CopyLlmCaseResult
    :ivar violations: 结构化违规（解析失败等）。
    :vartype violations: tuple[Violation, ...]
    """

    case_id: str
    case_name: str
    passed: bool
    result: CopyLlmCaseResult
    violations: tuple[Violation, ...]


@dataclass(frozen=True, slots=True)
class CopyLlmBatchReport:
    """copy-llm 批跑汇总报告。

    :ivar mode: 运行范围模式。
    :vartype mode: CopyLlmBatchModeLiteral
    :ivar dataset_version: case 数据集版本。
    :vartype dataset_version: str
    :ivar total: 参与批跑的 case 数。
    :vartype total: int
    :ivar passed: 通过数。
    :vartype passed: int
    :ivar failed: 失败数。
    :vartype failed: int
    :ivar skipped_llm: 是否跳过 LLM（``skip_llm=True`` 且未使用机械路径）。
    :vartype skipped_llm: bool
    :ivar used_mechanical: 是否使用机械文案生成器。
    :vartype used_mechanical: bool
    :ivar case_ids: 实际运行的 caseId 列表。
    :vartype case_ids: tuple[str, ...]
    :ivar failed_case_ids: 失败 caseId 列表。
    :vartype failed_case_ids: tuple[str, ...]
    :ivar records: 逐 case 记录。
    :vartype records: tuple[CopyLlmBatchRecord, ...]
    """

    mode: CopyLlmBatchModeLiteral
    dataset_version: str
    total: int
    passed: int
    failed: int
    skipped_llm: bool
    used_mechanical: bool
    case_ids: tuple[str, ...]
    failed_case_ids: tuple[str, ...]
    records: tuple[CopyLlmBatchRecord, ...]


async def run_copy_llm_batch_async(
    config: CopyLlmBatchConfig,
    *,
    dataset: HealthTriageDataset | None = None,
    qwen_client: AsyncQwenClient | None = None,  # noqa: F821
) -> CopyLlmBatchReport:
    """异步执行 copy-llm 批跑。

    :param config: 批跑配置。
    :type config: CopyLlmBatchConfig
    :param dataset: 可选已加载数据集。
    :type dataset: HealthTriageDataset | None
    :param qwen_client: 可选共享通义客户端（批内复用连接）。
    :type qwen_client: AsyncQwenClient | None
    :returns: 批跑报告。
    :rtype: CopyLlmBatchReport
    :raises ValueError: 请求的 caseId 在数据集中不存在时抛出。
    """
    resolved_dataset = (
        dataset
        if dataset is not None
        else load_health_triage_dataset(
            config.cases_path
            if config.cases_path is not None
            else default_cases_path(),
        )
    )
    selected_cases = _select_cases(resolved_dataset, config)
    case_ids = tuple(case.case_id for case in selected_cases)

    semaphore = asyncio.Semaphore(config.max_concurrency)
    owns_client = (
        qwen_client is None and not config.skip_llm and not config.use_mechanical
    )
    client = qwen_client

    if owns_client:
        from xiaozhua_health_agent.copy import create_default_qwen_client

        client = create_default_qwen_client()

    try:
        tasks = [
            _run_one_case(
                case,
                semaphore=semaphore,
                qwen_client=client,
                skip_llm=config.skip_llm,
                use_mechanical=config.use_mechanical,
            )
            for case in selected_cases
        ]
        records = list(await asyncio.gather(*tasks))
    finally:
        if owns_client and client is not None:
            await client.aclose()

    passed_count = sum(1 for record in records if record.passed)
    failed_ids = tuple(record.case_id for record in records if not record.passed)

    return CopyLlmBatchReport(
        mode=config.mode,
        dataset_version=resolved_dataset.dataset_version,
        total=len(records),
        passed=passed_count,
        failed=len(records) - passed_count,
        skipped_llm=config.skip_llm,
        used_mechanical=config.use_mechanical,
        case_ids=case_ids,
        failed_case_ids=failed_ids,
        records=tuple(records),
    )


def run_copy_llm_batch(
    config: CopyLlmBatchConfig,
    *,
    dataset: HealthTriageDataset | None = None,
    qwen_client: AsyncQwenClient | None = None,  # noqa: F821
) -> CopyLlmBatchReport:
    """同步包装：在事件循环中执行 ``run_copy_llm_batch_async``。

    :param config: 批跑配置。
    :type config: CopyLlmBatchConfig
    :param dataset: 可选数据集。
    :type dataset: HealthTriageDataset | None
    :param qwen_client: 可选通义客户端。
    :type qwen_client: AsyncQwenClient | None
    :returns: 批跑报告。
    :rtype: CopyLlmBatchReport
    """
    return asyncio.run(
        run_copy_llm_batch_async(
            config,
            dataset=dataset,
            qwen_client=qwen_client,
        ),
    )


def assert_copy_llm_hard_gate(report: CopyLlmBatchReport) -> None:
    """断言 copy-llm 硬门槛：全部 case ``DraftCopyJSON`` 解析成功。

    :param report: 批跑报告。
    :type report: CopyLlmBatchReport
    :raises AssertionError: 存在失败 case 或跳过 LLM 时抛出。
    """
    if report.skipped_llm and not report.used_mechanical:
        msg = (
            "copy-llm 硬门槛要求实际产出文案（skip_llm=False 或 use_mechanical=True）。"
        )
        raise AssertionError(msg)
    if report.failed > 0:
        msg = (
            f"copy-llm 硬门槛未通过：{report.failed}/{report.total} 失败，"
            f"caseIds={list(report.failed_case_ids)}"
        )
        raise AssertionError(msg)


def format_copy_llm_record_line(record: CopyLlmBatchRecord) -> str:
    """格式化单条 copy-llm 记录为一行摘要。

    :param record: 批跑记录。
    :type record: CopyLlmBatchRecord
    :returns: 人类可读一行文本。
    :rtype: str
    """
    status = "PASS" if record.passed else "FAIL"
    parts = [
        f"[{status}]",
        record.case_id,
        f"({record.case_name})",
        f"template={record.result.template_id}",
        f"generator={record.result.generator}",
        f"model={record.result.model}",
    ]
    if record.result.triage is not None:
        parts.append(f"risk={record.result.triage.final_risk_level}")
    if record.result.parse_warnings:
        codes = ",".join(
            warning.code.value for warning in record.result.parse_warnings[:3]
        )
        parts.append(f"parseWarnings=[{codes}]")
    if record.result.mechanical_warnings:
        codes = ",".join(
            warning.code.value for warning in record.result.mechanical_warnings[:3]
        )
        parts.append(f"mechWarnings=[{codes}]")
    if not record.passed and record.violations:
        first = record.violations[0]
        parts.append(f"reason={first.code}: {first.message}")
    return " ".join(parts)


def format_copy_llm_report_summary(report: CopyLlmBatchReport) -> str:
    """格式化 copy-llm 报告头部汇总。

    :param report: 批跑报告。
    :type report: CopyLlmBatchReport
    :returns: 多行汇总文本。
    :rtype: str
    """
    lines = [
        "mode=copy-llm",
        f"scope={report.mode}",
        f"datasetVersion={report.dataset_version}",
        f"total={report.total} passed={report.passed} failed={report.failed}",
        f"skippedLlm={report.skipped_llm}",
        f"usedMechanical={report.used_mechanical}",
        f"caseIds={list(report.case_ids)}",
    ]
    if report.failed_case_ids:
        lines.append(f"failedCaseIds={list(report.failed_case_ids)}")
    return "\n".join(lines)


def format_copy_llm_batch_report(
    report: CopyLlmBatchReport,
    *,
    include_per_case: bool = True,
) -> str:
    """格式化完整 copy-llm 文本报告。

    :param report: 批跑报告。
    :type report: CopyLlmBatchReport
    :param include_per_case: 是否包含逐 case 段。
    :type include_per_case: bool
    :returns: 多行报告文本。
    :rtype: str
    """
    sections: list[str] = [format_copy_llm_report_summary(report), ""]
    if include_per_case:
        sections.append("--- per case ---")
        for record in report.records:
            sections.append(format_copy_llm_record_line(record))
        sections.append("")
    return "\n".join(sections).rstrip() + "\n"


def copy_llm_report_to_dict(report: CopyLlmBatchReport) -> dict[str, Any]:
    """将 copy-llm 报告转为可 JSON 序列化的字典。

    :param report: 批跑报告。
    :type report: CopyLlmBatchReport
    :returns: 嵌套字典（``draft`` 使用 camelCase alias）。
    :rtype: dict[str, Any]
    """
    return {
        "mode": "copy-llm",
        "scope": report.mode,
        "datasetVersion": report.dataset_version,
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "skippedLlm": report.skipped_llm,
        "usedMechanical": report.used_mechanical,
        "caseIds": list(report.case_ids),
        "failedCaseIds": list(report.failed_case_ids),
        "records": [_record_to_dict(record) for record in report.records],
    }


def write_copy_llm_batch_report(
    report: CopyLlmBatchReport,
    stream: TextIO | None = None,
    *,
    include_per_case: bool = True,
) -> None:
    """将 copy-llm 报告写入流（默认 stdout）。

    :param report: 批跑报告。
    :type report: CopyLlmBatchReport
    :param stream: 输出流；省略时为 ``sys.stdout``。
    :type stream: TextIO | None
    :param include_per_case: 是否输出逐 case 段。
    :type include_per_case: bool
    """
    import sys

    target = stream if stream is not None else sys.stdout
    target.write(
        format_copy_llm_batch_report(report, include_per_case=include_per_case),
    )


def _record_to_dict(record: CopyLlmBatchRecord) -> dict[str, Any]:
    """序列化单条批跑记录。

    :param record: 批跑记录。
    :type record: CopyLlmBatchRecord
    :returns: JSON 友好字典。
    :rtype: dict[str, Any]
    """
    result = record.result
    draft_payload: dict[str, Any] | None
    if result.draft is None:
        draft_payload = None
    else:
        draft_payload = result.draft.to_alias_dict()

    return {
        "caseId": record.case_id,
        "caseName": record.case_name,
        "passed": record.passed,
        "templateId": result.template_id,
        "generator": result.generator,
        "model": result.model,
        "errorCode": result.error_code,
        "errorMessage": result.error_message,
        "draft": draft_payload,
        "parseWarnings": [
            {
                "code": warning.code.value,
                "message": warning.message,
                "field": warning.field,
            }
            for warning in result.parse_warnings
        ],
        "mechanicalWarnings": [
            {
                "code": warning.code.value,
                "message": warning.message,
                "field": warning.field,
            }
            for warning in result.mechanical_warnings
        ],
        "violations": [violation.model_dump() for violation in record.violations],
    }


def _select_cases(
    dataset: HealthTriageDataset,
    config: CopyLlmBatchConfig,
) -> list[CaseRecord]:
    """按配置筛选待运行 case 列表。

    :param dataset: 完整数据集。
    :type dataset: HealthTriageDataset
    :param config: 批跑配置。
    :type config: CopyLlmBatchConfig
    :returns: 有序 case 记录列表。
    :rtype: list[CaseRecord]
    :raises ValueError: 指定 caseId 不存在时抛出。
    """
    if config.case_ids:
        id_set = set(config.case_ids)
        selected = [case for case in dataset.cases if case.case_id in id_set]
        missing = id_set - {case.case_id for case in selected}
        if missing:
            msg = f"case 数据集中不存在以下 caseId：{sorted(missing)}"
            raise ValueError(msg)
        order = {case_id: index for index, case_id in enumerate(config.case_ids)}
        selected.sort(key=lambda record: order.get(record.case_id, 0))
        return selected

    if config.mode == CopyLlmBatchMode.FULL.value:
        if len(dataset.cases) != EXPECTED_CASE_COUNT:
            return list(dataset.cases)
        return list(dataset.cases)

    smoke_set = set(COPY_LLM_SMOKE_CASE_IDS)
    selected = [case for case in dataset.cases if case.case_id in smoke_set]
    missing_smoke = smoke_set - {case.case_id for case in selected}
    if missing_smoke:
        msg = f"冒烟子集 case 缺失：{sorted(missing_smoke)}"
        raise ValueError(msg)
    order = {case_id: index for index, case_id in enumerate(COPY_LLM_SMOKE_CASE_IDS)}
    selected.sort(key=lambda record: order[record.case_id])
    return selected


async def _run_one_case(
    case: CaseRecord,
    *,
    semaphore: asyncio.Semaphore,
    qwen_client: AsyncQwenClient | None,  # noqa: F821
    skip_llm: bool,
    use_mechanical: bool,
) -> CopyLlmBatchRecord:
    """在信号量限制下执行单 case copy-llm 管道。

    :param case: case 记录。
    :type case: CaseRecord
    :param semaphore: 并发限制。
    :type semaphore: asyncio.Semaphore
    :param qwen_client: 共享通义客户端。
    :type qwen_client: AsyncQwenClient | None
    :param skip_llm: 是否跳过文案生成（仅 ③-1）。
    :type skip_llm: bool
    :param use_mechanical: 是否使用机械文案路径。
    :type use_mechanical: bool
    :returns: 批跑记录。
    :rtype: CopyLlmBatchRecord
    """
    from xiaozhua_health_agent.copy import generate_draft_copy_async

    agent_input_payload = case.input.model_dump(by_alias=True, mode="json")

    async with semaphore:
        result = await generate_draft_copy_async(
            agent_input_payload,
            qwen_client=qwen_client,
            skip_llm=skip_llm,
            use_mechanical=use_mechanical,
        )

    violations: list[Violation] = []
    if not result.passed:
        violation_code: ViolationCode = ViolationCode.PARSE_ERROR
        if result.error_code == "QWEN_CONFIG":
            violation_code = ViolationCode.EVAL_SKIPPED
        elif result.error_code in {"QWEN_TIMEOUT", "QWEN_API", "QWEN_CLIENT"}:
            violation_code = ViolationCode.EVAL_SKIPPED
        elif result.error_code == "LLM_SKIPPED":
            violation_code = ViolationCode.EVAL_SKIPPED
        elif result.error_code == "PARSE_ERROR":
            violation_code = ViolationCode.PARSE_ERROR
        else:
            violation_code = ViolationCode.FIELD_MISSING

        violations.append(
            Violation(
                code=violation_code.value,
                path="$",
                message=result.error_message or "copy-llm 生成失败",
                severity=ViolationSeverity.HIGH.value,
                field=None,
                domain="schema",
            ),
        )

    passed = result.passed and (use_mechanical or not skip_llm)

    return CopyLlmBatchRecord(
        case_id=case.case_id,
        case_name=case.name,
        passed=passed,
        result=result,
        violations=tuple(violations),
    )
