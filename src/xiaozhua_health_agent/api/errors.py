"""HTTP 错误映射（管道结果 → 状态码与响应体，WP6 阶段 2）。"""

from __future__ import annotations

from dataclasses import dataclass

from xiaozhua_health_agent.api.http_types import HealthTriageErrorBody
from xiaozhua_health_agent.api.pipeline_http_mapping import (
    build_health_triage_error_body_from_pipeline_result,
    build_health_triage_error_body_from_pipeline_result_async,
    resolve_pipeline_failure_http_mapping,
    resolve_pipeline_failure_http_mapping_async,
)
from xiaozhua_health_agent.pipeline import HealthTriagePipelineResult

__all__ = [
    "HealthTriageHttpError",
    "map_pipeline_result_to_http_error",
    "map_pipeline_result_to_http_error_async",
]


@dataclass(frozen=True, slots=True)
class HealthTriageHttpError(Exception):
    """可映射为 HTTP 响应的管道失败异常。

    :ivar status_code: HTTP 状态码。
    :vartype status_code: int
    :ivar body: 结构化错误响应体。
    :vartype body: HealthTriageErrorBody
    """

    status_code: int
    body: HealthTriageErrorBody

    def __str__(self) -> str:
        """返回错误说明摘要。

        :returns: 包含 caseId 与 stage 的简短文本。
        :rtype: str
        """
        return (
            f"HealthTriageHttpError(status={self.status_code}, "
            f"caseId={self.body.case_id}, stage={self.body.stage})"
        )


def map_pipeline_result_to_http_error(
    result: HealthTriagePipelineResult,
) -> HealthTriageHttpError:
    """将未通过的管道结果映射为 HTTP 错误异常（同步）。

    HTTP 状态码与 ``error`` 类型由 ``pipeline_http_mapping`` 按阶段与
    ``violations`` 域解析（``merge`` → 500、``final_schema`` schema-only → 422 等）。

    :param result: ``passed=False`` 的管道执行结果。
    :type result: HealthTriagePipelineResult
    :returns: 含状态码与响应体的异常，供异常处理器抛出。
    :rtype: HealthTriageHttpError
    :raises ValueError: ``result.passed`` 为 ``True`` 时抛出。
    """
    if result.passed:
        msg = "map_pipeline_result_to_http_error 仅用于 passed=False 的结果。"
        raise ValueError(msg)

    mapping = resolve_pipeline_failure_http_mapping(
        stage=result.stage,
        violations=result.violations,
        error_message=result.error_message,
    )
    body = build_health_triage_error_body_from_pipeline_result(
        result,
        mapping=mapping,
    )
    return HealthTriageHttpError(status_code=mapping.status_code, body=body)


async def map_pipeline_result_to_http_error_async(
    result: HealthTriagePipelineResult,
) -> HealthTriageHttpError:
    """将未通过的管道结果映射为 HTTP 错误异常（异步，供 ``async`` 路由使用）。

    :param result: ``passed=False`` 的管道执行结果。
    :type result: HealthTriagePipelineResult
    :returns: 含状态码与响应体的异常。
    :rtype: HealthTriageHttpError
    :raises ValueError: ``result.passed`` 为 ``True`` 时抛出。
    """
    if result.passed:
        msg = "map_pipeline_result_to_http_error_async 仅用于 passed=False 的结果。"
        raise ValueError(msg)

    mapping = await resolve_pipeline_failure_http_mapping_async(
        stage=result.stage,
        violations=result.violations,
        error_message=result.error_message,
    )
    body = await build_health_triage_error_body_from_pipeline_result_async(
        result,
        mapping=mapping,
    )
    return HealthTriageHttpError(status_code=mapping.status_code, body=body)
