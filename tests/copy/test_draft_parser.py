"""WP4 ③-2 draft_parser 单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xiaozhua_health_agent.copy import (
    DraftParseError,
    DraftParseWarningCode,
    backfill_draft_payload,
    extract_json_object_text,
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


def test_extract_json_object_text_from_markdown_fence() -> None:
    """应从 Markdown 围栏中提取 JSON。"""
    raw = '说明\n```json\n{"title": "测试"}\n```\n'
    json_text, warnings = extract_json_object_text(raw)
    assert json.loads(json_text)["title"] == "测试"
    assert any(
        warning.code == DraftParseWarningCode.JSON_EXTRACTED_FROM_FENCE
        for warning in warnings
    )


def test_extract_json_object_text_brace_scan() -> None:
    """应从夹杂文本中扫描首个 JSON 对象。"""
    raw = '请查看：{"title":"活动后观察","summary":"休息补水"} 谢谢'
    json_text, warnings = extract_json_object_text(raw)
    payload = json.loads(json_text)
    assert payload["title"] == "活动后观察"
    assert any(
        warning.code == DraftParseWarningCode.JSON_EXTRACTED_BY_BRACE_SCAN
        for warning in warnings
    )


def test_parse_draft_copy_strips_ruling_fields_and_backfills(
    mild_fever_resolved: object,
) -> None:
    """应丢弃 riskLevel 等字段并回填 primaryAction / safetyNotice。"""
    resolved = mild_fever_resolved
    raw = json.dumps(
        {
            "title": "活动后指标偏高",
            "summary": "刚运动后体温略高，建议休息补水后复查。",
            "evidence": list(resolved.evidence_bullets),
            "recommendation": "请先休息并补充饮水。",
            "whenToSeeVet": "若休息后仍偏高，请联系兽医。",
            "safetyNotice": "",
            "riskLevel": "watch",
            "confidence": "medium",
        },
        ensure_ascii=False,
    )
    result = parse_draft_copy_from_model_text(raw, resolved=resolved)

    assert result.draft.title == "活动后指标偏高"
    assert result.draft.primary_action.label == resolved.primary_action_draft.label
    if resolved.safety_notice_snippet.strip():
        assert result.draft.safety_notice == resolved.safety_notice_snippet
    assert "riskLevel" in result.stripped_ruling_fields


def test_backfill_evidence_on_invalid_list(mild_fever_resolved: object) -> None:
    """evidence 非法时应降级为 evidenceBullets。"""
    resolved = mild_fever_resolved
    payload = {
        "title": "标题",
        "summary": "摘要内容足够长。",
        "evidence": [123, ""],
        "recommendation": "建议",
        "whenToSeeVet": "就医条件",
        "primaryAction": resolved.primary_action_draft.model_dump(by_alias=True),
    }
    backfilled, warnings = backfill_draft_payload(payload, resolved)  # type: ignore[arg-type]
    assert backfilled["evidence"] == list(resolved.evidence_bullets)
    assert any(
        warning.code == DraftParseWarningCode.EVIDENCE_BACKFILLED
        for warning in warnings
    )


def test_parse_draft_copy_raises_on_invalid_json(mild_fever_resolved: object) -> None:
    """非法 JSON 应抛出 DraftParseError。"""
    with pytest.raises(DraftParseError, match="JSON"):
        parse_draft_copy_from_model_text("{not-json", resolved=mild_fever_resolved)  # type: ignore[arg-type]


def test_parse_draft_copy_corrects_wrong_primary_route(
    mild_fever_resolved: object,
) -> None:
    """LLM 输出错误 primaryAction.route 时应强制回写 draft。"""
    resolved = mild_fever_resolved
    primary = resolved.primary_action_draft.model_dump(by_alias=True, mode="json")  # type: ignore[attr-defined]
    primary["route"] = "emergency"
    raw = json.dumps(
        {
            "title": "活动后指标偏高",
            "summary": "刚运动后体温略高，建议休息补水后复查。",
            "evidence": list(resolved.evidence_bullets),  # type: ignore[attr-defined]
            "recommendation": "请先休息并补充饮水。",
            "whenToSeeVet": "若休息后仍偏高，请联系兽医。",
            "safetyNotice": "",
            "primaryAction": primary,
        },
        ensure_ascii=False,
    )
    result = parse_draft_copy_from_model_text(raw, resolved=resolved)  # type: ignore[arg-type]

    assert result.draft.primary_action.route == resolved.primary_action_draft.route  # type: ignore[attr-defined]
    assert any(
        warning.code == DraftParseWarningCode.PRIMARY_ACTION_ROUTE_CORRECTED
        for warning in result.warnings
    )
