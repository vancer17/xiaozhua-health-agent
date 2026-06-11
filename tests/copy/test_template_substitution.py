"""模板占位符机械替换单元测试。"""

from __future__ import annotations

import pytest

from xiaozhua_health_agent.copy import (
    filter_outline_lines,
    has_unresolved_placeholders,
    substitute_template_text,
)


def test_substitute_template_text_replaces_known_slots() -> None:
    """已知槽位应正确替换。"""
    result = substitute_template_text(
        "{petName}当前体温{temperature}",
        {"petName": "豆豆", "temperature": "39.1°C"},
    )
    assert result == "豆豆当前体温39.1°C"


def test_substitute_template_text_omit_missing_slot() -> None:
    """缺失槽位在 omit 模式下应删除占位符。"""
    result = substitute_template_text(
        "安静时体温{temperature}偏高",
        {},
        on_missing="omit",
    )
    assert result == "安静时体温偏高"
    assert not has_unresolved_placeholders(result)


def test_substitute_template_text_keep_missing_slot() -> None:
    """keep 模式应保留未解析占位符。"""
    result = substitute_template_text(
        "体温{temperature}",
        {},
        on_missing="keep",
    )
    assert result == "体温{temperature}"
    assert has_unresolved_placeholders(result)


def test_substitute_template_text_invalid_on_missing_raises() -> None:
    """非法 on_missing 应抛出 ValueError。"""
    with pytest.raises(ValueError, match="on_missing"):
        substitute_template_text("x", {}, on_missing="invalid")


def test_filter_outline_lines_drops_unresolved() -> None:
    """仍含未解析占位符的提纲行应被丢弃。"""
    lines = filter_outline_lines(
        (
            "体温{temperature}偏高",
            "建议休息补水",
        ),
        {"temperature": "39.1°C"},
    )
    assert lines == ("体温39.1°C偏高", "建议休息补水")


def test_filter_outline_lines_drops_empty_after_omit() -> None:
    """仅含缺失槽位的提纲行在 omit 后应被丢弃。"""
    lines = filter_outline_lines(("{temperature}", "有效行"), {})
    assert lines == ("有效行",)
