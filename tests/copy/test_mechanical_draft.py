"""WP4 ③ 机械文案路径测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.copy import (
    DraftCopyJSON,
    MechanicalDraftOptions,
    clear_default_copy_knowledge_cache,
    generate_mechanical_draft,
    generate_mechanical_draft_from_input,
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


def test_generate_mechanical_draft_all_cases(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """20 case 机械路径均应产出合法 DraftCopyJSON。"""
    for case in dataset.cases:  # type: ignore[attr-defined]
        result = generate_mechanical_draft_from_input(
            case.input,
            bundle=knowledge_bundle,  # type: ignore[arg-type]
            options=MechanicalDraftOptions(append_missing_mentions=True),
        )
        draft = result.draft
        assert isinstance(draft, DraftCopyJSON)
        assert draft.title
        assert draft.summary
        assert draft.recommendation
        assert draft.when_to_see_vet
        assert draft.primary_action.label
        parsed = parse_input(case.input)
        assert parsed.fact_sheet is not None
        triage = run_triage_core(parsed.fact_sheet)
        assert list(draft.evidence) == list(triage.evidence_bullets)


def test_mechanical_evidence_matches_bullets_exactly(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """机械路径 evidence 必须与 ② evidenceBullets 逐条一致。"""
    case = dataset.case_by_id("emergency_breathing_difficulty")  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    result = generate_mechanical_draft(resolved)
    assert result.draft.evidence == list(triage.evidence_bullets)


def test_post_exercise_mechanical_mentions_exercise_context(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """case #2：机械 summary 应体现运动情境。"""
    case = dataset.case_by_id("mild_fever_after_exercise")  # type: ignore[attr-defined]
    result = generate_mechanical_draft_from_input(
        case.input,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    corpus = result.draft.title + result.draft.summary + result.draft.recommendation
    assert "运动" in corpus or "活动" in corpus or "刚" in corpus


def test_data_missing_mechanical_no_normal_claim(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """case #10：机械文案不应声称当前正常。"""
    case = dataset.case_by_id("missing_vitals")  # type: ignore[attr-defined]
    result = generate_mechanical_draft_from_input(
        case.input,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    corpus = result.draft.summary + result.draft.recommendation
    assert "当前正常" not in corpus
    assert "一切正常" not in corpus


def test_safety_notice_when_required(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """safetyNoticeRequired 为 true 时机械 safetyNotice 应非空。"""
    case = dataset.case_by_id("emergency_seizure")  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    assert resolved.safety_notice_snippet
    result = generate_mechanical_draft(resolved)
    assert result.draft.safety_notice.strip()


@pytest.mark.asyncio
async def test_copy_llm_pipeline_use_mechanical(dataset: object) -> None:
    """异步管道 use_mechanical=True 应 passed 且 generator=mechanical。"""
    from xiaozhua_health_agent.copy import generate_draft_copy_async

    case = dataset.case_by_id("normal_dog_daily_check")  # type: ignore[attr-defined]
    result = await generate_draft_copy_async(
        case.input,
        use_mechanical=True,
    )
    assert result.passed is True
    assert result.generator == "mechanical"
    assert result.draft is not None
    assert result.draft.title
