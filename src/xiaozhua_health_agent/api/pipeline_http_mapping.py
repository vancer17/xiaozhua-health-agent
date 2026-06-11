"""HTTP 层管道失败映射 — merge / merge_ready / final_schema 专章（WP6）。

将 ``HealthTriagePipelineResult`` 的终止阶段与 ``Violation`` 域映射为 HTTP
状态码与结构化错误类型，使客户端能区分：

- **400**：入参契约失败（``parse``）；
- **422**：入参曾合法，但出站组装/契约不满足（``merge_ready``、``final_schema``）；
- **500**：内部管道失败（``merge``、``guard`` 及其他）。

包外请通过 ``xiaozhua_health_agent.api`` 门面导入公开符号。
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from fastapi import status

from xiaozhua_health_agent.api.http_types import HealthTriageErrorBody
from xiaozhua_health_agent.eval import Violation, ViolationDomain
from xiaozhua_health_agent.pipeline import (
    HealthTriagePipelineResult,
    HealthTriagePipelineStage,
    HealthTriagePipelineStageLiteral,
)

__all__ = [
    "ERROR_INPUT_VALIDATION",
    "ERROR_OUTPUT_MERGE_FAILED",
    "ERROR_OUTPUT_NOT_MERGE_READY",
    "ERROR_OUTPUT_SCHEMA_VALIDATION_FAILED",
    "ERROR_PIPELINE_FAILED",
    "HTTP_STATUS_BAD_REQUEST",
    "HTTP_STATUS_INTERNAL_SERVER_ERROR",
    "HTTP_STATUS_UNPROCESSABLE_ENTITY",
    "PipelineFailureHttpMapping",
    "build_health_triage_error_body_from_pipeline_result",
    "build_health_triage_error_body_from_pipeline_result_async",
    "resolve_pipeline_failure_http_mapping",
    "resolve_pipeline_failure_http_mapping_async",
]

ERROR_INPUT_VALIDATION: Final[str] = "input_validation_failed"
"""``stage=parse`` 时的错误类型标识。"""

ERROR_OUTPUT_MERGE_FAILED: Final[str] = "output_merge_failed"
"""``stage=merge`` 时的错误类型标识（内部组装不一致，500）。"""

ERROR_OUTPUT_NOT_MERGE_READY: Final[str] = "output_not_merge_ready"
"""``stage=merge_ready`` 时的错误类型标识（422）。"""

ERROR_OUTPUT_SCHEMA_VALIDATION_FAILED: Final[str] = "output_schema_validation_failed"
"""``stage=final_schema`` 且违规均为 ``schema`` 域时的错误类型标识（422）。"""

ERROR_PIPELINE_FAILED: Final[str] = "pipeline_failed"
"""其他管道阶段或无法细分的失败（默认 500）。"""

HTTP_STATUS_BAD_REQUEST: Final[int] = status.HTTP_400_BAD_REQUEST
HTTP_STATUS_UNPROCESSABLE_ENTITY: Final[int] = status.HTTP_422_UNPROCESSABLE_CONTENT
"""出站契约/merge-ready 失败时使用的 422 状态码。"""
HTTP_STATUS_INTERNAL_SERVER_ERROR: Final[int] = status.HTTP_500_INTERNAL_SERVER_ERROR


@dataclass(frozen=True, slots=True)
class PipelineFailureHttpMapping:
    """管道失败对应的 HTTP 映射结果（纯数据，不含异常）。

    :ivar status_code: 建议的 HTTP 状态码。
    :vartype status_code: int
    :ivar error_kind: 机器可读错误类型，写入 ``HealthTriageErrorBody.error``。
    :vartype error_kind: str
    :ivar message: 人类可读说明；通常来自管道 ``error_message`` 或阶段默认文案。
    :vartype message: str
    """

    status_code: int
    error_kind: str
    message: str


def resolve_pipeline_failure_http_mapping(
    *,
    stage: HealthTriagePipelineStageLiteral,
    violations: Sequence[Violation] = (),
    error_message: str | None = None,
) -> PipelineFailureHttpMapping:
    """根据管道终止阶段与违规项解析 HTTP 状态码与错误类型。

    映射规则（WP5 merge / FinalSchemaCheck 闭环 · HTTP 层）：

    - ``parse`` → 400 / ``input_validation_failed``；
    - ``merge_ready`` → 422 / ``output_not_merge_ready``；
    - ``final_schema`` → 若 ``violations`` 为空或全部为 ``schema`` 域 → 422 /
      ``output_schema_validation_failed``；否则 → 500 / ``pipeline_failed``；
    - ``merge`` → 500 / ``output_merge_failed``；
    - 其他阶段（``guard``、``triage`` 等）→ 500 / ``pipeline_failed``。

    :param stage: 管道终止阶段。
    :type stage: HealthTriagePipelineStageLiteral
    :param violations: 结构化违规列表；``final_schema`` 阶段用于区分 422/500。
    :type violations: collections.abc.Sequence[Violation]
    :param error_message: 管道级错误说明；省略时使用阶段默认文案。
    :type error_message: str | None
    :returns: HTTP 映射三元组（状态码、错误类型、说明）。
    :rtype: PipelineFailureHttpMapping
    """
    if stage == HealthTriagePipelineStage.PARSE:
        return PipelineFailureHttpMapping(
            status_code=HTTP_STATUS_BAD_REQUEST,
            error_kind=ERROR_INPUT_VALIDATION,
            message=error_message or _default_message_for_stage(stage),
        )

    if stage == HealthTriagePipelineStage.MERGE_READY:
        return PipelineFailureHttpMapping(
            status_code=HTTP_STATUS_UNPROCESSABLE_ENTITY,
            error_kind=ERROR_OUTPUT_NOT_MERGE_READY,
            message=error_message or _default_message_for_stage(stage),
        )

    if stage == HealthTriagePipelineStage.FINAL_SCHEMA:
        if _violations_are_schema_only(violations):
            return PipelineFailureHttpMapping(
                status_code=HTTP_STATUS_UNPROCESSABLE_ENTITY,
                error_kind=ERROR_OUTPUT_SCHEMA_VALIDATION_FAILED,
                message=error_message or _default_message_for_stage(stage),
            )
        return PipelineFailureHttpMapping(
            status_code=HTTP_STATUS_INTERNAL_SERVER_ERROR,
            error_kind=ERROR_PIPELINE_FAILED,
            message=error_message or _default_message_for_stage(stage),
        )

    if stage == HealthTriagePipelineStage.MERGE:
        return PipelineFailureHttpMapping(
            status_code=HTTP_STATUS_INTERNAL_SERVER_ERROR,
            error_kind=ERROR_OUTPUT_MERGE_FAILED,
            message=error_message or _default_message_for_stage(stage),
        )

    return PipelineFailureHttpMapping(
        status_code=HTTP_STATUS_INTERNAL_SERVER_ERROR,
        error_kind=ERROR_PIPELINE_FAILED,
        message=error_message or _default_message_for_stage(stage),
    )


async def resolve_pipeline_failure_http_mapping_async(
    *,
    stage: HealthTriagePipelineStageLiteral,
    violations: Sequence[Violation] = (),
    error_message: str | None = None,
) -> PipelineFailureHttpMapping:
    """异步解析管道失败 HTTP 映射（CPU 逻辑委托线程池，避免阻塞事件循环）。

    :param stage: 管道终止阶段。
    :type stage: HealthTriagePipelineStageLiteral
    :param violations: 结构化违规列表。
    :type violations: collections.abc.Sequence[Violation]
    :param error_message: 管道级错误说明。
    :type error_message: str | None
    :returns: HTTP 映射结果。
    :rtype: PipelineFailureHttpMapping
    """

    def _resolve_sync() -> PipelineFailureHttpMapping:
        """在线程池中执行同步映射（闭包）。

        :returns: HTTP 映射结果。
        :rtype: PipelineFailureHttpMapping
        """
        return resolve_pipeline_failure_http_mapping(
            stage=stage,
            violations=violations,
            error_message=error_message,
        )

    return await asyncio.to_thread(_resolve_sync)


def build_health_triage_error_body_from_pipeline_result(
    result: HealthTriagePipelineResult,
    *,
    mapping: PipelineFailureHttpMapping | None = None,
) -> HealthTriageErrorBody:
    """由管道失败结果构造 HTTP 错误响应体。

    :param result: ``passed=False`` 的管道执行结果。
    :type result: HealthTriagePipelineResult
    :param mapping: 可选预计算的 HTTP 映射；省略时按 ``result`` 字段解析。
    :type mapping: PipelineFailureHttpMapping | None
    :returns: 与 OpenAPI ``HealthTriageErrorBody`` 对齐的响应 DTO。
    :rtype: HealthTriageErrorBody
    :raises ValueError: ``result.passed`` 为 ``True`` 时抛出。
    """
    if result.passed:
        msg = (
            "build_health_triage_error_body_from_pipeline_result "
            "仅用于 passed=False 的结果。"
        )
        raise ValueError(msg)

    resolved_mapping = mapping or resolve_pipeline_failure_http_mapping(
        stage=result.stage,
        violations=result.violations,
        error_message=result.error_message,
    )

    return HealthTriageErrorBody(
        error=resolved_mapping.error_kind,
        caseId=result.case_id,
        stage=result.stage,
        message=resolved_mapping.message,
        violations=list(result.violations),
    )


async def build_health_triage_error_body_from_pipeline_result_async(
    result: HealthTriagePipelineResult,
    *,
    mapping: PipelineFailureHttpMapping | None = None,
) -> HealthTriageErrorBody:
    """异步构造 HTTP 错误响应体。

    :param result: ``passed=False`` 的管道执行结果。
    :type result: HealthTriagePipelineResult
    :param mapping: 可选预计算的 HTTP 映射。
    :type mapping: PipelineFailureHttpMapping | None
    :returns: 错误响应 DTO。
    :rtype: HealthTriageErrorBody
    :raises ValueError: ``result.passed`` 为 ``True`` 时抛出。
    """

    def _build_sync() -> HealthTriageErrorBody:
        """在线程池中执行同步构造（闭包）。

        :returns: 错误响应 DTO。
        :rtype: HealthTriageErrorBody
        """
        return build_health_triage_error_body_from_pipeline_result(
            result,
            mapping=mapping,
        )

    return await asyncio.to_thread(_build_sync)


def _violations_are_schema_only(violations: Sequence[Violation]) -> bool:
    """判断违规列表是否全部为 ``schema`` 域（或为空）。

    ``final_schema`` 阶段空违规仍视为出站契约问题，映射 422。

    :param violations: 管道结果中的违规项。
    :type violations: collections.abc.Sequence[Violation]
    :returns: 全部为 ``schema`` 域或无违规时返回 ``True``。
    :rtype: bool
    """
    if len(violations) == 0:
        return True

    schema_domain = ViolationDomain.SCHEMA.value
    return all(item.domain == schema_domain for item in violations)


def _default_message_for_stage(stage: HealthTriagePipelineStageLiteral) -> str:
    """为缺少 ``error_message`` 的结果生成默认中文说明（内部辅助）。

    :param stage: 管道终止阶段。
    :type stage: HealthTriagePipelineStageLiteral
    :returns: 阶段默认说明。
    :rtype: str
    """
    if stage == HealthTriagePipelineStage.PARSE:
        return "输入契约校验失败，未进入分诊管道。"
    if stage == HealthTriagePipelineStage.MERGE:
        return "合并分诊结论与文案时失败。"
    if stage == HealthTriagePipelineStage.MERGE_READY:
        return "文案草稿未满足 merge-ready 契约，未进入合并。"
    if stage == HealthTriagePipelineStage.FINAL_SCHEMA:
        return "出站 output_schema 校验失败。"
    return "健康分诊管道执行失败。"
