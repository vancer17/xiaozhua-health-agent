"""``POST /intelligent`` HTTP 错误与校验映射（方案 A 占位）。"""

from __future__ import annotations

import asyncio

from xiaozhua_health_agent.api.errors import HealthTriageHttpError
from xiaozhua_health_agent.api.http_types import HealthTriageErrorBody
from xiaozhua_health_agent.eval import ValidationResult, Violation
from xiaozhua_health_agent.schemas import AgentInput

__all__ = [
    "ERROR_INTELLIGENT_DISABLED",
    "ERROR_INTELLIGENT_INPUT_VALIDATION",
    "HTTP_STATUS_NOT_FOUND",
    "build_intelligent_disabled_http_error",
    "build_intelligent_input_validation_http_error",
    "map_intelligent_validation_to_http_error",
    "map_intelligent_validation_to_http_error_async",
]

HTTP_STATUS_NOT_FOUND: int = 404
"""intelligent 端点未启用时的 HTTP 状态码。"""

ERROR_INTELLIGENT_DISABLED: str = "intelligent_endpoint_disabled"
"""intelligent 功能开关关闭时的错误类型。"""

ERROR_INTELLIGENT_INPUT_VALIDATION: str = "input_validation_failed"
"""入参契约校验失败时的错误类型（与 ``/health`` 对齐）。"""


def build_intelligent_disabled_http_error() -> HealthTriageHttpError:
    """构造 intelligent 端点未启用的 HTTP 错误。

    :returns: 404 结构化错误异常。
    :rtype: HealthTriageHttpError
    """
    body = HealthTriageErrorBody(
        error=ERROR_INTELLIGENT_DISABLED,
        caseId="unknown",
        stage="parse",
        message="智能对话入口未启用。",
        violations=[],
    )
    return HealthTriageHttpError(status_code=HTTP_STATUS_NOT_FOUND, body=body)


def build_intelligent_input_validation_http_error(
    *,
    violations: list[Violation],
    case_id: str,
) -> HealthTriageHttpError:
    """构造 intelligent 入参校验失败的 HTTP 错误。

    :param violations: 契约违规列表。
    :type violations: list[Violation]
    :param case_id: 尽力读取的 caseId。
    :type case_id: str
    :returns: 400 结构化错误异常。
    :rtype: HealthTriageHttpError
    """
    body = HealthTriageErrorBody(
        error=ERROR_INTELLIGENT_INPUT_VALIDATION,
        caseId=case_id,
        stage="parse",
        message="请求体不符合 input_schema.v1 契约。",
        violations=violations,
    )
    return HealthTriageHttpError(status_code=400, body=body)


def map_intelligent_validation_to_http_error(
    validation: ValidationResult[AgentInput],
    *,
    case_id_hint: str | None = None,
) -> HealthTriageHttpError:
    """将未通过的入参校验结果映射为 HTTP 错误（同步）。

    :param validation: ``validate_intelligent_request`` 产出。
    :type validation: ValidationResult[AgentInput]
    :param case_id_hint: 路由层从原始 JSON 尽力读取的 caseId。
    :type case_id_hint: str | None
    :returns: 400 错误异常。
    :rtype: HealthTriageHttpError
    :raises ValueError: ``validation.passed`` 为 ``True`` 时抛出。
    """
    if validation.passed:
        msg = "map_intelligent_validation_to_http_error 要求 validation.passed=False"
        raise ValueError(msg)

    case_id = _resolve_case_id_for_validation(
        validation,
        case_id_hint=case_id_hint,
    )
    return build_intelligent_input_validation_http_error(
        violations=list(validation.violations),
        case_id=case_id,
    )


async def map_intelligent_validation_to_http_error_async(
    validation: ValidationResult[AgentInput],
    *,
    case_id_hint: str | None = None,
) -> HealthTriageHttpError:
    """将未通过的入参校验结果映射为 HTTP 错误（异步包装）。

    :param validation: ``validate_intelligent_request_async`` 产出。
    :type validation: ValidationResult[AgentInput]
    :param case_id_hint: 路由层从原始 JSON 尽力读取的 caseId。
    :type case_id_hint: str | None
    :returns: 400 错误异常。
    :rtype: HealthTriageHttpError
    :raises ValueError: ``validation.passed`` 为 ``True`` 时抛出。
    """

    def _map_in_thread() -> HealthTriageHttpError:
        """在线程池中执行错误映射（闭包）。

        :returns: HTTP 错误异常。
        :rtype: HealthTriageHttpError
        """
        return map_intelligent_validation_to_http_error(
            validation,
            case_id_hint=case_id_hint,
        )

    return await asyncio.to_thread(_map_in_thread)


def _resolve_case_id_for_validation(
    validation: ValidationResult[AgentInput],
    *,
    case_id_hint: str | None,
) -> str:
    """解析错误响应中使用的 caseId（内部辅助）。

    :param validation: 未通过的校验结果。
    :type validation: ValidationResult[AgentInput]
    :param case_id_hint: 原始请求体中的 caseId 提示。
    :type case_id_hint: str | None
    :returns: caseId 字符串；无法提取时返回 ``unknown``。
    :rtype: str
    """
    if validation.parsed is not None:
        return validation.parsed.case_id

    if case_id_hint is not None:
        stripped = case_id_hint.strip()
        if stripped:
            return stripped

    return "unknown"
