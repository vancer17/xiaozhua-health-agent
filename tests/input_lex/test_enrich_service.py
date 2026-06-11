"""KB-INPUT-LEX enrich 编排服务与管道接入测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from xiaozhua_health_agent.copy import load_copy_knowledge_bundle
from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.input_lex import (
    InputLexEnrichOptions,
    enrich_agent_input_payload_async,
    load_input_lex_bundle,
    load_input_lex_bundle_async,
)
from xiaozhua_health_agent.paths import default_input_lex_path
from xiaozhua_health_agent.pipeline import (
    HealthTriagePipelineStage,
    run_health_triage,
)
from xiaozhua_health_agent.pipeline.pipeline_types import HealthTriagePipelineOptions
from xiaozhua_health_agent.schemas import AgentInput


@pytest.fixture
def lex_bundle():
    """默认词表制品 fixture。

    :returns: 已加载的 KB-INPUT-LEX 快照。
    :rtype: xiaozhua_health_agent.input_lex.InputLexBundle
    """
    return load_input_lex_bundle(default_input_lex_path())


@pytest.fixture
def knowledge_bundle():
    """copy 知识资产聚合包 fixture。

    :returns: ``CopyKnowledgeBundle`` 实例。
    :rtype: object
    """
    return load_copy_knowledge_bundle()


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


@pytest.mark.asyncio
async def test_enrich_colloquial_seizure_sets_structured_field(
    lex_bundle,
) -> None:
    """口语「抽搐」应补全 ``userReport.seizure=true``。"""
    payload = _colloquial_seizure_payload()
    result = await enrich_agent_input_payload_async(
        payload,
        bundle=lex_bundle,
        options=InputLexEnrichOptions(build_audit=True, persist_audit=False),
    )

    assert result.skipped is False
    assert result.enriched_payload["userReport"]["seizure"] is True
    assert result.merge_result.applied_patch_count >= 1
    assert result.audit is not None
    assert result.audit.hit_count >= 1


@pytest.mark.asyncio
async def test_enrich_async_loader_matches_sync(lex_bundle) -> None:
    """异步默认词表加载应与同步路径产出一致 bundle 版本。"""
    async_bundle = await load_input_lex_bundle_async(default_input_lex_path())
    assert async_bundle.meta.bundle_version == lex_bundle.meta.bundle_version


def test_pipeline_with_input_lex_enabled_no_regression_on_structured_cases(
    knowledge_bundle,
) -> None:
    """启用 enrich 时 20 个已结构化 case 应保持 riskLevel 与通过状态不变。"""
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    dataset = load_health_triage_dataset(cases_path)
    lex_bundle = load_input_lex_bundle(default_input_lex_path())

    baseline_options = HealthTriagePipelineOptions(
        copy_bundle=knowledge_bundle,
        load_default_copy_bundle=False,
        input_lex_enabled=False,
    )
    enriched_options = HealthTriagePipelineOptions(
        copy_bundle=knowledge_bundle,
        load_default_copy_bundle=False,
        input_lex_enabled=True,
        input_lex_bundle=lex_bundle,
        load_default_input_lex_bundle=False,
        input_lex_enrich_options=InputLexEnrichOptions(
            build_audit=False,
            persist_audit=False,
        ),
    )

    for case in dataset.cases:
        baseline = run_health_triage(
            case.input,
            options=baseline_options,
            copy_bundle=knowledge_bundle,
        )
        enriched = run_health_triage(
            case.input,
            options=enriched_options,
            copy_bundle=knowledge_bundle,
        )

        assert baseline.passed is True, case.case_id
        assert enriched.passed is True, case.case_id
        assert enriched.stage == HealthTriagePipelineStage.COMPLETED
        assert enriched.input_lex_enrich is not None
        assert baseline.output is not None
        assert enriched.output is not None
        assert enriched.output.risk_level == baseline.output.risk_level, case.case_id
        assert enriched.output.confidence == baseline.output.confidence, case.case_id


def test_enriched_payload_passes_agent_input_schema(lex_bundle) -> None:
    """enrich 产出应仍可通过 ``AgentInput`` 校验。"""
    payload = _colloquial_seizure_payload()

    result = asyncio.run(
        enrich_agent_input_payload_async(payload, bundle=lex_bundle),
    )
    validated = AgentInput.model_validate(result.enriched_payload)
    assert validated.user_report.seizure is True
