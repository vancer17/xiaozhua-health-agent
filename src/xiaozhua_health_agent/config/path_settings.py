"""制品路径与项目根目录配置（环境变量）。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from xiaozhua_health_agent.paths import (
    DEFAULT_ACTION_MATRIX_RELATIVE_PATH,
    DEFAULT_CASES_RELATIVE_PATH,
    DEFAULT_FORBIDDEN_PATTERNS_RELATIVE_PATH,
    DEFAULT_KB_ACTION_RELATIVE_PATH,
    DEFAULT_KB_TPL_CONFIG_RELATIVE_DIR,
    DEFAULT_SYNONYM_MAP_RELATIVE_PATH,
    PACKAGE_ANCHOR_PROJECT_ROOT,
)

__all__ = [
    "XiaozhuaPathSettings",
    "clear_xiaozhua_path_settings_cache",
    "get_xiaozhua_path_settings",
    "resolve_configured_path",
]


class XiaozhuaPathSettings(BaseSettings):
    """知识资产与 case 文件路径配置。

    环境变量前缀 ``XIAOZHUA_``。相对路径均相对于 :func:`resolved_project_root`。

    兼容旧名（无 ``XIAOZHUA_`` 前缀）：``KB_TPL_DIR``、``TRIAGE_CORE_PATH``。

    :ivar project_root: 可选项目根绝对路径；省略时由包锚点推断。
    :vartype project_root: str | None
    :ivar cases_path: mock case JSON 路径。
    :vartype cases_path: str
    :ivar kb_tpl_dir: KB-TPL 配置目录。
    :vartype kb_tpl_dir: str
    :ivar kb_forbid_path: KB-FORBID JSON 路径。
    :vartype kb_forbid_path: str
    :ivar kb_syn_path: KB-SYN JSON 路径。
    :vartype kb_syn_path: str
    :ivar kb_action_path: KB-ACTION JSON 路径。
    :vartype kb_action_path: str
    :ivar triage_core_path: triage-core 决策表路径（预留；当前规则仍内嵌于 Python）。
    :vartype triage_core_path: str
    :ivar action_matrix_path: action 评测 fixture 路径。
    :vartype action_matrix_path: str
    """

    model_config = SettingsConfigDict(
        env_prefix="XIAOZHUA_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    project_root: str | None = Field(
        default=None,
        description="可选项目根绝对路径。",
    )
    cases_path: str = Field(
        default=DEFAULT_CASES_RELATIVE_PATH,
        description="mock case JSON 相对或绝对路径。",
    )
    kb_tpl_dir: str = Field(
        default=DEFAULT_KB_TPL_CONFIG_RELATIVE_DIR,
        validation_alias=AliasChoices("XIAOZHUA_KB_TPL_DIR", "KB_TPL_DIR"),
        description="KB-TPL 配置目录。",
    )
    kb_forbid_path: str = Field(
        default=DEFAULT_FORBIDDEN_PATTERNS_RELATIVE_PATH,
        description="KB-FORBID JSON 路径。",
    )
    kb_syn_path: str = Field(
        default=DEFAULT_SYNONYM_MAP_RELATIVE_PATH,
        description="KB-SYN JSON 路径。",
    )
    kb_action_path: str = Field(
        default=DEFAULT_KB_ACTION_RELATIVE_PATH,
        description="KB-ACTION JSON 路径。",
    )
    triage_core_path: str = Field(
        default="assets/triage-core/triage-core.v1.json",
        validation_alias=AliasChoices(
            "XIAOZHUA_TRIAGE_CORE_PATH",
            "TRIAGE_CORE_PATH",
        ),
        description="triage-core 决策表路径（预留接线）。",
    )
    action_matrix_path: str = Field(
        default=DEFAULT_ACTION_MATRIX_RELATIVE_PATH,
        description="action 矩阵评测 fixture 路径。",
    )

    def resolved_project_root(self) -> Path:
        """返回生效的项目根目录。

        :returns: 绝对路径。
        :rtype: pathlib.Path
        """
        if self.project_root:
            return Path(self.project_root).expanduser().resolve()
        return PACKAGE_ANCHOR_PROJECT_ROOT

    def resolve_path(self, configured: str) -> Path:
        """将配置项解析为绝对路径。

        :param configured: 相对项目根或绝对路径字符串。
        :type configured: str
        :returns: 解析后的绝对路径。
        :rtype: pathlib.Path
        """
        return resolve_configured_path(configured, root=self.resolved_project_root())


def resolve_configured_path(configured: str, *, root: Path) -> Path:
    """将相对或绝对路径字符串解析为 ``Path``。

    :param configured: 路径字符串。
    :type configured: str
    :param root: 相对路径的基准目录。
    :type root: pathlib.Path
    :returns: 绝对路径。
    :rtype: pathlib.Path
    """
    path = Path(configured).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


@lru_cache(maxsize=1)
def get_xiaozhua_path_settings() -> XiaozhuaPathSettings:
    """加载并缓存路径配置（进程内单例）。

    :returns: 自环境变量解析的配置实例。
    :rtype: XiaozhuaPathSettings
    """
    return XiaozhuaPathSettings()


def clear_xiaozhua_path_settings_cache() -> None:
    """清空路径配置 LRU 缓存（单测用）。

    :rtype: None
    """
    get_xiaozhua_path_settings.cache_clear()
