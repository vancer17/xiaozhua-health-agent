"""intelligent 占位服务单元测试（方案 A）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from xiaozhua_health_agent.eval import load_health_triage_dataset
from xiaozhua_health_agent.intelligent import (
    IntelligentPlaceholderBuildContext,
    IntelligentPlaceholderRequestContext,
    build_intelligent_placeholder_response,
    build_intelligent_placeholder_response_async,
    resolve_session_id,
    validate_intelligent_request,
    validate_intelligent_request_async,
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


def test_resolve_session_id_generates_uuid_when_missing() -> None:
    """缺失会话头时应生成非空 UUID。"""
    session_id = resolve_session_id(None)
    assert session_id
    assert len(session_id) >= 32


def test_resolve_session_id_trims_header_value() -> None:
    """应去除会话头首尾空白。"""
    assert resolve_session_id("  sess-abc  ") == "sess-abc"


def test_validate_intelligent_request_accepts_case_input(
    dataset: object,
) -> None:
    """合法 case input 应通过契约校验。"""
    case = dataset.case_by_id("normal_dog_daily_check")  # type: ignore[attr-defined]
    result = validate_intelligent_request(
        case.input.model_dump(by_alias=True, mode="json")
    )
    assert result.passed is True
    assert result.parsed is not None


@pytest.mark.asyncio
async def test_build_placeholder_response_async(dataset: object) -> None:
    """异步构建应产出占位信封且 triage 为 null。"""
    case = dataset.case_by_id("emergency_seizure")  # type: ignore[attr-defined]
    validation = await validate_intelligent_request_async(
        case.input.model_dump(by_alias=True, mode="json"),
    )
    assert validation.passed and validation.parsed is not None

    context = IntelligentPlaceholderBuildContext(
        parsed_input=validation.parsed,
        request_context=IntelligentPlaceholderRequestContext(
            session_id_header="test-session",
            user_message="它刚刚抽搐了",
        ),
    )
    response = await build_intelligent_placeholder_response_async(context)

    assert response.mode == "placeholder"
    assert response.session_id == "test-session"
    assert response.triage is None
    assert response.triage_status == "not_run"
    assert response.case_id == case.case_id  # type: ignore[attr-defined]
    assert response.pet_id == validation.parsed.pet.pet_id
    assert len(response.messages) >= 3
    assert response.meta.placeholder is True
    assert any("占位回显" in message.content for message in response.messages)


def test_build_placeholder_sync_matches_pet_name(dataset: object) -> None:
    """同步构建应在欢迎语中包含宠物名。"""
    case = dataset.case_by_id("normal_dog_daily_check")  # type: ignore[attr-defined]
    validation = validate_intelligent_request(
        case.input.model_dump(by_alias=True, mode="json"),
    )
    assert validation.passed and validation.parsed is not None

    response = build_intelligent_placeholder_response(
        IntelligentPlaceholderBuildContext(
            parsed_input=validation.parsed,
            request_context=IntelligentPlaceholderRequestContext(),
        ),
    )
    assert validation.parsed.pet.name in response.messages[1].content
