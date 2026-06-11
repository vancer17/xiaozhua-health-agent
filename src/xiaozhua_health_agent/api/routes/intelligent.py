"""智能对话产品 API（``POST /intelligent``，V1 方案 A · 纯静态占位）。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, status
from fastapi.responses import JSONResponse

from xiaozhua_health_agent.api.app_state import HealthApiAppState
from xiaozhua_health_agent.api.dependencies import require_intelligent_endpoint
from xiaozhua_health_agent.api.http_types import (
    HealthTriageErrorBody,
    HealthTriageRequestBody,
)
from xiaozhua_health_agent.api.intelligent_http_mapping import (
    map_intelligent_validation_to_http_error_async,
)
from xiaozhua_health_agent.intelligent import (
    IntelligentPlaceholderBuildContext,
    IntelligentPlaceholderRequestContext,
    build_intelligent_placeholder_response_async,
    serialize_intelligent_placeholder_response,
    validate_intelligent_request_async,
)

__all__ = [
    "build_intelligent_router",
]

_INTELLIGENT_USER_MESSAGE_KEY: str = "userMessage"
"""可选请求体字段：用户本轮输入（占位回显，不参与分诊）。"""


def build_intelligent_router() -> APIRouter:
    """构造智能对话占位路由器。

    :returns: 包含 ``POST /intelligent`` 的路由器。
    :rtype: APIRouter
    """
    router = APIRouter(tags=["intelligent"])

    @router.post(
        "/intelligent",
        summary="智能对话（占位）",
        description=(
            "V1 方案 A：返回固定模板对话信封，**不**执行健康分诊管道。"
            "入参契约与 ``POST /health`` 相同（``input_schema.v1``）；"
            "``triage`` 固定为 ``null``，``triageStatus`` 为 ``not_run``。"
        ),
        responses={
            status.HTTP_400_BAD_REQUEST: {
                "description": "输入契约校验失败。",
                "model": HealthTriageErrorBody,
            },
            status.HTTP_404_NOT_FOUND: {
                "description": "intelligent 端点未启用。",
                "model": HealthTriageErrorBody,
            },
        },
    )
    async def post_intelligent_placeholder(
        body: HealthTriageRequestBody,
        app_state: Annotated[HealthApiAppState, Depends(require_intelligent_endpoint)],
        x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
    ) -> JSONResponse:
        """返回静态模板占位对话响应（异步）。

        :param body: 符合 input_schema 的 JSON 请求体。
        :type body: HealthTriageRequestBody
        :param app_state: 已启用 intelligent 的应用状态。
        :type app_state: HealthApiAppState
        :param x_session_id: 可选会话标识请求头。
        :type x_session_id: str | None
        :returns: 200 时返回占位对话信封 JSON。
        :rtype: JSONResponse
        :raises HealthTriageHttpError: 入参校验失败或端点未启用时由异常处理器转换。
        """
        _ = app_state  # 占位阶段仅用于依赖注入与开关校验

        case_id_hint = _extract_case_id_hint(body)
        validation = await validate_intelligent_request_async(body)
        if not validation.passed or validation.parsed is None:
            raise await map_intelligent_validation_to_http_error_async(
                validation,
                case_id_hint=case_id_hint,
            )

        user_message = _extract_optional_user_message(body)
        request_context = IntelligentPlaceholderRequestContext(
            session_id_header=x_session_id,
            user_message=user_message,
        )
        build_context = IntelligentPlaceholderBuildContext(
            parsed_input=validation.parsed,
            request_context=request_context,
        )

        placeholder = await build_intelligent_placeholder_response_async(
            build_context,
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content=serialize_intelligent_placeholder_response(placeholder),
        )

    return router


def _extract_case_id_hint(body: Mapping[str, Any]) -> str | None:
    """从请求体尽力读取 ``caseId``（内部辅助）。

    :param body: 原始请求 JSON 对象。
    :type body: collections.abc.Mapping[str, Any]
    :returns: 非空 caseId 或 ``None``。
    :rtype: str | None
    """
    raw = body.get("caseId")
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    return stripped


def _extract_optional_user_message(body: Mapping[str, Any]) -> str | None:
    """从请求体提取可选 ``userMessage`` 字段（内部辅助）。

    :param body: 原始请求 JSON 对象。
    :type body: collections.abc.Mapping[str, Any]
    :returns: 非空用户消息或 ``None``。
    :rtype: str | None
    """
    raw = body.get(_INTELLIGENT_USER_MESSAGE_KEY)
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    return stripped
