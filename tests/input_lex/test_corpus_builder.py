"""KB-INPUT-LEX CorpusBuilder 单测。"""

from __future__ import annotations

import pytest

from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.input_lex import (
    CorpusBuilder,
    InputLexCorpusBuildError,
    build_match_corpus,
    build_match_corpus_async,
    build_match_corpus_from_mapping,
    build_match_corpus_from_mapping_async,
    load_input_lex_bundle,
    normalize_match_text,
)
from xiaozhua_health_agent.paths import default_input_lex_path
from xiaozhua_health_agent.schemas import AgentInput


@pytest.fixture
def lex_bundle():
    """默认词表制品 fixture。

    :returns: 已加载的 KB-INPUT-LEX 快照。
    :rtype: xiaozhua_health_agent.input_lex.InputLexBundle
    """
    return load_input_lex_bundle(default_input_lex_path())


@pytest.fixture
def emergency_seizure_input() -> AgentInput:
    """抽搐紧急 case 入参 fixture。

    :returns: ``emergency_seizure`` 的 ``AgentInput``。
    :rtype: AgentInput
    """
    dataset = load_health_triage_dataset()
    case = dataset.case_by_id("emergency_seizure")
    assert case is not None
    return case.input


def test_normalize_match_text_collapses_whitespace(lex_bundle) -> None:
    """空白折叠应与 matchDefaults 一致。"""
    normalized = normalize_match_text(
        "  刚 跑 完  ",
        match_defaults=lex_bundle.match_defaults,
    )
    assert normalized == "刚跑完"


def test_corpus_builder_collects_three_sources(
    lex_bundle,
    emergency_seizure_input: AgentInput,
) -> None:
    """应展开 text、symptoms、notes 三类来源。"""
    builder = CorpusBuilder(lex_bundle)
    corpus = builder.build(emergency_seizure_input)

    assert corpus.match_sources == (
        "userReport.text",
        "userReport.symptoms",
        "context.notes",
    )
    assert len(corpus.segments) >= 1
    text_segments = [
        segment for segment in corpus.segments if segment.source == "userReport.text"
    ]
    assert len(text_segments) == 1
    assert "抽搐" in text_segments[0].raw_text
    assert "抽搐" in corpus.merged


def test_merged_contains_symptoms_and_notes(lex_bundle) -> None:
    """symptoms 与 notes 应并入合并语料。"""
    agent_input = AgentInput.model_validate(
        {
            "caseId": "lex-corpus-test",
            "scene": "health_triage",
            "timestamp": "2026-06-08T12:00:00+08:00",
            "pet": {
                "petId": "pet-lex",
                "name": "测试",
                "species": "dog",
                "ageMonths": 24,
                "weightKg": 10.0,
            },
            "device": {
                "deviceOnline": True,
                "dataQuality": "good",
            },
            "vitals": {},
            "healthEvidence": {
                "riskLevel": "unknown",
                "riskLabel": "未知",
                "displayClaim": "测试",
                "recommendationText": "测试",
                "confidence": "low",
                "signals": [],
            },
            "userReport": {
                "text": "今天还好",
                "symptoms": ["呕吐", "精神差"],
            },
            "context": {
                "notes": ["刚运动", "环境变化"],
            },
            "missingData": [],
        }
    )
    corpus = CorpusBuilder(lex_bundle).build(agent_input)
    assert "呕吐" in corpus.merged
    assert "精神差" in corpus.merged
    assert "刚运动" in corpus.merged
    assert "环境变化" in corpus.merged
    assert corpus.normalized_texts_for_source("userReport.symptoms") == (
        "呕吐",
        "精神差",
    )


@pytest.mark.asyncio
async def test_build_match_corpus_async_matches_sync(
    lex_bundle,
    emergency_seizure_input: AgentInput,
) -> None:
    """异步构建应与同步结果一致。"""
    sync_corpus = build_match_corpus(emergency_seizure_input, lex_bundle)
    async_corpus = await build_match_corpus_async(
        emergency_seizure_input,
        lex_bundle,
    )
    assert sync_corpus.merged == async_corpus.merged
    assert len(sync_corpus.segments) == len(async_corpus.segments)


@pytest.mark.asyncio
async def test_build_from_mapping_async(
    lex_bundle,
    emergency_seizure_input: AgentInput,
) -> None:
    """mapping 异步路径应成功并包含关键短语。"""
    payload = emergency_seizure_input.model_dump(by_alias=True, mode="json")
    corpus = await build_match_corpus_from_mapping_async(payload, lex_bundle)
    assert corpus.contains_normalized_phrase("抽搐")


def test_build_from_mapping_invalid_payload_raises(lex_bundle) -> None:
    """非法入参应抛出 InputLexCorpusBuildError。"""
    with pytest.raises(InputLexCorpusBuildError, match="AgentInput 校验失败"):
        build_match_corpus_from_mapping({"caseId": "only-id"}, lex_bundle)


def test_all_cases_produce_non_empty_text_segment(lex_bundle) -> None:
    """20 case 均应能构建含 userReport.text 的语料。"""
    dataset = load_health_triage_dataset()
    builder = CorpusBuilder(lex_bundle)
    for case in dataset.cases:
        corpus = builder.build(case.input)
        text_parts = corpus.normalized_texts_for_source("userReport.text")
        assert len(text_parts) == 1
        assert text_parts[0]
