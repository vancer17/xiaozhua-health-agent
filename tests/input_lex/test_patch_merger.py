"""KB-INPUT-LEX PatchMerger 单测。"""

from __future__ import annotations

import copy

import pytest

from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.input_lex import (
    CorpusBuilder,
    PatchMerger,
    RuleMatcher,
    build_match_corpus,
    load_input_lex_bundle,
    merge_input_lex_patches,
    merge_input_lex_patches_async,
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


def _minimal_input_payload() -> dict[str, object]:
    """构造最小合法 input JSON（口语待补全）fixture。

    :returns: camelCase 入参字典。
    :rtype: dict[str, object]
    """
    dataset = load_health_triage_dataset()
    case = dataset.case_by_id("normal_dog_daily_check")
    assert case is not None
    payload = case.input.model_dump(by_alias=True, mode="json")
    user_report = dict(payload["userReport"])
    user_report.update(
        {
            "text": "刚刚突然抽搐了一阵，口吐白沫",
            "seizure": None,
            "trauma": None,
            "breathingDifficulty": None,
            "pain": None,
            "limping": None,
            "vomiting": "unknown",
            "diarrhea": "unknown",
            "energy": "unknown",
            "appetite": "unknown",
            "drinking": "unknown",
            "symptoms": [],
        },
    )
    payload["userReport"] = user_report
    return payload


def test_force_mode_sets_emergency_seizure_from_colloquial_text(
    lex_bundle,
) -> None:
    """口语「抽搐」应 force 写入 ``userReport.seizure=true``。"""
    payload = _minimal_input_payload()
    agent_input = AgentInput.model_validate(payload)
    corpus = build_match_corpus(agent_input, lex_bundle)
    match_result = RuleMatcher(lex_bundle).match(
        corpus, species=agent_input.pet.species
    )

    merge_result = PatchMerger(lex_bundle).merge(payload, match_result)

    assert merge_result.enriched_payload["userReport"]["seizure"] is True
    assert merge_result.applied_patch_count >= 1
    seizure_records = [
        record
        for record in merge_result.rule_records
        if record.rule_id == "LEX-EMG-SEIZURE-01"
    ]
    assert len(seizure_records) == 1
    patch_apps = seizure_records[0].patch_applications
    seizure_app = next(
        item for item in patch_apps if item.field_path == "userReport.seizure"
    )
    assert seizure_app.action == "applied"
    assert seizure_app.rule_mode == "force"


def test_explicit_ui_wins_blocks_fill_if_unknown_enum(
    lex_bundle,
) -> None:
    """UI 已填 ``vomiting=none`` 时，fill_if_unknown 呕吐规则不得覆盖。"""
    payload = _minimal_input_payload()
    payload["userReport"]["text"] = "从早上吐到现在，吐了三四次"
    payload["userReport"]["vomiting"] = "none"

    agent_input = AgentInput.model_validate(payload)
    corpus = build_match_corpus(agent_input, lex_bundle)
    match_result = RuleMatcher(lex_bundle).match(
        corpus, species=agent_input.pet.species
    )
    merge_result = PatchMerger(lex_bundle).merge(payload, match_result)

    assert merge_result.enriched_payload["userReport"]["vomiting"] == "none"


def test_enum_escalation_upgrades_vomiting_to_repeated(
    lex_bundle,
) -> None:
    """反复呕吐口语在 unknown 时应升级为 ``repeated``。"""
    payload = _minimal_input_payload()
    payload["userReport"]["text"] = "从早上吐到现在，吐了三四次"
    payload["userReport"]["vomiting"] = "unknown"

    agent_input = AgentInput.model_validate(payload)
    corpus = build_match_corpus(agent_input, lex_bundle)
    match_result = RuleMatcher(lex_bundle).match(
        corpus, species=agent_input.pet.species
    )
    merge_result = PatchMerger(lex_bundle).merge(payload, match_result)

    assert merge_result.enriched_payload["userReport"]["vomiting"] == "repeated"


def test_emergency_boolean_sticky_prevents_downgrade(
    lex_bundle,
) -> None:
    """紧急布尔 sticky：``seizure=true`` 后不得被后续规则写回 ``false``。"""
    payload = _minimal_input_payload()
    merger = PatchMerger(lex_bundle)

    first = merger.merge(
        payload,
        RuleMatcher(lex_bundle).match(
            CorpusBuilder(lex_bundle).build(
                AgentInput.model_validate(
                    {
                        **payload,
                        "userReport": {
                            **payload["userReport"],
                            "text": "突然抽搐",
                            "seizure": None,
                        },
                    },
                ),
            ),
            species="dog",
        ),
    )
    assert first.enriched_payload["userReport"]["seizure"] is True

    downgraded_payload = copy.deepcopy(first.enriched_payload)
    downgraded_payload["userReport"]["text"] = "没事应该正常"
    synthetic_hit = merger.merge(
        downgraded_payload,
        RuleMatcher(lex_bundle).match(
            CorpusBuilder(lex_bundle).build(
                AgentInput.model_validate(downgraded_payload),
            ),
            species="dog",
        ),
    )
    assert synthetic_hit.enriched_payload["userReport"]["seizure"] is True


def test_energy_normal_blocked_when_already_lower(
    lex_bundle,
) -> None:
    """``energy=lower`` 时不得被补丁写回 ``normal``。"""
    payload = _minimal_input_payload()
    payload["userReport"]["text"] = "看着挺好，应该没事"
    payload["userReport"]["energy"] = "lower"

    agent_input = AgentInput.model_validate(payload)
    corpus = build_match_corpus(agent_input, lex_bundle)
    match_result = RuleMatcher(lex_bundle).match(
        corpus, species=agent_input.pet.species
    )
    merge_result = PatchMerger(lex_bundle).merge(payload, match_result)

    assert merge_result.enriched_payload["userReport"]["energy"] == "lower"


def test_append_deduplicates_symptoms(
    lex_bundle,
) -> None:
    """``append`` 在 ``appendDeduplicate=true`` 时不重复追加症状。"""
    payload = _minimal_input_payload()
    payload["userReport"]["text"] = "张口呼吸，很难受"
    payload["userReport"]["symptoms"] = ["张口呼吸"]

    agent_input = AgentInput.model_validate(payload)
    corpus = build_match_corpus(agent_input, lex_bundle)
    match_result = RuleMatcher(lex_bundle).match(
        corpus, species=agent_input.pet.species
    )
    merge_result = PatchMerger(lex_bundle).merge(payload, match_result)

    symptoms = merge_result.enriched_payload["userReport"]["symptoms"]
    assert symptoms.count("张口呼吸") == 1


def test_20_cases_unchanged_when_structured_fields_already_set(
    lex_bundle,
) -> None:
    """20 case 已填结构化字段时 enrich 不得改变关键风险字段。"""
    dataset = load_health_triage_dataset()
    merger = PatchMerger(lex_bundle)

    for case in dataset.cases:
        original = case.input.model_dump(by_alias=True, mode="json")
        corpus = build_match_corpus(case.input, lex_bundle)
        match_result = RuleMatcher(lex_bundle).match(
            corpus,
            species=case.input.pet.species,
        )
        merged = merger.merge(original, match_result).enriched_payload

        assert merged["userReport"]["seizure"] == original["userReport"]["seizure"]
        assert merged["userReport"]["vomiting"] == original["userReport"]["vomiting"]
        assert (
            merged["userReport"]["breathingDifficulty"]
            == (original["userReport"]["breathingDifficulty"])
        )


@pytest.mark.asyncio
async def test_merge_input_lex_patches_async_matches_sync(
    lex_bundle,
) -> None:
    """异步合并结果应与同步路径一致。"""
    payload = _minimal_input_payload()
    agent_input = AgentInput.model_validate(payload)
    corpus = build_match_corpus(agent_input, lex_bundle)
    match_result = RuleMatcher(lex_bundle).match(
        corpus, species=agent_input.pet.species
    )

    sync_result = merge_input_lex_patches(lex_bundle, payload, match_result)
    async_result = await merge_input_lex_patches_async(
        lex_bundle,
        payload,
        match_result,
    )

    assert async_result.enriched_payload == sync_result.enriched_payload
    assert async_result.applied_patch_count == sync_result.applied_patch_count
