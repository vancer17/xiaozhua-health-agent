"""KB-INPUT-LEX RuleMatcher 单测。"""

from __future__ import annotations

import pytest

from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.input_lex import (
    CorpusBuilder,
    InputLexMatchCorpus,
    RuleMatcher,
    build_match_corpus,
    load_input_lex_bundle,
    match_input_lex_rules,
    match_input_lex_rules_async,
    match_single_input_lex_rule,
    phrase_matches_corpus,
    rule_passes_species_filter,
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


def _build_corpus(
    lex_bundle,
    agent_input: AgentInput,
) -> InputLexMatchCorpus:
    """构建匹配语料（测试辅助）。

    :param lex_bundle: 词表快照。
    :type lex_bundle: xiaozhua_health_agent.input_lex.InputLexBundle
    :param agent_input: 分诊入参。
    :type agent_input: AgentInput
    :returns: 归一化语料。
    :rtype: InputLexMatchCorpus
    """
    return CorpusBuilder(lex_bundle).build(agent_input)


def test_emergency_seizure_hits_seizure_rule(
    lex_bundle,
    emergency_seizure_input: AgentInput,
) -> None:
    """抽搐 case 应命中 LEX-EMG-SEIZURE-01。"""
    corpus = _build_corpus(lex_bundle, emergency_seizure_input)
    result = RuleMatcher(lex_bundle).match(corpus, species="cat")

    hit_ids = {hit.rule.id for hit in result.hits}
    assert "LEX-EMG-SEIZURE-01" in hit_ids

    seizure_hit = next(
        hit for hit in result.hits if hit.rule.id == "LEX-EMG-SEIZURE-01"
    )
    assert seizure_hit.rule.patches.get("userReport.seizure") is True
    assert any("抽搐" in detail.raw_phrase for detail in seizure_hit.matched_phrases)


def test_hits_ordered_by_priority(lex_bundle) -> None:
    """命中列表应按 priority 升序。"""
    agent_input = AgentInput.model_validate(
        {
            "caseId": "lex-priority-test",
            "scene": "health_triage",
            "timestamp": "2026-06-08T10:00:00+08:00",
            "pet": {
                "petId": "p1",
                "name": "测试",
                "species": "dog",
                "ageMonths": 24,
                "weightKg": 10.0,
            },
            "device": {
                "deviceOnline": True,
                "dataQuality": "good",
                "lastSeenAt": "2026-06-08T09:59:00+08:00",
            },
            "vitals": {
                "activityLevel": "resting",
            },
            "healthEvidence": {
                "riskLevel": "unknown",
                "riskLabel": "未知",
                "displayClaim": "",
                "recommendationText": "",
                "confidence": "low",
                "signals": [],
            },
            "userReport": {
                "text": "它抽搐了，看起来没事，刚跑完一圈",
                "symptoms": ["抽搐"],
            },
            "context": {
                "recentExercise": "intense",
                "notes": ["刚运动"],
            },
            "missingData": [],
        }
    )
    corpus = _build_corpus(lex_bundle, agent_input)
    result = match_input_lex_rules(lex_bundle, corpus, species="dog")

    priorities = [hit.rule.priority for hit in result.hits]
    assert priorities == sorted(priorities)
    assert "LEX-EMG-SEIZURE-01" in {hit.rule.id for hit in result.hits}


def test_species_filter_skips_dog_only_rule(lex_bundle) -> None:
    """带 species=dog 的规则在 cat 上下文应被跳过。"""
    rule = lex_bundle.rule_by_id("LEX-BRACHY-BREED-ZH-01")
    assert rule is not None
    assert rule.species == ("dog",)

    assert rule_passes_species_filter(rule, "dog") is True
    assert rule_passes_species_filter(rule, "cat") is False
    assert rule_passes_species_filter(rule, None) is False

    agent_input = AgentInput.model_validate(
        {
            "caseId": "lex-brachy-cat",
            "scene": "health_triage",
            "timestamp": "2026-06-08T10:00:00+08:00",
            "pet": {
                "petId": "p1",
                "name": "猫",
                "species": "cat",
                "ageMonths": 24,
                "weightKg": 4.0,
            },
            "device": {
                "deviceOnline": True,
                "dataQuality": "good",
                "lastSeenAt": "2026-06-08T09:59:00+08:00",
            },
            "vitals": {},
            "healthEvidence": {
                "riskLevel": "unknown",
                "riskLabel": "未知",
                "displayClaim": "",
                "recommendationText": "",
                "confidence": "low",
                "signals": [],
            },
            "userReport": {
                "text": "它是法斗混血",
                "symptoms": [],
            },
            "context": {},
            "missingData": [],
        }
    )
    corpus = _build_corpus(lex_bundle, agent_input)

    without_species = RuleMatcher(lex_bundle).match(corpus, species=None)
    with_cat = RuleMatcher(lex_bundle).match(corpus, species="cat")
    with_dog = RuleMatcher(lex_bundle).match(corpus, species="dog")

    assert "LEX-BRACHY-BREED-ZH-01" not in {h.rule.id for h in without_species.hits}
    assert "LEX-BRACHY-BREED-ZH-01" not in {h.rule.id for h in with_cat.hits}
    assert "LEX-BRACHY-BREED-ZH-01" in {h.rule.id for h in with_dog.hits}
    assert with_cat.skipped_species_filter_count >= 1


def test_phrase_matches_merged_corpus(lex_bundle) -> None:
    """子串匹配应在合并语料上生效。"""
    agent_input = AgentInput.model_validate(
        {
            "caseId": "lex-phrase",
            "scene": "health_triage",
            "timestamp": "2026-06-08T10:00:00+08:00",
            "pet": {
                "petId": "p1",
                "name": "狗",
                "species": "dog",
                "ageMonths": 24,
                "weightKg": 10.0,
            },
            "device": {
                "deviceOnline": True,
                "dataQuality": "good",
                "lastSeenAt": "2026-06-08T09:59:00+08:00",
            },
            "vitals": {},
            "healthEvidence": {
                "riskLevel": "normal",
                "riskLabel": "正常",
                "displayClaim": "",
                "recommendationText": "",
                "confidence": "high",
                "signals": [],
            },
            "userReport": {
                "text": "今天刚遛完一圈，有点喘",
                "symptoms": [],
            },
            "context": {"notes": []},
            "missingData": [],
        }
    )
    corpus = build_match_corpus(agent_input, lex_bundle)
    assert "刚遛" in corpus.merged or "遛完" in corpus.merged

    result = RuleMatcher(lex_bundle).match(corpus, species="dog")
    exercise_hit_ids = {
        hit.rule.id
        for hit in result.hits
        if "EXERCISE" in hit.rule.id or hit.rule.intent.startswith("post_exercise")
    }
    assert len(exercise_hit_ids) >= 1


@pytest.mark.asyncio
async def test_match_input_lex_rules_async(
    lex_bundle,
    emergency_seizure_input: AgentInput,
) -> None:
    """异步匹配应与同步结果一致。"""
    corpus = _build_corpus(lex_bundle, emergency_seizure_input)
    sync_result = match_input_lex_rules(lex_bundle, corpus, species="cat")
    async_result = await match_input_lex_rules_async(
        lex_bundle,
        corpus,
        species="cat",
    )

    assert async_result.bundle_version == sync_result.bundle_version
    assert [hit.rule.id for hit in async_result.hits] == [
        hit.rule.id for hit in sync_result.hits
    ]


def test_match_single_rule_returns_none_when_no_phrase_hit(lex_bundle) -> None:
    """无语料命中时单条规则应返回 None。"""
    rule = lex_bundle.rule_by_id("LEX-EMG-SEIZURE-01")
    assert rule is not None

    agent_input = AgentInput.model_validate(
        {
            "caseId": "lex-no-hit",
            "scene": "health_triage",
            "timestamp": "2026-06-08T10:00:00+08:00",
            "pet": {
                "petId": "p1",
                "name": "狗",
                "species": "dog",
                "ageMonths": 24,
                "weightKg": 10.0,
            },
            "device": {
                "deviceOnline": True,
                "dataQuality": "good",
                "lastSeenAt": "2026-06-08T09:59:00+08:00",
            },
            "vitals": {},
            "healthEvidence": {
                "riskLevel": "normal",
                "riskLabel": "正常",
                "displayClaim": "",
                "recommendationText": "",
                "confidence": "high",
                "signals": [],
            },
            "userReport": {
                "text": "一切正常",
                "symptoms": [],
            },
            "context": {},
            "missingData": [],
        }
    )
    corpus = _build_corpus(lex_bundle, agent_input)
    assert match_single_input_lex_rule(rule, corpus, species="dog") is None


def test_phrase_matches_corpus_helper(lex_bundle) -> None:
    """phrase_matches_corpus 应对合并语料子串返回 True。"""
    corpus = InputLexMatchCorpus(
        merged="刚刚抽搐了一阵",
        segments=(),
        match_sources=("userReport.text",),
        match_defaults=lex_bundle.match_defaults,
    )
    assert phrase_matches_corpus("抽搐", corpus) is True
    assert phrase_matches_corpus("骨折", corpus) is False
