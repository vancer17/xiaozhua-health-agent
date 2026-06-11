"""FastAPI 异步 lifespan（预加载知识包与就绪标记，WP6 阶段 2）。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import TYPE_CHECKING

from xiaozhua_health_agent.api.app_state import HealthApiAppState
from xiaozhua_health_agent.api.settings import HealthApiSettings
from xiaozhua_health_agent.copy import (
    CopyKnowledgeBundle,
    load_default_copy_knowledge_bundle,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = [
    "build_health_api_lifespan",
]

LifespanCallable = Callable[["FastAPI"], AbstractAsyncContextManager[None]]
"""FastAPI ``lifespan`` 参数可接受的异步上下文管理器工厂类型。"""


def build_health_api_lifespan(
    *,
    settings: HealthApiSettings,
    app_state: HealthApiAppState,
) -> LifespanCallable:
    """构造绑定到指定应用状态的 lifespan 钩子。

    :param settings: HTTP API 配置。
    :type settings: HealthApiSettings
    :param app_state: 待初始化的共享状态容器。
    :type app_state: HealthApiAppState
    :returns: 供 ``FastAPI(lifespan=...)`` 使用的上下文管理器函数。
    :rtype: LifespanCallable
    """

    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """应用启动与关闭钩子（闭包）。

        :param _app: FastAPI 应用实例（未使用，保留以符合 lifespan 签名）。
        :type _app: FastAPI
        :yields: 控制权交还请求处理阶段。
        :rtype: None
        """
        try:
            await _startup_health_api_state(
                settings=settings,
                app_state=app_state,
            )
        except Exception as exc:
            app_state.startup_error = str(exc)
            app_state.service_ready = False
            raise

        yield

        await _shutdown_health_api_state(app_state=app_state)

    return _lifespan


async def _startup_health_api_state(
    *,
    settings: HealthApiSettings,
    app_state: HealthApiAppState,
) -> None:
    """执行启动阶段异步初始化（内部辅助）。

    :param settings: HTTP API 配置。
    :type settings: HealthApiSettings
    :param app_state: 待填充的应用状态。
    :type app_state: HealthApiAppState
    :returns: ``None``。
    :rtype: None
    """
    if app_state.copy_bundle is not None:
        app_state.copy_bundle_ready = True
        app_state.service_ready = True
        return

    if not settings.preload_copy_bundle:
        app_state.copy_bundle_ready = False
        app_state.service_ready = True
        return

    async def _load_bundle() -> CopyKnowledgeBundle:
        """在线程池中加载默认 KB-TPL 知识包（闭包）。

        :returns: 默认 copy 知识资产聚合包。
        :rtype: CopyKnowledgeBundle
        """
        return await asyncio.to_thread(load_default_copy_knowledge_bundle)

    loaded_bundle = await _load_bundle()
    app_state.copy_bundle = loaded_bundle
    app_state.copy_bundle_ready = True
    app_state.service_ready = True


async def _shutdown_health_api_state(
    *,
    app_state: HealthApiAppState,
) -> None:
    """执行关闭阶段清理（内部辅助）。

    :param app_state: 应用状态。
    :type app_state: HealthApiAppState
    :returns: ``None``。
    :rtype: None
    """
    app_state.service_ready = False
