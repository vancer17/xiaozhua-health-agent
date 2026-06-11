"""HTTP 服务运行时配置（WP6 阶段 2 · FastAPI 机械门面）。

通过环境变量加载；前缀 ``HEALTH_API_``（如 ``HEALTH_API_HOST``、
``HEALTH_API_PORT``）。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "DEFAULT_HEALTH_API_HOST",
    "DEFAULT_HEALTH_API_PORT",
    "HealthApiSettings",
    "get_health_api_settings",
]


DEFAULT_HEALTH_API_HOST: Final[str] = "0.0.0.0"
"""默认监听地址。"""

DEFAULT_HEALTH_API_PORT: Final[int] = 8080
"""默认 HTTP 端口（与运维 ``/healthz`` 区分于产品 ``POST /health``）。"""


class HealthApiSettings(BaseSettings):
    """健康分诊 HTTP API 运行时配置。

    :ivar host: Uvicorn 绑定地址。
    :vartype host: str
    :ivar port: Uvicorn 监听端口。
    :vartype port: int
    :ivar preload_copy_bundle: 启动时是否异步预加载 KB-TPL 知识包（影响 ``/readyz``）。
    :vartype preload_copy_bundle: bool
    :ivar access_log: 是否启用 Uvicorn 访问日志。
    :vartype access_log: bool
    :ivar api_title: OpenAPI 文档标题。
    :vartype api_title: str
    :ivar api_version: OpenAPI 文档版本字符串。
    :vartype api_version: str
    :ivar internal_prefix: 运维探针路由前缀（如 ``/internal``）；空字符串表示挂载在根路径。
    :vartype internal_prefix: str
    :ivar intelligent_enabled: 是否挂载 ``POST /intelligent`` 占位端点。
    :vartype intelligent_enabled: bool
    :ivar preload_input_lex_bundle: 启动时是否异步预加载 KB-INPUT-LEX 词表（影响 ``/readyz``）。
    :vartype preload_input_lex_bundle: bool
    """

    model_config = SettingsConfigDict(
        env_prefix="HEALTH_API_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    host: str = Field(
        default=DEFAULT_HEALTH_API_HOST,
        description="Uvicorn 绑定地址。",
    )
    port: int = Field(
        default=DEFAULT_HEALTH_API_PORT,
        ge=1,
        le=65535,
        description="Uvicorn 监听端口。",
    )
    preload_copy_bundle: bool = Field(
        default=True,
        description="启动 lifespan 中预加载默认 copy 知识包。",
    )
    access_log: bool = Field(
        default=True,
        description="是否输出 HTTP 访问日志。",
    )
    api_title: str = Field(
        default="小爪 AI 健康/兽医分诊 Agent V1",
        description="OpenAPI 文档标题。",
    )
    api_version: str = Field(
        default="0.1.0",
        description="OpenAPI 文档版本。",
    )
    internal_prefix: str = Field(
        default="/internal",
        description="运维探针（``/healthz``、``/readyz``）路径前缀。",
    )
    intelligent_enabled: bool = Field(
        default=True,
        description="是否启用 ``POST /intelligent`` 静态占位端点。",
    )
    preload_input_lex_bundle: bool = Field(
        default=False,
        description="启动 lifespan 中预加载默认 KB-INPUT-LEX 词表。",
    )


@lru_cache(maxsize=1)
def get_health_api_settings() -> HealthApiSettings:
    """加载并缓存 HTTP API 配置（进程内单例）。

    :returns: 自环境变量解析的配置实例。
    :rtype: HealthApiSettings
    """
    return HealthApiSettings()
