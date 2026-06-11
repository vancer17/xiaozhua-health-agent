"""项目根目录与 docs / assets 制品路径。"""

from __future__ import annotations

from pathlib import Path
from typing import Final

DEFAULT_CASES_RELATIVE_PATH: str = "docs/cases/health_triage_cases.v1.json"
"""相对项目根目录的默认 case 文件路径。"""

DEFAULT_FORBIDDEN_PATTERNS_RELATIVE_PATH: str = (
    "assets/kb-forbid/forbidden_patterns.v1.json"
)
"""相对项目根目录的默认 KB-FORBID 文件路径。"""

DEFAULT_SYNONYM_MAP_RELATIVE_PATH: str = "assets/kb-syn/kb-syn.v1.json"
"""相对项目根目录的默认 KB-SYN 文件路径。"""

DEFAULT_KB_TPL_CONFIG_RELATIVE_DIR: str = "assets/kb-tpl/config"
"""相对项目根目录的默认 KB-TPL 配置目录。"""

DEFAULT_KB_ACTION_RELATIVE_PATH: str = "assets/kb-action/actions.v1.json"
"""相对项目根目录的默认 KB-ACTION 文件路径。"""

DEFAULT_ACTION_MATRIX_RELATIVE_PATH: str = "assets/eval/action_matrix.v1.json"
"""相对项目根目录的默认 action 矩阵期望 fixture 路径。"""

DEFAULT_KB_INPUT_LEX_RELATIVE_PATH: str = "assets/kb-input-lex/input-lex.v1.json"
"""相对项目根目录的默认 KB-INPUT-LEX 文件路径。"""

PACKAGE_ANCHOR_PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
"""以 ``paths.py`` 为锚点推断的项目根（未设置 ``XIAOZHUA_PROJECT_ROOT`` 时使用）。"""


def project_root() -> Path:
    """推断当前生效的项目根目录。

    优先读取 ``XIAOZHUA_PROJECT_ROOT``；否则使用包锚点路径。

    :returns: 项目根目录绝对路径。
    :rtype: pathlib.Path
    """
    from xiaozhua_health_agent.config.path_settings import get_xiaozhua_path_settings

    return get_xiaozhua_path_settings().resolved_project_root()


def default_cases_path() -> Path:
    """返回 mock case 文件路径。

    :returns: case JSON 绝对路径。
    :rtype: pathlib.Path
    """
    from xiaozhua_health_agent.config.path_settings import get_xiaozhua_path_settings

    settings = get_xiaozhua_path_settings()
    return settings.resolve_path(settings.cases_path)


def default_forbidden_patterns_path() -> Path:
    """返回默认 KB-FORBID 文件路径。

    :returns: 禁止词 JSON 绝对路径。
    :rtype: pathlib.Path
    """
    from xiaozhua_health_agent.config.path_settings import get_xiaozhua_path_settings

    settings = get_xiaozhua_path_settings()
    return settings.resolve_path(settings.kb_forbid_path)


def default_synonym_map_path() -> Path:
    """返回默认 KB-SYN 文件路径。

    :returns: 同义词 JSON 绝对路径。
    :rtype: pathlib.Path
    """
    from xiaozhua_health_agent.config.path_settings import get_xiaozhua_path_settings

    settings = get_xiaozhua_path_settings()
    return settings.resolve_path(settings.kb_syn_path)


def default_kb_tpl_config_dir() -> Path:
    """返回默认 KB-TPL 配置目录路径。

    :returns: KB-TPL JSON 制品目录绝对路径。
    :rtype: pathlib.Path
    """
    from xiaozhua_health_agent.config.path_settings import get_xiaozhua_path_settings

    settings = get_xiaozhua_path_settings()
    return settings.resolve_path(settings.kb_tpl_dir)


def default_kb_action_path() -> Path:
    """返回默认 KB-ACTION 文件路径。

    :returns: KB-ACTION JSON 绝对路径。
    :rtype: pathlib.Path
    """
    from xiaozhua_health_agent.config.path_settings import get_xiaozhua_path_settings

    settings = get_xiaozhua_path_settings()
    return settings.resolve_path(settings.kb_action_path)


def default_action_matrix_path() -> Path:
    """返回默认 action 矩阵期望 fixture 路径。

    :returns: action_matrix.v1.json 绝对路径。
    :rtype: pathlib.Path
    """
    from xiaozhua_health_agent.config.path_settings import get_xiaozhua_path_settings

    settings = get_xiaozhua_path_settings()
    return settings.resolve_path(settings.action_matrix_path)


def default_input_lex_path() -> Path:
    """返回默认 KB-INPUT-LEX 文件路径。

    :returns: input-lex JSON 绝对路径。
    :rtype: pathlib.Path
    """
    from xiaozhua_health_agent.config.path_settings import get_xiaozhua_path_settings

    settings = get_xiaozhua_path_settings()
    return settings.resolve_path(settings.kb_input_lex_path)


def default_triage_core_path() -> Path:
    """返回 triage-core 决策表路径（预留；当前规则仍内嵌于 Python）。

    :returns: triage-core JSON 绝对路径。
    :rtype: pathlib.Path
    """
    from xiaozhua_health_agent.config.path_settings import get_xiaozhua_path_settings

    settings = get_xiaozhua_path_settings()
    return settings.resolve_path(settings.triage_core_path)
