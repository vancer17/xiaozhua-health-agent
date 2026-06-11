"""WP4 ③-2 行动锁定（route/label 强制回写）单元测试。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from xiaozhua_health_agent.copy import (
    ActionLockOptions,
    DraftParseWarningCode,
    LockedActionField,
    collect_locked_action_mismatches,
    enforce_locked_actions,
    load_copy_knowledge_bundle,
    parse_draft_copy_from_model_text,
    resolve_copy_template,
)
from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.triage import run_triage_core


@pytest.fixture
def mild_fever_resolved() -> object:
    """case #2 的 CopyTemplateResolved。"""
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    dataset = load_health_triage_dataset(cases_path)
    case = dataset.case_by_id("mild_fever_after_exercise")
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    bundle = load_copy_knowledge_bundle()
    return resolve_copy_template(parsed.fact_sheet, triage, bundle=bundle)


def _minimal_draft_payload(
    resolved: object,
    *,
    route_override: str | None = None,
    label_override: str | None = None,
) -> dict[str, Any]:
    """构造最小合法 DraftCopyJSON 载荷（可覆盖 primaryAction 字段）。"""
    primary = resolved.primary_action_draft.model_dump(by_alias=True, mode="json")  # type: ignore[attr-defined]
    if route_override is not None:
        primary["route"] = route_override
    if label_override is not None:
        primary["label"] = label_override
    return {
        "title": "活动后指标偏高",
        "summary": "刚运动后体温略高，建议休息补水后复查。",
        "evidence": list(resolved.evidence_bullets),  # type: ignore[attr-defined]
        "recommendation": "请先休息并补充饮水。",
        "whenToSeeVet": "若休息后仍偏高，请联系兽医。",
        "safetyNotice": "",
        "primaryAction": primary,
        "secondaryAction": None,
    }


def test_collect_locked_action_mismatches_detects_wrong_route(
    mild_fever_resolved: object,
) -> None:
    """未 enforce 时应检测到 route 与 draft 不一致。"""
    payload = _minimal_draft_payload(mild_fever_resolved, route_override="emergency")
    mismatches = collect_locked_action_mismatches(payload, mild_fever_resolved)  # type: ignore[arg-type]
    assert len(mismatches) == 1
    assert mismatches[0].mismatch_kind == LockedActionField.ROUTE
    assert mismatches[0].json_path == "primaryAction.route"


def test_enforce_locked_actions_rewrites_wrong_route(
    mild_fever_resolved: object,
) -> None:
    """enforce 时应整对象回写 draft 并产出 ROUTE_CORRECTED 警告。"""
    resolved = mild_fever_resolved
    payload = _minimal_draft_payload(resolved, route_override="emergency")
    expected_route = resolved.primary_action_draft.route  # type: ignore[attr-defined]

    corrected, warnings = enforce_locked_actions(payload, resolved)  # type: ignore[arg-type]

    assert corrected["primaryAction"]["route"] == expected_route
    assert any(
        warning.code == DraftParseWarningCode.PRIMARY_ACTION_ROUTE_CORRECTED
        for warning in warnings
    )


def test_parse_draft_copy_enforces_route_by_default(
    mild_fever_resolved: object,
) -> None:
    """parse_draft_copy_from_model_text 默认应回写错误 route。"""
    resolved = mild_fever_resolved
    raw = json.dumps(
        _minimal_draft_payload(resolved, route_override="emergency"),
        ensure_ascii=False,
    )
    result = parse_draft_copy_from_model_text(raw, resolved=resolved)  # type: ignore[arg-type]

    assert result.draft.primary_action.route == resolved.primary_action_draft.route  # type: ignore[attr-defined]
    assert any(
        warning.code == DraftParseWarningCode.PRIMARY_ACTION_ROUTE_CORRECTED
        for warning in result.warnings
    )


def test_enforce_locked_actions_disabled_preserves_wrong_route(
    mild_fever_resolved: object,
) -> None:
    """关闭 enforce 时不修改 payload。"""
    resolved = mild_fever_resolved
    payload = _minimal_draft_payload(resolved, route_override="emergency")

    corrected, warnings = enforce_locked_actions(
        payload,
        resolved,  # type: ignore[arg-type]
        options=ActionLockOptions(enforce=False),
    )

    assert corrected["primaryAction"]["route"] == "emergency"
    assert warnings == ()
