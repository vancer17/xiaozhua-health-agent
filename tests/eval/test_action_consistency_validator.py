"""WP4 ④-B 行动锁定一致性校验单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.copy import (
    DraftCopyJSON,
    load_copy_knowledge_bundle,
    resolve_copy_template,
)
from xiaozhua_health_agent.eval import (
    ViolationCode,
    load_health_triage_dataset,
    validate_locked_draft_actions,
)
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.schemas import ActionItem
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


def test_validate_locked_draft_actions_passes_when_aligned(
    mild_fever_resolved: object,
) -> None:
    """与 draft 一致时不应产出违规。"""
    resolved = mild_fever_resolved
    draft = DraftCopyJSON(
        title="活动后指标偏高",
        summary="刚运动后体温略高，建议休息补水后复查。",
        evidence=list(resolved.evidence_bullets),  # type: ignore[attr-defined]
        recommendation="请先休息并补充饮水。",
        when_to_see_vet="若休息后仍偏高，请联系兽医。",
        safety_notice="",
        primary_action=resolved.primary_action_draft,  # type: ignore[attr-defined]
        secondary_action=None,
    )

    violations = validate_locked_draft_actions(draft, resolved)  # type: ignore[arg-type]

    assert violations == ()


def test_validate_locked_draft_actions_detects_route_mismatch(
    mild_fever_resolved: object,
) -> None:
    """route 不一致时应产出 ACTION_ROUTE_MISMATCH。"""
    resolved = mild_fever_resolved
    expected = resolved.primary_action_draft  # type: ignore[attr-defined]
    wrong_primary = ActionItem(label=expected.label, route="emergency")
    draft = DraftCopyJSON(
        title="活动后指标偏高",
        summary="刚运动后体温略高，建议休息补水后复查。",
        evidence=list(resolved.evidence_bullets),  # type: ignore[attr-defined]
        recommendation="请先休息并补充饮水。",
        when_to_see_vet="若休息后仍偏高，请联系兽医。",
        safety_notice="",
        primary_action=wrong_primary,
        secondary_action=None,
    )

    violations = validate_locked_draft_actions(draft, resolved)  # type: ignore[arg-type]

    assert len(violations) == 1
    assert violations[0].code == ViolationCode.ACTION_ROUTE_MISMATCH.value
    assert violations[0].path == "primaryAction.route"
