"""项目根目录与 docs 制品路径。"""

from __future__ import annotations

from pathlib import Path

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


def project_root() -> Path:
    """推断项目根目录。

    以 ``src/xiaozhua_health_agent/paths.py`` 为锚点，向上两级即为项目根。

    :returns: 项目根目录绝对路径。
    """
    return Path(__file__).resolve().parents[2]


def default_cases_path() -> Path:
    """返回默认 case 文件路径。"""
    return project_root() / DEFAULT_CASES_RELATIVE_PATH


def default_forbidden_patterns_path() -> Path:
    """返回默认 KB-FORBID 文件路径。

    :returns: 禁止词 JSON 绝对路径。
    :rtype: pathlib.Path
    """
    return project_root() / DEFAULT_FORBIDDEN_PATTERNS_RELATIVE_PATH


def default_synonym_map_path() -> Path:
    """返回默认 KB-SYN 文件路径。

    :returns: 同义词 JSON 绝对路径。
    :rtype: pathlib.Path
    """
    return project_root() / DEFAULT_SYNONYM_MAP_RELATIVE_PATH


def default_kb_tpl_config_dir() -> Path:
    """返回默认 KB-TPL 配置目录路径。

    :returns: KB-TPL JSON 制品目录绝对路径。
    :rtype: pathlib.Path
    """
    return project_root() / DEFAULT_KB_TPL_CONFIG_RELATIVE_DIR


def default_kb_action_path() -> Path:
    """返回默认 KB-ACTION 文件路径。

    :returns: KB-ACTION JSON 绝对路径。
    :rtype: pathlib.Path
    """
    return project_root() / DEFAULT_KB_ACTION_RELATIVE_PATH


def default_action_matrix_path() -> Path:
    """返回默认 action 矩阵期望 fixture 路径。

    :returns: action_matrix.v1.json 绝对路径。
    :rtype: pathlib.Path
    """
    return project_root() / DEFAULT_ACTION_MATRIX_RELATIVE_PATH
