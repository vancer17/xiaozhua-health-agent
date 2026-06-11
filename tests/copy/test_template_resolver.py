"""WP4 ③-1 模板解析器测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.copy import (
    build_template_id,
    clear_default_copy_knowledge_cache,
    load_copy_knowledge_bundle,
    resolve_copy_template,
)
from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.triage import run_triage_core


@pytest.fixture(autouse=True)
def _clear_copy_bundle_cache() -> None:
    """每个测试前清空默认知识包缓存。"""
    clear_default_copy_knowledge_cache()


@pytest.fixture
def dataset() -> object:
    """加载 V1 mock case 数据集。"""
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    return load_health_triage_dataset(cases_path)


@pytest.fixture
def knowledge_bundle() -> object:
    """加载完整知识资产聚合包。"""
    return load_copy_knowledge_bundle()


def test_resolve_copy_template_all_cases(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """20 case 均能命中主模板且产出完整 CopyTemplateResolved。"""
    for case in dataset.cases:  # type: ignore[attr-defined]
        parsed = parse_input(case.input)
        assert parsed.passed and parsed.fact_sheet is not None
        triage = run_triage_core(parsed.fact_sheet)
        resolved = resolve_copy_template(
            parsed.fact_sheet,
            triage,
            bundle=knowledge_bundle,  # type: ignore[arg-type]
        )

        expected_template_id = build_template_id(
            final_risk_level=triage.final_risk_level,
            primary_flag=triage.primary_flag,
        )
        assert resolved.template_id == expected_template_id
        assert resolved.resolved_lookup_key == expected_template_id
        assert resolved.used_fallback is False
        assert resolved.risk_level_mismatch is False
        assert resolved.title_pattern
        assert len(resolved.summary_outline) >= 2
        assert resolved.recommendation_template
        assert resolved.when_to_see_vet_template
        assert resolved.evidence_bullets == triage.evidence_bullets
        assert resolved.required_mentions == triage.forced_mentions
        assert resolved.primary_action_hint == triage.primary_action_hint
        assert resolved.primary_action_draft.label
        assert resolved.forbidden
        assert "确诊为" in resolved.forbidden


def test_post_exercise_primary_vital_temperature(
    dataset: object, knowledge_bundle: object
) -> None:
    """case #2：POST_EXERCISE 优先突出体温槽位。"""
    case = dataset.case_by_id("mild_fever_after_exercise")  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    assert resolved.template_id == "watch.POST_EXERCISE"
    assert "temperature" in resolved.filled_slots or "°C" in "".join(
        resolved.filled_slots.values()
    )
    assert resolved.filled_slots.get("primaryVital")


def test_post_exercise_primary_vital_heart_rate(
    dataset: object, knowledge_bundle: object
) -> None:
    """case #5：POST_EXERCISE 优先突出心率槽位。"""
    case = dataset.case_by_id("heart_rate_high_after_play")  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    assert resolved.template_id == "watch.POST_EXERCISE"
    assert resolved.filled_slots.get("primaryVital")
    assert "次/分" in resolved.filled_slots.get("primaryVital", "")


def test_emergency_safety_notice_snippet(
    dataset: object, knowledge_bundle: object
) -> None:
    """emergency case 选用 SNIP-EMERGENCY 免责声明。"""
    case = dataset.case_by_id("emergency_breathing_difficulty")  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    assert triage.safety_notice_required is True
    assert "紧急" in resolved.safety_notice_snippet


def test_data_missing_secondary_action(
    dataset: object, knowledge_bundle: object
) -> None:
    """case #10：DATA_MISSING 映射记录症状次行动。"""
    case = dataset.case_by_id("missing_vitals")  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    assert resolved.template_id == "watch.DATA_MISSING"
    assert resolved.secondary_action_draft is not None
    assert resolved.secondary_action_draft.label == "记录症状"


def test_partial_device_appends_inline_summary(
    dataset: object, knowledge_bundle: object
) -> None:
    """partial 数据质量时 summaryOutline 追加不完整提示。"""
    case = dataset.case_by_id("emergency_seizure")  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    assert parsed.fact_sheet.device.data_quality == "partial"
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    assert any("不完整" in line for line in resolved.summary_outline)


def test_fallback_when_template_missing(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """主模板缺失时走 fallback-by-risk。"""
    case = dataset.cases[0]  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)

    stripped_templates = {
        key: value
        for key, value in knowledge_bundle.kb_tpl.templates.items()  # type: ignore[attr-defined]
        if key != "normal.NORMAL_DAILY"
    }
    from xiaozhua_health_agent.copy import CopyKnowledgeBundle

    broken_tpl = knowledge_bundle.kb_tpl.model_copy(  # type: ignore[attr-defined]
        update={"templates": stripped_templates}
    )
    broken_bundle = CopyKnowledgeBundle(
        kb_tpl=broken_tpl,
        kb_action=knowledge_bundle.kb_action,  # type: ignore[attr-defined]
        kb_forbid=knowledge_bundle.kb_forbid,  # type: ignore[attr-defined]
    )
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=broken_bundle,
    )
    assert resolved.used_fallback is True
    assert resolved.resolved_lookup_key == "normal"
