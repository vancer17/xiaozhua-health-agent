"""WP5 MergeOutput 单元与集成测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.copy import (
    DraftCopyJSON,
    MechanicalDraftOptions,
    generate_mechanical_draft_from_input,
    load_copy_knowledge_bundle,
)
from xiaozhua_health_agent.eval import (
    OutputValidationMode,
    load_health_triage_dataset,
    validate_output,
)
from xiaozhua_health_agent.output import MergeOutputError, merge_agent_output
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.schemas import ActionItem
from xiaozhua_health_agent.triage import run_triage_core


@pytest.fixture
def dataset() -> object:
    """加载 V1 mock case 数据集。

    :returns: 解析后的 ``HealthTriageDataset`` 实例。
    :rtype: object
    """
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    return load_health_triage_dataset(cases_path)


@pytest.fixture
def knowledge_bundle() -> object:
    """加载完整 copy 知识资产聚合包。

    :returns: ``CopyKnowledgeBundle`` 实例。
    :rtype: object
    """
    return load_copy_knowledge_bundle()


def test_merge_preserves_primary_and_secondary_actions(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """``primaryAction`` / ``secondaryAction`` 应与草稿对象深拷贝一致。"""
    case = dataset.case_by_id("missing_vitals")  # type: ignore[attr-defined]
    mechanical = generate_mechanical_draft_from_input(
        case.input,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    draft = mechanical.draft
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)

    assert draft.primary_action.route == "check_device"
    assert draft.secondary_action is not None
    assert draft.secondary_action.route == "record_symptom"

    output = merge_agent_output(triage=triage, draft=draft)

    assert output.primary_action.label == draft.primary_action.label
    assert output.primary_action.route == draft.primary_action.route
    assert output.secondary_action is not None
    assert output.secondary_action.label == draft.secondary_action.label
    assert output.secondary_action.route == draft.secondary_action.route
    assert output.primary_action is not draft.primary_action
    assert output.secondary_action is not draft.secondary_action


def test_merge_does_not_mutate_draft_actions() -> None:
    """合并后修改出站行动项不应影响草稿内 ``ActionItem``。"""
    draft = DraftCopyJSON(
        title="测试标题",
        summary="测试摘要内容足够长。",
        evidence=["测试证据。"],
        recommendation="测试建议。",
        whenToSeeVet="若加重请就医。",
        safetyNotice="测试免责声明。",
        primaryAction=ActionItem(label="联系兽医", route="contact_vet"),
        secondaryAction=ActionItem(label="记录症状", route="record_symptom"),
    )
    parsed = parse_input(
        {
            "caseId": "action_passthrough_test",
            "scene": "health_triage",
            "timestamp": "2026-06-08T10:00:00+08:00",
            "pet": {
                "petId": "pet-test",
                "name": "测试",
                "species": "dog",
                "ageMonths": 12,
                "weightKg": 5.0,
            },
            "device": {
                "deviceOnline": True,
                "lastSeenAt": "2026-06-08T09:59:00+08:00",
                "dataQuality": "good",
            },
            "vitals": {
                "temperatureC": 38.5,
                "heartRateBpm": 90,
                "activityLevel": "resting",
            },
            "healthEvidence": {
                "riskLevel": "normal",
                "riskLabel": "正常",
                "displayClaim": "平稳",
                "recommendationText": "观察",
                "confidence": "high",
                "signals": [],
            },
            "userReport": {
                "text": "正常",
                "symptoms": [],
                "appetite": "normal",
                "drinking": "normal",
                "energy": "normal",
                "vomiting": "none",
                "diarrhea": "none",
            },
            "context": {"ageRisk": "normal", "notes": []},
            "missingData": [],
        },
    )
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)

    output = merge_agent_output(triage=triage, draft=draft)
    output.primary_action.label = "已修改标签"

    assert draft.primary_action.label == "联系兽医"


def test_merge_risk_fields_from_triage_not_draft(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """``riskLevel`` / ``confidence`` / ``missingData`` 必须来自 ②。"""
    case = dataset.case_by_id("missing_vitals")  # type: ignore[attr-defined]
    mechanical = generate_mechanical_draft_from_input(
        case.input,
        bundle=knowledge_bundle,  # type: ignore[arg-type]
    )
    parsed = parse_input(case.input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    draft = mechanical.draft

    output = merge_agent_output(triage=triage, draft=draft)

    assert output.risk_level == triage.final_risk_level
    assert output.confidence == triage.confidence
    assert output.missing_data == list(triage.missing_data_user)
    assert output.scene == "health_triage"
    assert output.title == draft.title
    assert output.summary == draft.summary


def test_merge_all_cases_mechanical_passes_full_schema(
    dataset: object,
    knowledge_bundle: object,
) -> None:
    """20 case 机械文案 + 合并后均应通过 FULL output_schema 校验。"""
    for case in dataset.cases:  # type: ignore[attr-defined]
        mechanical = generate_mechanical_draft_from_input(
            case.input,
            bundle=knowledge_bundle,  # type: ignore[arg-type]
            options=MechanicalDraftOptions(append_missing_mentions=True),
        )
        parsed = parse_input(case.input)
        assert parsed.fact_sheet is not None
        triage = run_triage_core(parsed.fact_sheet)
        output = merge_agent_output(triage=triage, draft=mechanical.draft)
        result = validate_output(output, mode=OutputValidationMode.FULL)
        assert result.passed, f"case {case.case_id} FULL 校验失败: {result.violations}"


def test_merge_raises_when_required_safety_notice_missing() -> None:
    """``safetyNoticeRequired=true`` 且草稿 disclaimer 为空时应拒绝合并。"""
    draft = DraftCopyJSON(
        title="紧急",
        summary="需要立即就医的摘要说明。",
        evidence=["用户报告抽搐。"],
        recommendation="请立即联系兽医。",
        whenToSeeVet="立即就医。",
        safetyNotice="",
        primaryAction=ActionItem(label="立即联系兽医/就医", route="contact_vet"),
    )
    parsed = parse_input(
        {
            "caseId": "merge_safety_fail",
            "scene": "health_triage",
            "timestamp": "2026-06-08T12:00:00+08:00",
            "pet": {
                "petId": "pet-s",
                "name": "点",
                "species": "cat",
                "ageMonths": 18,
                "weightKg": 3.9,
            },
            "device": {
                "deviceOnline": True,
                "lastSeenAt": "2026-06-08T11:59:00+08:00",
                "dataQuality": "partial",
            },
            "vitals": {"heartRateBpm": 190, "respiratoryRateBpm": 55},
            "healthEvidence": {
                "riskLevel": "emergency",
                "riskLabel": "紧急",
                "displayClaim": "抽搐",
                "recommendationText": "立即联系兽医",
                "confidence": "high",
                "signals": [
                    {
                        "id": "user_report",
                        "label": "抽搐",
                        "category": "user_report",
                        "riskLevel": "emergency",
                        "value": "seizure",
                        "reason": "用户报告抽搐",
                        "confidence": "high",
                    }
                ],
            },
            "userReport": {
                "text": "刚刚抽搐",
                "symptoms": ["抽搐"],
                "seizure": True,
                "energy": "very_low",
            },
            "context": {"ageRisk": "normal", "notes": []},
            "missingData": ["temperature", "hrv"],
        },
    )
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    assert triage.safety_notice_required is True

    with pytest.raises(MergeOutputError, match="safetyNoticeRequired"):
        merge_agent_output(triage=triage, draft=draft)
