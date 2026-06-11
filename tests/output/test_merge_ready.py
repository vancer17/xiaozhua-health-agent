"""WP5 merge-ready draft 契约单元测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.copy import (
    generate_mechanical_draft,
    load_copy_knowledge_bundle,
    resolve_copy_template,
)
from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.output import (
    MergeReadyError,
    assert_merge_ready,
    check_merge_ready,
)
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.pipeline import (
    HealthTriagePipelineStage,
    attempt_merge_and_validate_once,
)
from xiaozhua_health_agent.triage import run_triage_core


@pytest.fixture
def dataset() -> object:
    """加载 V1 mock case 数据集。

    :returns: ``HealthTriageDataset`` 实例。
    :rtype: object
    """
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    return load_health_triage_dataset(cases_path)


@pytest.fixture
def knowledge_bundle() -> object:
    """加载 copy 知识资产聚合包。

    :returns: ``CopyKnowledgeBundle`` 实例。
    :rtype: object
    """
    return load_copy_knowledge_bundle()


def test_mechanical_draft_passes_merge_ready(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """机械文案应对典型 case 满足 merge-ready 契约。"""
    case = dataset.case_by_id("emergency_seizure")  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    draft = generate_mechanical_draft(resolved).draft

    result = check_merge_ready(draft, triage)
    assert result.passed is True
    assert result.draft is not None
    assert len(result.violations) == 0


def test_empty_safety_fails_when_required(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """safetyNoticeRequired=true 且 safetyNotice 为空时应失败。"""
    case = dataset.case_by_id("emergency_seizure")  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    draft = generate_mechanical_draft(resolved).draft.model_copy(
        update={"safety_notice": ""},
        deep=True,
    )

    result = check_merge_ready(draft, triage)
    assert result.passed is False
    assert any(v.path == "safetyNotice" for v in result.violations)


def test_assert_merge_ready_raises(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """``assert_merge_ready`` 在契约不满足时应抛出 ``MergeReadyError``。"""
    case = dataset.case_by_id("high_fever_resting")  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    bad_draft = generate_mechanical_draft(resolved).draft.model_copy(
        update={"title": "   "},
        deep=True,
    )

    with pytest.raises(MergeReadyError) as exc_info:
        assert_merge_ready(bad_draft, triage)

    assert len(exc_info.value.violations) > 0


def test_attempt_merge_stops_at_merge_ready_stage(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """``attempt_merge_and_validate_once`` 在 merge-ready 失败时应停在 merge_ready 阶段。"""
    case = dataset.case_by_id("emergency_breathing_difficulty")  # type: ignore[attr-defined]
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(
        parsed.fact_sheet,
        triage,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    bad_draft = generate_mechanical_draft(resolved).draft.model_copy(
        update={"safety_notice": ""},
        deep=True,
    )

    attempt = attempt_merge_and_validate_once(
        triage=triage,
        draft=bad_draft,
        skip_final_schema_check=False,
    )

    assert attempt.passed is False
    assert attempt.stage == HealthTriagePipelineStage.MERGE_READY
    assert attempt.output is None
    assert len(attempt.violations) > 0
