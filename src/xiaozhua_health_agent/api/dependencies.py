"""FastAPI 依赖注入（WP6 阶段 2）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from xiaozhua_health_agent.api.app_state import HealthApiAppState
from xiaozhua_health_agent.api.errors import HealthTriageHttpError
from xiaozhua_health_agent.api.http_types import HealthTriageErrorBody
from xiaozhua_health_agent.api.intelligent_http_mapping import (
    build_intelligent_disabled_http_error,
)

__all__ = [
    "get_health_api_app_state",
    "require_intelligent_endpoint",
    "require_service_ready",
]


def get_health_api_app_state(request: Request) -> HealthApiAppState:
    """从 ``FastAPI`` 应用状态读取共享运行时容器。

    :param request: 当前 HTTP 请求。
    :type request: Request
    :returns: 挂载在 ``app.state.health_api`` 上的状态对象。
    :rtype: HealthApiAppState
    :raises RuntimeError: 应用未通过 ``create_app`` 初始化状态时抛出。
    """
    state = getattr(request.app.state, "health_api", None)
    if state is None:
        msg = "HealthApiAppState 未初始化；请通过 create_app() 创建应用。"
        raise RuntimeError(msg)
    if not isinstance(state, HealthApiAppState):
        msg = "app.state.health_api 类型不是 HealthApiAppState。"
        raise RuntimeError(msg)
    return state


async def require_service_ready(
    app_state: Annotated[HealthApiAppState, Depends(get_health_api_app_state)],
) -> HealthApiAppState:
    """依赖项：要求服务已完成启动并就绪。

    :param app_state: 注入的应用状态。
    :type app_state: HealthApiAppState
    :returns: 就绪的应用状态（原样返回）。
    :rtype: HealthApiAppState
    :raises HealthTriageHttpError: 服务未就绪或启动失败时抛出（503）。
    """
    if app_state.startup_error is not None:
        body = HealthTriageErrorBody(
            error="service_startup_failed",
            caseId="unknown",
            stage="parse",
            message=app_state.startup_error,
            violations=[],
        )
        raise HealthTriageHttpError(status_code=503, body=body)

    if not app_state.service_ready:
        body = HealthTriageErrorBody(
            error="service_not_ready",
            caseId="unknown",
            stage="parse",
            message="服务尚未完成启动，请稍后重试。",
            violations=[],
        )
        raise HealthTriageHttpError(status_code=503, body=body)

    return app_state


async def require_intelligent_endpoint(
    app_state: Annotated[HealthApiAppState, Depends(get_health_api_app_state)],
) -> HealthApiAppState:
    """依赖项：要求 ``POST /intelligent`` 占位端点已启用。

    占位实现 **不** 依赖 KB-TPL 预加载或分诊管道就绪；仅检查功能开关。

    :param app_state: 注入的应用状态。
    :type app_state: HealthApiAppState
    :returns: 已启用 intelligent 的应用状态（原样返回）。
    :rtype: HealthApiAppState
    :raises HealthTriageHttpError: ``intelligent_enabled=False`` 时抛出（404）。
    """
    if not app_state.intelligent_enabled:
        raise build_intelligent_disabled_http_error()
    return app_state
