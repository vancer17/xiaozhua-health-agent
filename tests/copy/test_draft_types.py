"""WP4 ③-2 DraftCopyJSON 类型测试。"""

from __future__ import annotations

import pytest

from xiaozhua_health_agent.copy import DraftCopyJSON
from xiaozhua_health_agent.schemas import ActionItem


def test_draft_copy_json_alias_round_trip() -> None:
    """camelCase 序列化与反序列化往返一致。"""
    draft = DraftCopyJSON(
        title="安静状态下体温偏高",
        summary="安静时体温偏高，建议联系兽医。",
        evidence=["安静时体温 40.2°C"],
        recommendation="请尽快联系兽医。",
        when_to_see_vet="若精神变差请就医。",
        safety_notice="以上建议仅供参考。",
        primary_action=ActionItem(label="联系兽医", route="contact_vet"),
        secondary_action=None,
    )
    payload = draft.to_alias_dict()
    assert payload["whenToSeeVet"] == "若精神变差请就医。"
    assert payload["primaryAction"]["label"] == "联系兽医"
    restored = DraftCopyJSON.from_alias_dict(payload)
    assert restored == draft


def test_draft_copy_json_allows_empty_safety_notice() -> None:
    """safetyNoticeRequired=false 场景允许空 safetyNotice。"""
    draft = DraftCopyJSON(
        title="标题",
        summary="摘要",
        evidence=["证据"],
        recommendation="建议",
        when_to_see_vet="就医条件",
        safety_notice="",
        primary_action=ActionItem(label="休息观察", route="rest_observe"),
    )
    assert draft.safety_notice == ""


def test_draft_copy_json_rejects_empty_evidence_string() -> None:
    """evidence 列表中不允许空字符串元素。"""
    with pytest.raises(ValueError, match="evidence"):
        DraftCopyJSON(
            title="标题",
            summary="摘要",
            evidence=["有效", ""],
            recommendation="建议",
            when_to_see_vet="就医条件",
            primary_action=ActionItem(label="联系兽医", route="contact_vet"),
        )
