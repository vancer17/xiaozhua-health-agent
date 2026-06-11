"""路径配置环境变量单测。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.config.path_settings import (
    clear_xiaozhua_path_settings_cache,
    get_xiaozhua_path_settings,
)
from xiaozhua_health_agent.paths import (
    default_cases_path,
    default_kb_tpl_config_dir,
    default_triage_core_path,
    project_root,
)


@pytest.fixture(autouse=True)
def _clear_path_settings_cache() -> None:
    """每个用例前后清空路径配置缓存。"""
    clear_xiaozhua_path_settings_cache()
    yield
    clear_xiaozhua_path_settings_cache()


def test_default_paths_resolve_under_package_root() -> None:
    """未设置环境变量时，默认路径应落在包锚点项目根下。"""
    root = project_root()
    assert default_cases_path() == root / "docs/cases/health_triage_cases.v1.json"
    assert default_kb_tpl_config_dir() == root / "assets/kb-tpl/config"


def test_kb_tpl_dir_legacy_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``KB_TPL_DIR`` 无 XIAOZHUA_ 前缀时仍应生效。"""
    custom_dir = tmp_path / "custom-tpl"
    custom_dir.mkdir()
    monkeypatch.setenv("XIAOZHUA_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("KB_TPL_DIR", "custom-tpl")
    clear_xiaozhua_path_settings_cache()

    settings = get_xiaozhua_path_settings()
    assert settings.kb_tpl_dir == "custom-tpl"
    assert default_kb_tpl_config_dir() == custom_dir.resolve()


def test_triage_core_path_legacy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """``TRIAGE_CORE_PATH`` 应映射到 triage_core_path。"""
    monkeypatch.setenv("TRIAGE_CORE_PATH", "assets/custom/triage.json")
    clear_xiaozhua_path_settings_cache()

    settings = get_xiaozhua_path_settings()
    assert settings.triage_core_path == "assets/custom/triage.json"
    assert default_triage_core_path().name == "triage.json"


def test_absolute_cases_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """绝对路径不应再拼接项目根。"""
    cases_file = tmp_path / "cases.json"
    cases_file.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("XIAOZHUA_CASES_PATH", str(cases_file))
    clear_xiaozhua_path_settings_cache()

    assert default_cases_path() == cases_file.resolve()
