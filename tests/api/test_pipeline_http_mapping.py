"""HTTP 层 merge / final_schema 管道失败映射测试。"""

from __future__ import annotations

import pytest

from xiaozhua_health_agent.api import (
    ERROR_OUTPUT_MERGE_FAILED,
    ERROR_OUTPUT_NOT_MERGE_READY,
    ERROR_OUTPUT_SCHEMA_VALIDATION_FAILED,
    ERROR_PIPELINE_FAILED,
    HTTP_STATUS_INTERNAL_SERVER_ERROR,
    HTTP_STATUS_UNPROCESSABLE_ENTITY,
    map_pipeline_result_to_http_error,
    map_pipeline_result_to_http_error_async,
    resolve_pipeline_failure_http_mapping,
    resolve_pipeline_failure_http_mapping_async,
)
from xiaozhua_health_agent.eval import (
    Violation,
    ViolationCode,
    ViolationDomain,
    ViolationSeverity,
)
from xiaozhua_health_agent.pipeline import (
    HealthTriagePipelineResult,
    HealthTriagePipelineStage,
)


def _schema_violation(*, path: str = "title") -> Violation:
    """构造一条 ``schema`` 域违规（测试辅助）。

    :param path: JSON 字段路径。
    :type path: str
    :returns: 违规项。
    :rtype: Violation
    """
    return Violation(
        code=ViolationCode.FIELD_MISSING.value,
        domain=ViolationDomain.SCHEMA.value,
        path=path,
        field=path.split(".")[0],
        message=f"缺少字段 {path}。",
        severity=ViolationSeverity.HIGH.value,
    )


def _guard_violation() -> Violation:
    """构造一条 ``guard`` 域违规（测试辅助）。

    :returns: 违规项。
    :rtype: Violation
    """
    return Violation(
        code=ViolationCode.FORBIDDEN_PATTERN_HIT.value,
        domain=ViolationDomain.GUARD.value,
        path="summary",
        field="summary",
        message="禁止词命中。",
        severity=ViolationSeverity.HIGH.value,
    )


def _pipeline_failure_result(
    *,
    stage: str,
    violations: tuple[Violation, ...] = (),
    error_message: str | None = None,
) -> HealthTriagePipelineResult:
    """构造最小 ``passed=False`` 管道结果（测试辅助）。

    :param stage: 终止阶段。
    :type stage: str
    :param violations: 违规列表。
    :type violations: tuple[Violation, ...]
    :param error_message: 可选错误说明。
    :type error_message: str | None
    :returns: 管道失败结果。
    :rtype: HealthTriagePipelineResult
    """
    return HealthTriagePipelineResult(
        passed=False,
        case_id="test-case",
        stage=stage,  # type: ignore[arg-type]
        output=None,
        violations=violations,
        error_message=error_message,
    )


def test_merge_stage_maps_to_500_and_output_merge_failed() -> None:
    """``stage=merge`` 应映射 500 与 ``output_merge_failed``。"""
    mapping = resolve_pipeline_failure_http_mapping(
        stage=HealthTriagePipelineStage.MERGE,
        violations=(_schema_violation(path="safetyNotice"),),
    )

    assert mapping.status_code == HTTP_STATUS_INTERNAL_SERVER_ERROR
    assert mapping.error_kind == ERROR_OUTPUT_MERGE_FAILED


def test_merge_ready_stage_maps_to_422() -> None:
    """``stage=merge_ready`` 应映射 422 与 ``output_not_merge_ready``。"""
    mapping = resolve_pipeline_failure_http_mapping(
        stage=HealthTriagePipelineStage.MERGE_READY,
        violations=(_schema_violation(),),
    )

    assert mapping.status_code == HTTP_STATUS_UNPROCESSABLE_ENTITY
    assert mapping.error_kind == ERROR_OUTPUT_NOT_MERGE_READY


def test_final_schema_schema_only_violations_maps_to_422() -> None:
    """``final_schema`` 且违规均为 schema 域时应映射 422。"""
    mapping = resolve_pipeline_failure_http_mapping(
        stage=HealthTriagePipelineStage.FINAL_SCHEMA,
        violations=(_schema_violation(path="evidence"),),
    )

    assert mapping.status_code == HTTP_STATUS_UNPROCESSABLE_ENTITY
    assert mapping.error_kind == ERROR_OUTPUT_SCHEMA_VALIDATION_FAILED


def test_final_schema_empty_violations_maps_to_422() -> None:
    """``final_schema`` 无违规列表时仍视为出站契约问题（422）。"""
    mapping = resolve_pipeline_failure_http_mapping(
        stage=HealthTriagePipelineStage.FINAL_SCHEMA,
        violations=(),
    )

    assert mapping.status_code == HTTP_STATUS_UNPROCESSABLE_ENTITY
    assert mapping.error_kind == ERROR_OUTPUT_SCHEMA_VALIDATION_FAILED


def test_final_schema_mixed_violations_maps_to_500() -> None:
    """``final_schema`` 含非 schema 域违规时应映射 500。"""
    mapping = resolve_pipeline_failure_http_mapping(
        stage=HealthTriagePipelineStage.FINAL_SCHEMA,
        violations=(_schema_violation(), _guard_violation()),
    )

    assert mapping.status_code == HTTP_STATUS_INTERNAL_SERVER_ERROR
    assert mapping.error_kind == ERROR_PIPELINE_FAILED


def test_guard_stage_maps_to_500_pipeline_failed() -> None:
    """``stage=guard`` 应映射通用 500。"""
    mapping = resolve_pipeline_failure_http_mapping(
        stage=HealthTriagePipelineStage.GUARD,
        violations=(_guard_violation(),),
    )

    assert mapping.status_code == HTTP_STATUS_INTERNAL_SERVER_ERROR
    assert mapping.error_kind == ERROR_PIPELINE_FAILED


def test_map_pipeline_result_to_http_error_carries_violations() -> None:
    """``map_pipeline_result_to_http_error`` 应保留 violations 于响应体。"""
    violation = _schema_violation(path="confidence")
    result = _pipeline_failure_result(
        stage=HealthTriagePipelineStage.FINAL_SCHEMA,
        violations=(violation,),
        error_message="出站校验失败。",
    )

    http_error = map_pipeline_result_to_http_error(result)

    assert http_error.status_code == HTTP_STATUS_UNPROCESSABLE_ENTITY
    assert http_error.body.error == ERROR_OUTPUT_SCHEMA_VALIDATION_FAILED
    assert http_error.body.stage == HealthTriagePipelineStage.FINAL_SCHEMA
    assert len(http_error.body.violations) == 1
    assert http_error.body.violations[0].path == "confidence"


def test_map_pipeline_result_to_http_error_rejects_passed_result() -> None:
    """``passed=True`` 的结果不得映射为 HTTP 错误。"""
    result = HealthTriagePipelineResult(
        passed=True,
        case_id="ok",
        stage=HealthTriagePipelineStage.COMPLETED,
        output=None,
    )

    with pytest.raises(ValueError, match="passed=False"):
        map_pipeline_result_to_http_error(result)


@pytest.mark.asyncio
async def test_resolve_mapping_async_matches_sync() -> None:
    """异步映射应与同步结果一致。"""
    sync_mapping = resolve_pipeline_failure_http_mapping(
        stage=HealthTriagePipelineStage.MERGE,
    )
    async_mapping = await resolve_pipeline_failure_http_mapping_async(
        stage=HealthTriagePipelineStage.MERGE,
    )

    assert async_mapping == sync_mapping


@pytest.mark.asyncio
async def test_map_pipeline_result_to_http_error_async() -> None:
    """异步 HTTP 异常映射应返回正确状态码与 error 类型。"""
    result = _pipeline_failure_result(
        stage=HealthTriagePipelineStage.MERGE_READY,
    )

    http_error = await map_pipeline_result_to_http_error_async(result)

    assert http_error.status_code == HTTP_STATUS_UNPROCESSABLE_ENTITY
    assert http_error.body.error == ERROR_OUTPUT_NOT_MERGE_READY
