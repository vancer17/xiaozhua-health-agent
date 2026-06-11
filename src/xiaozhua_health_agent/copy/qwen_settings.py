"""通义千问（DashScope OpenAI 兼容）客户端配置。

通过环境变量加载；供 ``qwen_client`` 构造 ``AsyncQwenClient`` 使用。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Final

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = [
    "DEFAULT_QWEN_BASE_URL",
    "DEFAULT_QWEN_MODEL",
    "QwenClientSettings",
    "QwenSettingsError",
    "get_qwen_client_settings",
]


class QwenSettingsError(Exception):
    """通义千问客户端配置缺失或非法。"""


DEFAULT_QWEN_BASE_URL: Final[str] = "https://dashscope.aliyuncs.com/compatible-mode/v1"
"""DashScope OpenAI 兼容模式默认基址。"""

DEFAULT_QWEN_MODEL: Final[str] = "qwen-plus"
"""V1 文案生成默认模型。"""


class QwenClientSettings(BaseSettings):
    """通义千问 HTTP 客户端运行时配置。

    环境变量前缀 ``QWEN_``（如 ``QWEN_API_KEY``、``QWEN_MODEL``）。

    :ivar api_key: DashScope API Key；未配置时客户端调用将失败。
    :vartype api_key: SecretStr | None
    :ivar base_url: OpenAI 兼容 API 基址。
    :vartype base_url: str
    :ivar model: 默认聊天模型名。
    :vartype model: str
    :ivar timeout_sec: 单次请求总超时（秒）。
    :vartype timeout_sec: float
    :ivar max_retries: 传输层自动重试次数（OpenAI SDK 层）。
    :vartype max_retries: int
    :ivar default_temperature: 默认采样温度。
    :vartype default_temperature: float
    :ivar default_max_tokens: 默认最大生成 token 数。
    :vartype default_max_tokens: int
    """

    model_config = SettingsConfigDict(
        env_prefix="QWEN_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_key: SecretStr | None = Field(
        default=None,
        description="DashScope API Key（环境变量 QWEN_API_KEY）。",
    )
    base_url: str = Field(
        default=DEFAULT_QWEN_BASE_URL,
        description="OpenAI 兼容 API 基址。",
    )
    model: str = Field(
        default=DEFAULT_QWEN_MODEL,
        description="默认聊天补全模型。",
    )
    timeout_sec: float = Field(
        default=30.0,
        gt=0.0,
        description="HTTP 请求总超时（秒）。",
    )
    max_retries: int = Field(
        default=2,
        ge=0,
        description="OpenAI SDK 传输层重试次数。",
    )
    default_temperature: float = Field(
        default=0.4,
        ge=0.0,
        le=2.0,
        description="chat.completions 默认 temperature。",
    )
    default_max_tokens: int = Field(
        default=1200,
        ge=1,
        description="chat.completions 默认 max_tokens。",
    )

    def require_api_key(self) -> str:
        """返回明文 API Key；未配置时抛出 ``QwenSettingsError``。

        :returns: API Key 明文字符串。
        :rtype: str
        :raises QwenSettingsError: ``api_key`` 未设置时抛出。
        """
        if self.api_key is None:
            msg = "未配置 QWEN_API_KEY，无法调用通义千问 API。"
            raise QwenSettingsError(msg)
        return self.api_key.get_secret_value()


@lru_cache
def get_qwen_client_settings() -> QwenClientSettings:
    """加载并缓存进程级 ``QwenClientSettings``（读取环境变量 / ``.env``）。

    :returns: 不可变配置快照（Pydantic 模型实例）。
    :rtype: QwenClientSettings
    """
    return QwenClientSettings()
