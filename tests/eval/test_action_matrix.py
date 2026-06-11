"""Action 矩阵 fixture 与批跑评测测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.eval.action_matrix import (
    ACTION_MATRIX_SCHEMA_VERSION,
    ActionMatrixLoadError,
    derive_action_matrix_entries,
    entries_match_derived,
    load_action_matrix,
    load_validated_action_matrix,
    validate_action_matrix_fixture,
)
from xiaozhua_health_agent.eval.action_matrix_evaluator import (
    assert_action_matrix_hard_gate,
    assert_fixture_matches_derived_pipeline,
    run_action_matrix_evaluation,
)
from xiaozhua_health_agent.eval.case_dataset import (
    EXPECTED_CASE_COUNT,
    load_health_triage_dataset,
)
from xiaozhua_health_agent.paths import default_action_matrix_path


@pytest.fixture
def dataset() -> object:
    """加载 V1 mock case 数据集。"""
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    return load_health_triage_dataset(cases_path)


@pytest.fixture
def action_matrix_fixture(dataset: object) -> object:
    """加载并校验默认 action 矩阵 fixture。"""
    return load_validated_action_matrix(dataset=dataset)  # type: ignore[arg-type]


def test_default_action_matrix_path_exists() -> None:
    """默认 action 矩阵制品文件应存在。"""
    path = default_action_matrix_path()
    assert path.is_file(), path


def test_action_matrix_loads_and_validates(dataset: object) -> None:
    """fixture 应通过静态校验（KB-ACTION / policy / summary / cases）。"""
    fixture = load_validated_action_matrix(dataset=dataset)  # type: ignore[arg-type]
    assert fixture.meta.schema_version == ACTION_MATRIX_SCHEMA_VERSION
    assert fixture.meta.expected_case_count == EXPECTED_CASE_COUNT
    assert len(fixture.entries) == EXPECTED_CASE_COUNT


def test_action_matrix_fixture_matches_derived_pipeline(
    dataset: object,
    action_matrix_fixture: object,
) -> None:
    """fixture 条目应与当前管道推导完全一致（无漂移）。"""
    assert_fixture_matches_derived_pipeline(
        action_matrix_fixture,  # type: ignore[arg-type]
        dataset,  # type: ignore[arg-type]
    )


def test_derived_entries_have_no_internal_diff(dataset: object) -> None:
    """derive 与 fixture 逐行比对应无差异。"""
    fixture = load_action_matrix()
    derived = derive_action_matrix_entries(dataset)  # type: ignore[arg-type]
    diffs = entries_match_derived(fixture.entries, derived)
    assert diffs == [], "\n".join(diffs)


def test_action_matrix_mechanical_merge_batch_20_20(dataset: object) -> None:
    """机械 + merge 管道应对 20 case action 矩阵硬门槛全绿。"""
    report = run_action_matrix_evaluation(dataset=dataset)  # type: ignore[arg-type]
    assert_action_matrix_hard_gate(report, expected_total=EXPECTED_CASE_COUNT)


def test_action_matrix_summary_counts() -> None:
    """summary 统计应与 entries 自洽。"""
    fixture = load_action_matrix()
    validate_action_matrix_fixture(
        fixture,
        dataset=load_health_triage_dataset(
            Path(__file__).resolve().parents[2]
            / "docs/cases/health_triage_cases.v1.json",
        ),
    )
    assert fixture.summary.with_secondary_action == 2
    assert fixture.summary.hint_counts["emergency_now"] == 2


def test_action_matrix_rejects_bad_schema_version() -> None:
    """非法 schemaVersion 应拒绝加载。"""
    payload = load_action_matrix()
    raw = payload.model_dump(by_alias=True)
    raw["meta"]["schemaVersion"] = "bad"
    with pytest.raises(ActionMatrixLoadError):
        from xiaozhua_health_agent.eval.action_matrix import (
            load_action_matrix_from_json,
        )

        load_action_matrix_from_json(raw)
