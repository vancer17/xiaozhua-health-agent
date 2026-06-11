"""运维探针路由（``/healthz``、``/readyz``，WP6 阶段 2）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from xiaozhua_health_agent.api.app_state import HealthApiAppState
from xiaozhua_health_agent.api.dependencies import get_health_api_app_state
from xiaozhua_health_agent.api.http_types import LivenessResponse, ReadinessResponse

__all__ = [
    "build_ops_router",
]


def build_ops_router() -> APIRouter:
    """构造运维探针路由器。

    :returns: 仅包含存活/就绪检查的路由器。
    :rtype: APIRouter
    """
    router = APIRouter(tags=["ops"])

    @router.get(
        "/healthz",
        response_model=LivenessResponse,
        summary="存活探针",
        description="进程存活检查；不验证知识包或管道逻辑。",
    )
    async def get_liveness() -> LivenessResponse:
        """返回进程存活状态（Liveness）。

        :returns: 固定 ``status=ok``。
        :rtype: LivenessResponse
        """
        return LivenessResponse(status="ok")

    @router.get(
        "/readyz",
        response_model=ReadinessResponse,
        summary="就绪探针",
        description="服务是否可接收 ``POST /health`` 分诊流量。",
        responses={
            status.HTTP_503_SERVICE_UNAVAILABLE: {
                "description": "服务未就绪。",
            },
        },
    )
    async def get_readiness(
        app_state: Annotated[HealthApiAppState, Depends(get_health_api_app_state)],
    ) -> JSONResponse:
        """返回服务就绪状态（Readiness）。

        :param app_state: 注入的应用共享状态。
        :type app_state: HealthApiAppState
        :returns: 200 就绪或 503 未就绪 JSON 响应。
        :rtype: JSONResponse
        """
        input_lex_required = app_state.pipeline_options.input_lex_enabled
        input_lex_ready = (
            app_state.input_lex_bundle_ready
            if input_lex_required
            else True
        )
        ready = (
            app_state.service_ready
            and app_state.startup_error is None
            and input_lex_ready
        )
        message = app_state.startup_error or ""
        if not ready and not message:
            if input_lex_required and not input_lex_ready:
                message = "KB-INPUT-LEX 词表尚未就绪。"
            else:
                message = "服务尚未完成启动。"

        payload = ReadinessResponse(
            ready=ready,
            copyBundleReady=app_state.copy_bundle_ready,
            inputLexBundleReady=input_lex_ready,
            message=message,
        )
        status_code = (
            status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return JSONResponse(
            status_code=status_code,
            content=payload.model_dump(by_alias=True, mode="json"),
        )

    return router
