"""Uvicorn 启动入口（WP6 阶段 2）。"""

from __future__ import annotations

import asyncio
from typing import Any

from xiaozhua_health_agent.api.app_factory import create_app
from xiaozhua_health_agent.api.settings import (
    HealthApiSettings,
    get_health_api_settings,
)

__all__ = [
    "run_health_api_server",
    "run_health_api_server_async",
]


def run_health_api_server(
    *,
    settings: HealthApiSettings | None = None,
) -> None:
    """以阻塞方式启动 Uvicorn HTTP 服务。

    :param settings: 可选 HTTP 配置；省略时从环境变量读取。
    :type settings: HealthApiSettings | None
    :returns: ``None``（通常直至进程退出）。
    :rtype: None
    """
    asyncio.run(run_health_api_server_async(settings=settings))


async def run_health_api_server_async(
    *,
    settings: HealthApiSettings | None = None,
) -> None:
    """以异步方式启动 Uvicorn HTTP 服务。

    :param settings: 可选 HTTP 配置；省略时从环境变量读取。
    :type settings: HealthApiSettings | None
    :returns: ``None``（直至 Uvicorn 退出）。
    :rtype: None
    """
    import uvicorn

    resolved_settings = settings if settings is not None else get_health_api_settings()
    application = create_app(settings=resolved_settings)

    config = uvicorn.Config(
        app=application,
        host=resolved_settings.host,
        port=resolved_settings.port,
        access_log=resolved_settings.access_log,
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


def build_uvicorn_run_kwargs(
    *,
    settings: HealthApiSettings | None = None,
) -> dict[str, Any]:
    """构造 ``uvicorn.run`` 关键字参数字典（便于 CLI 与测试）。

    :param settings: 可选 HTTP 配置。
    :type settings: HealthApiSettings | None
    :returns: 含 ``app``、``host``、``port`` 等键的字典。
    :rtype: dict[str, Any]
    """
    resolved_settings = settings if settings is not None else get_health_api_settings()
    application = create_app(settings=resolved_settings)
    return {
        "app": application,
        "host": resolved_settings.host,
        "port": resolved_settings.port,
        "access_log": resolved_settings.access_log,
    }
