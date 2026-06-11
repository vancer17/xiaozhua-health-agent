"""小爪 AI 健康/兽医分诊 Agent V1 包入口。"""

from __future__ import annotations

__all__ = [
    "main",
]


def main() -> None:
    """CLI 入口：启动 FastAPI 机械分诊 HTTP 服务。

    等价于 ``xiaozhua-health-agent`` 控制台脚本。

    :returns: ``None``。
    :rtype: None
    """
    from xiaozhua_health_agent.api import run_health_api_server

    run_health_api_server()
