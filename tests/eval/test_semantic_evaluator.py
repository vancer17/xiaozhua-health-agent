"""语义评测器与 full-output 组合测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.eval import (
    BatchRunConfig,
    BatchRunMode,
    SynonymMap,
    assert_full_output_hard_gate,
    build_corpus_bundle,
    check_forbidden_patterns,
    check_must_mention,
    check_must_not_mention,
    load_health_triage_dataset,
    make_golden_full_outputs_from_dataset,
    normalize_text,
    run_batch,
    run_full_output_evaluation,
)
from xiaozhua_health_agent.schemas import AgentOutput


@pytest.fixture
def dataset() -> object:
    """加载 V1 mock case 数据集。

    :returns: ``HealthTriageDataset`` 实例。
    """
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    return load_health_triage_dataset(cases_path)


def test_must_mention_passes_when_keywords_present(dataset: object) -> None:
    """mustMention 关键词出现在 summary 时应通过。"""
    case = dataset.case_by_id("mild_fever_after_exercise")  # type: ignore[attr-defined]
    output = make_golden_full_outputs_from_dataset(dataset)[case.case_id]  # type: ignore[arg-type]
    parsed = AgentOutput.model_validate(output)
    corpus = build_corpus_bundle(parsed)
    result = check_must_mention(
        expected=case.expected,
        corpus=corpus,
        synonym_map=SynonymMap(),
        case_id=case.case_id,
    )
    assert result.passed is True


def test_must_mention_fails_when_keyword_missing(dataset: object) -> None:
    """缺少 mustMention 关键词时应失败。"""
    case = dataset.case_by_id("mild_fever_after_exercise")  # type: ignore[attr-defined]
    output = make_golden_full_outputs_from_dataset(dataset)[case.case_id]  # type: ignore[arg-type]
    output["summary"] = "没有任何相关关键词。"
    parsed = AgentOutput.model_validate(output)
    corpus = build_corpus_bundle(parsed)
    result = check_must_mention(
        expected=case.expected,
        corpus=corpus,
        synonym_map=SynonymMap(),
        case_id=case.case_id,
    )
    assert result.passed is False
    assert len(result.missing_keywords) > 0


def test_must_not_mention_detects_forbidden_keyword(dataset: object) -> None:
    """mustNotMention 命中时应产生违规。"""
    case = dataset.case_by_id("normal_dog_daily_check")  # type: ignore[attr-defined]
    output = make_golden_full_outputs_from_dataset(dataset)[case.case_id]  # type: ignore[arg-type]
    output["summary"] = "这是确诊结论。"
    parsed = AgentOutput.model_validate(output)
    corpus = build_corpus_bundle(parsed)
    result = check_must_not_mention(
        expected=case.expected,
        segments=corpus.segments,
        case_id=case.case_id,
    )
    assert result.passed is False


def test_forbidden_pattern_detects_schema_phrase(dataset: object) -> None:
    """全局禁止词「确诊为」应被检出。"""
    case = dataset.case_by_id("normal_dog_daily_check")  # type: ignore[attr-defined]
    output = make_golden_full_outputs_from_dataset(dataset)[case.case_id]  # type: ignore[arg-type]
    output["recommendation"] = "确诊为胃炎。"
    parsed = AgentOutput.model_validate(output)
    corpus = build_corpus_bundle(parsed)
    result = check_forbidden_patterns(
        segments=corpus.segments,
        case_id=case.case_id,
    )
    assert result.passed is False


def test_synonym_map_expands_must_mention(dataset: object) -> None:
    """KB-SYN 同义词扩展后应能匹配变体表述。"""
    case = dataset.case_by_id("mild_fever_after_exercise")  # type: ignore[attr-defined]
    output = make_golden_full_outputs_from_dataset(dataset)[case.case_id]  # type: ignore[arg-type]
    output["summary"] = "建议让它歇一会并喝水，稍后复查。"
    parsed = AgentOutput.model_validate(output)
    corpus = build_corpus_bundle(parsed)
    synonym_map = SynonymMap(
        global_synonyms={
            "休息": ["歇一会"],
            "补水": ["喝水"],
        }
    )
    result = check_must_mention(
        expected=case.expected,
        corpus=corpus,
        synonym_map=synonym_map,
        case_id=case.case_id,
    )
    assert "休息" not in normalize_text(output["summary"])
    assert result.passed is True


def test_golden_full_output_batch_passes(dataset: object) -> None:
    """golden full stub 应对 20 case full-output 硬门槛全绿。"""
    outputs = make_golden_full_outputs_from_dataset(dataset)  # type: ignore[arg-type]
    report = run_full_output_evaluation(dataset, outputs)  # type: ignore[arg-type]
    assert_full_output_hard_gate(report)


def test_batch_runner_full_output_mode(dataset: object) -> None:
    """``run_batch`` full-output 模式应产出 ``FullEvalReport``。"""
    config = BatchRunConfig(
        mode=BatchRunMode.FULL_OUTPUT.value,
        use_golden_outputs=True,
    )
    report = run_batch(config, dataset=dataset)  # type: ignore[arg-type]
    assert report.mode == "full-output"
    assert report.passed == report.total == 20
