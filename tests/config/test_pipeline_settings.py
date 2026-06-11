"""管道开关环境变量单测。"""

from __future__ import annotations

import pytest

from xiaozhua_health_agent.config.pipeline_settings import (
    clear_xiaozhua_pipeline_settings_cache,
    get_default_health_triage_pipeline_options,
    get_xiaozhua_pipeline_settings,
)
from xiaozhua_health_agent.guard import ContentGuardMode
from xiaozhua_health_agent.pipeline.retry_types import DraftRetryOptions


@pytest.fixture(autouse=True)
def _clear_pipeline_settings_cache() -> None:
    """每个用例前后清空管道配置缓存。"""
    clear_xiaozhua_pipeline_settings_cache()
    yield
    clear_xiaozhua_pipeline_settings_cache()


def test_default_pipeline_options() -> None:
    """默认管道开关应与静态默认值一致（机械路径）。"""
    options = get_default_health_triage_pipeline_options()
    assert options.skip_content_guard is False
    assert options.guard_mode == ContentGuardMode.STRICT
    assert options.retry_options is None
    assert options.resolved_draft_retry_options().llm_enabled is False


def test_skip_content_guard_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """``XIAOZHUA_PIPELINE_SKIP_CONTENT_GUARD=true`` 应生效。"""
    monkeypatch.setenv("XIAOZHUA_PIPELINE_SKIP_CONTENT_GUARD", "true")
    clear_xiaozhua_pipeline_settings_cache()

    options = get_default_health_triage_pipeline_options()
    assert options.skip_content_guard is True


def test_llm_enabled_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """启用 LLM 时应注入 ``retry_options``。"""
    monkeypatch.setenv("XIAOZHUA_PIPELINE_LLM_ENABLED", "true")
    monkeypatch.setenv("XIAOZHUA_PIPELINE_GUARD_MODE", "report_only")
    clear_xiaozhua_pipeline_settings_cache()

    settings = get_xiaozhua_pipeline_settings()
    options = settings.to_pipeline_options()
    assert options.guard_mode == "report_only"
    assert options.retry_options is not None
    assert isinstance(options.retry_options, DraftRetryOptions)
    assert options.retry_options.llm_enabled is True
