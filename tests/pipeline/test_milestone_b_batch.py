"""WP5 里程碑 B — 机械管道 full-output 批跑闭环验收测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.copy import load_copy_knowledge_bundle
from xiaozhua_health_agent.eval import EXPECTED_CASE_COUNT, load_health_triage_dataset
from xiaozhua_health_agent.pipeline import (
    DEFAULT_MILESTONE_B_BATCH_CONFIG,
    MilestoneBBatchReport,
    assert_milestone_b_hard_gate,
    assert_milestone_b_pipeline_hard_gate,
    assert_milestone_b_soft_gates,
    format_milestone_b_report,
    milestone_b_report_to_dict,
    run_milestone_b_batch,
    run_milestone_b_batch_async,
    write_milestone_b_json_report,
)


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


def test_milestone_b_batch_sync_hard_gate(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """同步批跑应满足里程碑 B 管道 + full-output 硬门槛（20/20）。"""
    report = run_milestone_b_batch(
        dataset,  # type: ignore[arg-type]
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
    )

    assert isinstance(report, MilestoneBBatchReport)
    assert report.total == EXPECTED_CASE_COUNT
    assert report.mode == "milestone-b"
    assert_milestone_b_pipeline_hard_gate(report)
    assert_milestone_b_hard_gate(report)


@pytest.mark.asyncio
async def test_milestone_b_batch_async_hard_gate(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """异步批跑应与同步路径等价且硬门槛全绿。"""
    report = await run_milestone_b_batch_async(
        dataset,  # type: ignore[arg-type]
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
    )

    assert report.total == EXPECTED_CASE_COUNT
    assert report.pipeline_passed == EXPECTED_CASE_COUNT
    assert report.full_eval.risk_passed == EXPECTED_CASE_COUNT
    assert report.full_eval.semantic_passed == EXPECTED_CASE_COUNT
    assert_milestone_b_hard_gate(report)


def test_milestone_b_soft_gate(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """mustMention 软门槛应 ≥ 18/20。"""
    report = run_milestone_b_batch(
        dataset,  # type: ignore[arg-type]
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
    )

    assert report.must_mention_soft_threshold == (
        DEFAULT_MILESTONE_B_BATCH_CONFIG.must_mention_soft_threshold
    )
    assert_milestone_b_soft_gates(report)


def test_milestone_b_report_serialization(
    dataset: object,
    knowledge_bundle: object,
    tmp_path: Path,
) -> None:
    """文本/JSON 报告序列化应包含管道与 full-output 汇总字段。"""
    report = run_milestone_b_batch(
        dataset,  # type: ignore[arg-type]
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
    )

    text = format_milestone_b_report(report, include_per_case=False)
    assert "milestone-b" in text
    assert f"管道: {EXPECTED_CASE_COUNT}/{EXPECTED_CASE_COUNT} passed" in text

    payload = milestone_b_report_to_dict(report)
    assert payload["pipelinePassed"] == EXPECTED_CASE_COUNT
    assert payload["fullEval"]["riskPassed"] == EXPECTED_CASE_COUNT
    assert len(payload["records"]) == EXPECTED_CASE_COUNT

    json_path = tmp_path / "milestone_b_report.json"
    write_milestone_b_json_report(report, json_path)
    assert json_path.exists()
    assert "pipelinePassed" in json_path.read_text(encoding="utf-8")
