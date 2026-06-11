"""宠物健康分诊产品 API（``POST /health``，WP6 阶段 2 · 机械门面）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from xiaozhua_health_agent.api.app_state import HealthApiAppState
from xiaozhua_health_agent.api.dependencies import require_service_ready
from xiaozhua_health_agent.api.errors import map_pipeline_result_to_http_error_async
from xiaozhua_health_agent.api.http_types import (
    HealthTriageErrorBody,
    HealthTriageRequestBody,
)
from xiaozhua_health_agent.api.serialization import serialize_agent_output
from xiaozhua_health_agent.pipeline import run_health_triage_async

__all__ = [
    "build_health_triage_router",
]


def build_health_triage_router() -> APIRouter:
    """构造健康分诊产品路由器。

    :returns: 包含 ``POST /health`` 的路由器。
    :rtype: APIRouter
    """
    router = APIRouter(tags=["health-triage"])

    @router.post(
        "/health",
        summary="健康/兽医分诊",
        description=(
            "消费 ``input_schema.v1`` 快照，经机械路径管道产出完整 "
            "``output_schema.v1`` 结构化 JSON。V1 阶段固定机械文案，不调用 LLM。"
        ),
        responses={
            status.HTTP_400_BAD_REQUEST: {
                "description": "输入契约校验失败（stage=parse）。",
                "model": HealthTriageErrorBody,
            },
            status.HTTP_422_UNPROCESSABLE_CONTENT: {
                "description": (
                    "入参曾合法，但 merge-ready 或出站 output_schema 未满足（"
                    "stage=merge_ready / final_schema）。"
                ),
                "model": HealthTriageErrorBody,
            },
            status.HTTP_500_INTERNAL_SERVER_ERROR: {
                "description": "管道内部失败（stage=merge / guard 等）。",
                "model": HealthTriageErrorBody,
            },
            status.HTTP_503_SERVICE_UNAVAILABLE: {
                "description": "服务未就绪。",
                "model": HealthTriageErrorBody,
            },
        },
    )
    async def post_health_triage(
        body: HealthTriageRequestBody,
        app_state: Annotated[HealthApiAppState, Depends(require_service_ready)],
    ) -> JSONResponse:
        """执行单次健康/兽医分诊（机械管道，异步）。

        :param body: 符合 input_schema 的 JSON 请求体。
        :type body: HealthTriageRequestBody
        :param app_state: 已就绪的应用共享状态（含预加载知识包）。
        :type app_state: HealthApiAppState
        :returns: 200 时返回 ``AgentOutput`` JSON；失败时返回结构化错误体。
        :rtype: JSONResponse
        :raises HealthTriageHttpError: 管道失败或服务未就绪时由异常处理器转换。
        """
        pipeline_result = await run_health_triage_async(
            body,
            options=app_state.resolved_pipeline_options(),
            copy_bundle=app_state.copy_bundle,
        )

        if pipeline_result.passed and pipeline_result.output is not None:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=serialize_agent_output(pipeline_result.output),
            )

        raise await map_pipeline_result_to_http_error_async(pipeline_result)

    return router
