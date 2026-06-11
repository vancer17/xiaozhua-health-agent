"""FastAPI 应用工厂（WP6 阶段 2）。"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from xiaozhua_health_agent.api.app_state import HealthApiAppState
from xiaozhua_health_agent.api.errors import HealthTriageHttpError
from xiaozhua_health_agent.api.lifespan import build_health_api_lifespan
from xiaozhua_health_agent.api.routes import build_api_router
from xiaozhua_health_agent.api.settings import (
    HealthApiSettings,
    get_health_api_settings,
)
from xiaozhua_health_agent.copy import CopyKnowledgeBundle
from xiaozhua_health_agent.config import get_default_health_triage_pipeline_options
from xiaozhua_health_agent.pipeline import HealthTriagePipelineOptions

__all__ = [
    "create_app",
    "register_health_triage_exception_handlers",
]

ExceptionHandler = Callable[[Request, Exception], JSONResponse]
"""FastAPI 异常处理器可调用类型别名。"""


def create_app(
    *,
    settings: HealthApiSettings | None = None,
    app_state: HealthApiAppState | None = None,
    copy_bundle: CopyKnowledgeBundle | None = None,
    pipeline_options: HealthTriagePipelineOptions | None = None,
    skip_lifespan: bool = False,
) -> FastAPI:
    """创建配置完成的 FastAPI 应用实例。

    阶段 2 默认挂载机械路径 ``POST /health`` 与运维探针；不包含 Guard / LLM。

    :param settings: HTTP 配置；省略时从环境变量加载。
    :type settings: HealthApiSettings | None
    :param app_state: 可选预构建应用状态；省略时自动创建。
    :type app_state: HealthApiAppState | None
    :param copy_bundle: 可选预注入知识包（测试用）；设置后跳过 lifespan 预加载。
    :type copy_bundle: CopyKnowledgeBundle | None
    :param pipeline_options: 可选管道配置覆盖。
    :type pipeline_options: HealthTriagePipelineOptions | None
    :param skip_lifespan: 为 ``True`` 时不注册 lifespan（单测可手动标记就绪）。
    :type skip_lifespan: bool
    :returns: 可交给 Uvicorn 或 TestClient 的 FastAPI 应用。
    :rtype: FastAPI
    """
    resolved_settings = settings if settings is not None else get_health_api_settings()
    resolved_state = app_state if app_state is not None else HealthApiAppState()

    resolved_state.pipeline_options = (
        pipeline_options
        if pipeline_options is not None
        else get_default_health_triage_pipeline_options()
    )

    resolved_state.intelligent_enabled = resolved_settings.intelligent_enabled

    if copy_bundle is not None:
        resolved_state.copy_bundle = copy_bundle
        resolved_state.copy_bundle_ready = True
        resolved_state.service_ready = True

    lifespan_hook = None
    if not skip_lifespan and copy_bundle is None:
        lifespan_hook = build_health_api_lifespan(
            settings=resolved_settings,
            app_state=resolved_state,
        )

    application = FastAPI(
        title=resolved_settings.api_title,
        version=resolved_settings.api_version,
        lifespan=lifespan_hook,
    )
    application.state.health_api = resolved_state

    application.include_router(
        build_api_router(internal_prefix=resolved_settings.internal_prefix),
    )
    register_health_triage_exception_handlers(application)

    return application


def register_health_triage_exception_handlers(application: FastAPI) -> None:
    """注册 ``HealthTriageHttpError`` 全局异常处理器。

    :param application: FastAPI 应用实例。
    :type application: FastAPI
    :returns: ``None``。
    :rtype: None
    """
    application.add_exception_handler(
        HealthTriageHttpError,
        _handle_health_triage_http_error,
    )


async def _handle_health_triage_http_error(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    """将 ``HealthTriageHttpError`` 映射为 JSON 响应（内部异常处理器）。

    :param _request: 当前请求（未使用）。
    :type _request: Request
    :param exc: 捕获的异常实例。
    :type exc: Exception
    :returns: 含结构化错误体的 JSON 响应。
    :rtype: JSONResponse
    """
    if not isinstance(exc, HealthTriageHttpError):
        body = {
            "error": "internal_server_error",
            "caseId": "unknown",
            "stage": "parse",
            "message": "未知服务器错误。",
            "violations": [],
        }
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=body
        )

    return JSONResponse(
        status_code=exc.status_code,
        content=exc.body.model_dump(by_alias=True, mode="json"),
    )
