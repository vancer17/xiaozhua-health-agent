"""ValidateStructure（④-A）与 ACTION_INVALID 测试。"""

from __future__ import annotations

import pytest

from xiaozhua_health_agent.eval import (
    ViolationCode,
    validate_structure,
)


def _minimal_valid_draft_payload() -> dict[str, object]:
    """构造可通过 ValidateStructure 的最小文案 JSON。

    :returns: 含必填文案字段与合法 ``primaryAction`` 的字典。
    :rtype: dict[str, object]
    """
    return {
        "title": "标题",
        "summary": "摘要",
        "evidence": ["证据句"],
        "recommendation": "建议",
        "whenToSeeVet": "就医条件",
        "safetyNotice": "",
        "primaryAction": {"label": "联系兽医", "route": "contact_vet"},
        "secondaryAction": None,
    }


def test_validate_structure_passes_valid_payload() -> None:
    """合法 DraftCopyJSON 映射应通过且返回 parsed。"""
    result = validate_structure(_minimal_valid_draft_payload())
    assert result.passed is True
    assert result.violations == []
    assert result.parsed is not None
    assert result.parsed.title == "标题"
    assert result.schema_kind == "draft_copy"


def test_validate_structure_parse_error_on_non_object() -> None:
    """非 JSON 对象应产出 PARSE_ERROR。"""
    result = validate_structure(["not", "a", "dict"])
    assert result.passed is False
    assert len(result.violations) == 1
    assert result.violations[0].code == ViolationCode.PARSE_ERROR.value


def test_validate_structure_field_missing_for_title() -> None:
    """缺少顶层文案字段应产出 FIELD_MISSING。"""
    payload = _minimal_valid_draft_payload()
    del payload["title"]
    result = validate_structure(payload)
    assert result.passed is False
    codes = {item.code for item in result.violations}
    assert ViolationCode.FIELD_MISSING.value in codes
    paths = {item.path for item in result.violations}
    assert "title" in paths


@pytest.mark.parametrize(
    ("primary_action", "expected_path"),
    [
        (None, "primaryAction"),
        ("not-an-object", "primaryAction"),
        ({"route": "contact_vet"}, "primaryAction.label"),
        ({"label": ""}, "primaryAction.label"),
        ({"label": "   "}, "primaryAction.label"),
        ({"label": 123}, "primaryAction.label"),
        ({"label": "联系兽医", "route": 99}, "primaryAction.route"),
    ],
)
def test_validate_structure_action_invalid_primary_action(
    primary_action: object,
    expected_path: str,
) -> None:
    """``primaryAction`` 形态非法时应产出 ACTION_INVALID 且 path 明确。"""
    payload = _minimal_valid_draft_payload()
    payload["primaryAction"] = primary_action
    result = validate_structure(payload)
    assert result.passed is False
    action_violations = [
        item
        for item in result.violations
        if item.code == ViolationCode.ACTION_INVALID.value
    ]
    assert action_violations, result.violations
    assert any(item.path == expected_path for item in action_violations)
    assert all(item.field == "primaryAction" for item in action_violations)


def test_validate_structure_action_invalid_secondary_action() -> None:
    """``secondaryAction`` 非 null 但缺少 label 时应产出 ACTION_INVALID。"""
    payload = _minimal_valid_draft_payload()
    payload["secondaryAction"] = {"route": "record_symptom"}
    result = validate_structure(payload)
    assert result.passed is False
    action_violations = [
        item
        for item in result.violations
        if item.code == ViolationCode.ACTION_INVALID.value
    ]
    assert any(item.path == "secondaryAction.label" for item in action_violations)
    assert all(item.field == "secondaryAction" for item in action_violations)


def test_validate_structure_missing_primary_action_is_field_missing() -> None:
    """完全缺少 ``primaryAction`` 键时应为 FIELD_MISSING（非 ACTION_INVALID）。"""
    payload = _minimal_valid_draft_payload()
    del payload["primaryAction"]
    result = validate_structure(payload)
    assert result.passed is False
    assert any(
        item.code == ViolationCode.FIELD_MISSING.value and item.path == "primaryAction"
        for item in result.violations
    )
    assert not any(
        item.code == ViolationCode.ACTION_INVALID.value for item in result.violations
    )


def test_validate_structure_accepts_parsed_draft_copy_json() -> None:
    """已解析 ``DraftCopyJSON`` 实例应直接通过。"""
    from xiaozhua_health_agent.copy import DraftCopyJSON
    from xiaozhua_health_agent.schemas import ActionItem

    draft = DraftCopyJSON(
        title="标题",
        summary="摘要",
        evidence=["证据"],
        recommendation="建议",
        when_to_see_vet="就医条件",
        primary_action=ActionItem(label="休息观察", route="rest_observe"),
    )
    result = validate_structure(draft)
    assert result.passed is True
    assert result.parsed == draft
