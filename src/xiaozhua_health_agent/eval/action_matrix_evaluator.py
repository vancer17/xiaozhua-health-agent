"""Action 矩阵批跑评测（机械 + merge 管道 vs fixture）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from xiaozhua_health_agent.eval.action_matrix import (
    ActionMatrixEntry,
    ActionMatrixFixture,
    derive_action_matrix_entry,
    entries_match_derived,
    load_validated_action_matrix,
)
from xiaozhua_health_agent.eval.case_dataset import (
    CaseRecord,
    HealthTriageDataset,
    load_health_triage_dataset,
)
from xiaozhua_health_agent.schemas import ActionItem, AgentOutput

ActionMatrixViolationCodeLiteral: TypeAlias = Literal[
    "ACTION_MATRIX_PRIMARY_FLAG_MISMATCH",
    "ACTION_MATRIX_HINT_MISMATCH",
    "ACTION_MATRIX_PRIMARY_LABEL_MISMATCH",
    "ACTION_MATRIX_PRIMARY_ROUTE_MISMATCH",
    "ACTION_MATRIX_SECONDARY_MISMATCH",
    "ACTION_MATRIX_PIPELINE_ERROR",
]


class ActionMatrixViolationCode(StrEnum):
    """action 矩阵评测违规码。"""

    PRIMARY_FLAG_MISMATCH = "ACTION_MATRIX_PRIMARY_FLAG_MISMATCH"
    HINT_MISMATCH = "ACTION_MATRIX_HINT_MISMATCH"
    PRIMARY_LABEL_MISMATCH = "ACTION_MATRIX_PRIMARY_LABEL_MISMATCH"
    PRIMARY_ROUTE_MISMATCH = "ACTION_MATRIX_PRIMARY_ROUTE_MISMATCH"
    SECONDARY_MISMATCH = "ACTION_MATRIX_SECONDARY_MISMATCH"
    PIPELINE_ERROR = "ACTION_MATRIX_PIPELINE_ERROR"


@dataclass(frozen=True, slots=True)
class ActionMatrixViolation:
    """单条 action 矩阵违规。"""

    code: ActionMatrixViolationCodeLiteral
    case_id: str
    field: str
    message: str


class ActionMatrixEvalRecord(BaseModel):
    """单条 case 的 action 矩阵评测记录。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    case_id: str = Field(alias="caseId")
    case_name: str = Field(alias="caseName")
    passed: bool
    expected: ActionMatrixEntry | None = None
    actual_primary_flag: str | None = Field(default=None, alias="actualPrimaryFlag")
    actual_primary_action_hint: str | None = Field(
        default=None,
        alias="actualPrimaryActionHint",
    )
    actual_primary_action: ActionItem | None = Field(
        default=None,
        alias="actualPrimaryAction",
    )
    actual_secondary_action: ActionItem | None = Field(
        default=None,
        alias="actualSecondaryAction",
    )
    violations: tuple[ActionMatrixViolation, ...] = ()


class ActionMatrixEvalReport(BaseModel):
    """action 矩阵批跑汇总报告。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mode: Literal["action-matrix"] = "action-matrix"
    dataset_version: str = Field(alias="datasetVersion")
    matrix_version: str = Field(alias="matrixVersion")
    pipeline_profile: str = Field(alias="pipelineProfile")
    total: int
    passed: int
    failed: int
    failed_case_ids: list[str] = Field(alias="failedCaseIds")
    records: list[ActionMatrixEvalRecord]
    generated_at: datetime = Field(alias="generatedAt")


def _compare_action_items(
    expected: ActionItem | None,
    actual: ActionItem | None,
    *,
    case_id: str,
    field_prefix: str,
) -> list[ActionMatrixViolation]:
    """比较期望与实际 ``ActionItem``。"""
    violations: list[ActionMatrixViolation] = []
    if expected is None and actual is None:
        return violations
    if expected is None or actual is None:
        violations.append(
            ActionMatrixViolation(
                code=ActionMatrixViolationCode.SECONDARY_MISMATCH.value,
                case_id=case_id,
                field=field_prefix,
                message=f"{field_prefix} 期望与 actual 一方为 null。",
            ),
        )
        return violations
    if expected.label != actual.label:
        violations.append(
            ActionMatrixViolation(
                code=(
                    ActionMatrixViolationCode.PRIMARY_LABEL_MISMATCH.value
                    if field_prefix == "primaryAction"
                    else ActionMatrixViolationCode.SECONDARY_MISMATCH.value
                ),
                case_id=case_id,
                field=f"{field_prefix}.label",
                message=(f"期望 label={expected.label!r}，实际 {actual.label!r}。"),
            ),
        )
    if expected.route != actual.route:
        violations.append(
            ActionMatrixViolation(
                code=(
                    ActionMatrixViolationCode.PRIMARY_ROUTE_MISMATCH.value
                    if field_prefix == "primaryAction"
                    else ActionMatrixViolationCode.SECONDARY_MISMATCH.value
                ),
                case_id=case_id,
                field=f"{field_prefix}.route",
                message=(f"期望 route={expected.route!r}，实际 {actual.route!r}。"),
            ),
        )
    return violations


def evaluate_action_matrix_for_case(
    case: CaseRecord,
    expected: ActionMatrixEntry,
    *,
    output: AgentOutput,
    primary_flag: str,
    primary_action_hint: str,
) -> ActionMatrixEvalRecord:
    """将单条 case 的实际输出与 fixture 期望比对。"""
    violations: list[ActionMatrixViolation] = []

    if primary_flag != expected.primary_flag:
        violations.append(
            ActionMatrixViolation(
                code=ActionMatrixViolationCode.PRIMARY_FLAG_MISMATCH.value,
                case_id=case.case_id,
                field="primaryFlag",
                message=(f"期望 {expected.primary_flag!r}，实际 {primary_flag!r}。"),
            ),
        )
    if primary_action_hint != expected.primary_action_hint:
        violations.append(
            ActionMatrixViolation(
                code=ActionMatrixViolationCode.HINT_MISMATCH.value,
                case_id=case.case_id,
                field="primaryActionHint",
                message=(
                    f"期望 {expected.primary_action_hint!r}，"
                    f"实际 {primary_action_hint!r}。"
                ),
            ),
        )

    violations.extend(
        _compare_action_items(
            expected.primary_action,
            output.primary_action,
            case_id=case.case_id,
            field_prefix="primaryAction",
        ),
    )
    violations.extend(
        _compare_action_items(
            expected.secondary_action,
            output.secondary_action,
            case_id=case.case_id,
            field_prefix="secondaryAction",
        ),
    )

    return ActionMatrixEvalRecord(
        caseId=case.case_id,
        caseName=case.name,
        passed=len(violations) == 0,
        expected=expected,
        actualPrimaryFlag=primary_flag,
        actualPrimaryActionHint=primary_action_hint,
        actualPrimaryAction=output.primary_action,
        actualSecondaryAction=output.secondary_action,
        violations=tuple(violations),
    )


def run_mechanical_merge_for_case(
    case: CaseRecord,
) -> tuple[AgentOutput, str, str]:
    """对单条 case 执行机械文案 + merge 管道。"""
    from xiaozhua_health_agent.copy import (
        MechanicalDraftOptions,
        generate_mechanical_draft_for_parsed,
    )
    from xiaozhua_health_agent.output import merge_agent_output
    from xiaozhua_health_agent.parse import parse_input
    from xiaozhua_health_agent.triage import run_triage_core

    parsed = parse_input(case.input)
    if not parsed.passed or parsed.fact_sheet is None:
        msg = f"case {case.case_id!r} 输入解析失败。"
        raise ValueError(msg)

    triage = run_triage_core(parsed.fact_sheet)
    mechanical = generate_mechanical_draft_for_parsed(
        parsed,
        options=MechanicalDraftOptions(append_missing_mentions=True),
    )
    output = merge_agent_output(triage=triage, draft=mechanical.draft)
    return output, triage.primary_flag, triage.primary_action_hint


def evaluate_action_matrix_for_case_pipeline(
    case: CaseRecord,
    expected: ActionMatrixEntry,
) -> ActionMatrixEvalRecord:
    """运行机械 + merge 管道并评测 action 矩阵。"""
    try:
        output, primary_flag, hint = run_mechanical_merge_for_case(case)
    except ValueError as exc:
        return ActionMatrixEvalRecord(
            caseId=case.case_id,
            caseName=case.name,
            passed=False,
            expected=expected,
            violations=(
                ActionMatrixViolation(
                    code=ActionMatrixViolationCode.PIPELINE_ERROR.value,
                    case_id=case.case_id,
                    field="pipeline",
                    message=str(exc),
                ),
            ),
        )

    return evaluate_action_matrix_for_case(
        case,
        expected,
        output=output,
        primary_flag=primary_flag,
        primary_action_hint=hint,
    )


def run_action_matrix_evaluation(
    dataset: HealthTriageDataset | None = None,
    fixture: ActionMatrixFixture | None = None,
) -> ActionMatrixEvalReport:
    """对全部 case 执行 action 矩阵批跑评测。"""
    resolved_dataset = dataset if dataset is not None else load_health_triage_dataset()
    resolved_fixture = (
        fixture
        if fixture is not None
        else load_validated_action_matrix(dataset=resolved_dataset)
    )
    expected_by_id = resolved_fixture.entry_by_case_id()

    records: list[ActionMatrixEvalRecord] = []
    for case in resolved_dataset.cases:
        expected = expected_by_id[case.case_id]
        records.append(evaluate_action_matrix_for_case_pipeline(case, expected))

    passed = sum(1 for record in records if record.passed)
    failed = len(records) - passed
    failed_ids = [record.case_id for record in records if not record.passed]

    return ActionMatrixEvalReport(
        datasetVersion=resolved_dataset.dataset_version,
        matrixVersion=resolved_fixture.meta.matrix_version,
        pipelineProfile=resolved_fixture.meta.pipeline_profile,
        total=len(records),
        passed=passed,
        failed=failed,
        failedCaseIds=failed_ids,
        records=records,
        generatedAt=datetime.now(tz=UTC),
    )


def assert_action_matrix_hard_gate(
    report: ActionMatrixEvalReport,
    *,
    expected_total: int = 20,
) -> None:
    """断言 action 矩阵批跑硬门槛全绿。"""
    if report.passed != expected_total or report.failed != 0:
        detail = ", ".join(report.failed_case_ids) or "unknown"
        msg = (
            f"action 矩阵硬门槛未全绿：{report.passed}/{report.total} passed；"
            f"failed={detail}"
        )
        raise AssertionError(msg)


def assert_fixture_matches_derived_pipeline(
    fixture: ActionMatrixFixture,
    dataset: HealthTriageDataset,
) -> None:
    """断言 fixture 条目与当前管道推导完全一致（漂移检测）。"""
    derived = [derive_action_matrix_entry(case) for case in dataset.cases]
    diffs = entries_match_derived(fixture.entries, derived)
    if diffs:
        detail = "\n".join(f"  - {line}" for line in diffs)
        msg = f"action 矩阵 fixture 与管道推导不一致：\n{detail}"
        raise AssertionError(msg)


def format_action_matrix_record_line(record: ActionMatrixEvalRecord) -> str:
    """格式化单条 action 矩阵评测为一行摘要。"""
    status = "PASS" if record.passed else "FAIL"
    route = (
        record.actual_primary_action.route
        if record.actual_primary_action is not None
        else None
    )
    return (
        f"[{status}] {record.case_id} ({record.case_name}) "
        f"flag={record.actual_primary_flag} route={route}"
    )


def format_action_matrix_report_summary(report: ActionMatrixEvalReport) -> str:
    """格式化 action 矩阵批跑报告头部汇总。"""
    return (
        f"action-matrix {report.passed}/{report.total} passed "
        f"(matrix={report.matrix_version}, profile={report.pipeline_profile})"
    )
