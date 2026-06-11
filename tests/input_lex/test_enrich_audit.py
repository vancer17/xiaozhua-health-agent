"""KB-INPUT-LEX EnrichAudit 单测。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.input_lex import (
    EnrichAudit,
    InputLexEnrichAuditBuildOptions,
    InputLexEnrichAuditPersistOptions,
    PatchMerger,
    RuleMatcher,
    build_enrich_audit_record,
    build_enrich_audit_record_async,
    build_match_corpus,
    load_input_lex_bundle,
    persist_enrich_audit_record_async,
    serialize_enrich_audit_record_to_json,
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


def _colloquial_seizure_payload() -> dict[str, object]:
    """构造含口语抽搐、结构化字段待补全的入参 fixture。

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


def test_build_enrich_audit_record_links_match_and_merge(
    lex_bundle,
) -> None:
    """审计记录应聚合命中短语、补丁明细与字段变更。"""
    payload = _colloquial_seizure_payload()
    agent_input = AgentInput.model_validate(payload)
    corpus = build_match_corpus(agent_input, lex_bundle)
    match_result = RuleMatcher(lex_bundle).match(corpus, species=agent_input.pet.species)
    merge_result = PatchMerger(lex_bundle).merge(payload, match_result)

    audit = build_enrich_audit_record(
        match_result=match_result,
        merge_result=merge_result,
        corpus=corpus,
        original_payload=payload,
        bundle=lex_bundle,
    )

    assert audit.case_id == payload["caseId"]
    assert audit.lex_bundle_version == lex_bundle.meta.bundle_version
    assert audit.agent_bundle_pin == lex_bundle.meta.agent_bundle_pin
    assert audit.hit_count == len(match_result.hits)
    assert len(audit.rule_hits) >= 1

    seizure_hit = next(
        item for item in audit.rule_hits if item.rule_id == "LEX-EMG-SEIZURE-01"
    )
    assert seizure_hit.has_effective_change is True
    assert len(seizure_hit.matched_phrases) >= 1
    assert "EMG-01" in seizure_hit.maps_to_agent_rules

    seizure_change = next(
        item
        for item in audit.field_changes
        if item.field_path == "userReport.seizure"
        and item.source_rule_id == "LEX-EMG-SEIZURE-01"
    )
    assert seizure_change.change_kind == "patch"
    assert seizure_change.new_value is True

    assert audit.corpus_summary is not None
    assert audit.corpus_summary.segment_count >= 1
    assert "抽搐" in audit.corpus_summary.merged_text_preview


def test_serialize_enrich_audit_record_roundtrip(
    lex_bundle,
) -> None:
    """审计记录 JSON 序列化应可往返解析。"""
    payload = _colloquial_seizure_payload()
    agent_input = AgentInput.model_validate(payload)
    corpus = build_match_corpus(agent_input, lex_bundle)
    match_result = RuleMatcher(lex_bundle).match(corpus, species=agent_input.pet.species)
    merge_result = PatchMerger(lex_bundle).merge(payload, match_result)

    audit = build_enrich_audit_record(
        match_result=match_result,
        merge_result=merge_result,
        bundle=lex_bundle,
    )
    text = serialize_enrich_audit_record_to_json(audit, indent=2)
    parsed = json.loads(text)

    assert parsed["auditSchemaVersion"] == audit.audit_schema_version
    assert parsed["hitCount"] == audit.hit_count
    assert isinstance(parsed["ruleHits"], list)


@pytest.mark.asyncio
async def test_build_and_persist_enrich_audit_async(
    lex_bundle,
    tmp_path: Path,
) -> None:
    """异步构建与 JSONL 持久化应写入可解析审计行。"""
    payload = _colloquial_seizure_payload()
    agent_input = AgentInput.model_validate(payload)
    corpus = build_match_corpus(agent_input, lex_bundle)
    match_result = RuleMatcher(lex_bundle).match(corpus, species=agent_input.pet.species)
    merge_result = PatchMerger(lex_bundle).merge(payload, match_result)

    audit = await build_enrich_audit_record_async(
        match_result=match_result,
        merge_result=merge_result,
        corpus=corpus,
        original_payload=payload,
        bundle=lex_bundle,
        options=InputLexEnrichAuditBuildOptions(
            include_enriched_payload=True,
        ),
    )

    target = tmp_path / "enrich-audit.jsonl"
    persist_result = await persist_enrich_audit_record_async(
        audit,
        InputLexEnrichAuditPersistOptions(path=str(target)),
    )

    assert persist_result.bytes_written > 0
    assert persist_result.format == "jsonl"
    lines = target.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["enrichedPayload"]["userReport"]["seizure"] is True


def test_enrich_audit_class_facade_matches_module_functions(
    lex_bundle,
) -> None:
    """EnrichAudit 类门面应与模块级便捷函数结果一致。"""
    payload = _colloquial_seizure_payload()
    agent_input = AgentInput.model_validate(payload)
    corpus = build_match_corpus(agent_input, lex_bundle)
    match_result = RuleMatcher(lex_bundle).match(corpus, species=agent_input.pet.species)
    merge_result = PatchMerger(lex_bundle).merge(payload, match_result)

    via_function = build_enrich_audit_record(
        match_result=match_result,
        merge_result=merge_result,
        bundle=lex_bundle,
    )
    via_class = EnrichAudit().build(
        match_result=match_result,
        merge_result=merge_result,
        bundle=lex_bundle,
    )

    assert via_class.model_dump() == via_function.model_dump()
