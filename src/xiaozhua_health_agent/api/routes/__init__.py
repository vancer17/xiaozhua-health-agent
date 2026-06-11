"""HTTP 路由聚合（WP6 阶段 2）。"""

from __future__ import annotations

from fastapi import APIRouter

from xiaozhua_health_agent.api.routes.health_triage import build_health_triage_router
from xiaozhua_health_agent.api.routes.intelligent import build_intelligent_router
from xiaozhua_health_agent.api.routes.ops import build_ops_router

__all__ = [
    "build_api_router",
]


def build_api_router(
    *,
    internal_prefix: str,
) -> APIRouter:
    """组装全部 HTTP 路由。

    :param internal_prefix: 运维探针挂载前缀（如 ``/internal``）；空串表示根路径。
    :type internal_prefix: str
    :returns: 包含产品与运维子路由的根路由器。
    :rtype: APIRouter
    """
    root = APIRouter()

    root.include_router(build_health_triage_router())
    root.include_router(build_intelligent_router())

    ops_router = build_ops_router()
    prefix = internal_prefix.rstrip("/")
    if prefix:
        root.include_router(ops_router, prefix=prefix)
    else:
        root.include_router(ops_router)

    return root
