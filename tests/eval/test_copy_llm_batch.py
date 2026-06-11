"""copy-llm 批跑模式测试（mock 通义千问）。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import SecretStr

from xiaozhua_health_agent.copy import (
    AsyncQwenClient,
    QwenClientSettings,
    resolve_copy_template,
)
from xiaozhua_health_agent.eval import (
    COPY_LLM_SMOKE_CASE_IDS,
    CopyLlmBatchConfig,
    CopyLlmBatchMode,
    load_health_triage_dataset,
    run_copy_llm_batch_async,
)
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.triage import run_triage_core


@pytest.fixture
def dataset() -> object:
    """V1 mock case 数据集。"""
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    return load_health_triage_dataset(cases_path)


@pytest.fixture
def qwen_settings() -> QwenClientSettings:
    """测试用通义配置。"""
    return QwenClientSettings(
        api_key=SecretStr("test-key"),
        base_url="https://example.com/v1",
        model="qwen-plus",
        timeout_sec=5.0,
        max_retries=0,
    )


def _draft_json_for_case(case_input: dict[str, Any]) -> str:
    """根据 case input 构造最小合法 DraftCopyJSON（测试用）。"""
    parsed = parse_input(case_input)
    assert parsed.fact_sheet is not None
    triage = run_triage_core(parsed.fact_sheet)
    resolved = resolve_copy_template(parsed.fact_sheet, triage)
    payload = {
        "title": "测试标题",
        "summary": "测试摘要：结合当前监测与情境，建议按模板观察。",
        "evidence": list(resolved.evidence_bullets) or ["基于当前可获得信息整理。"],
        "recommendation": "请按建议观察并采取下一步。",
        "whenToSeeVet": "若症状加重，请联系兽医。",
        "safetyNotice": resolved.safety_notice_snippet or "以上建议仅供参考。",
        "primaryAction": resolved.primary_action_draft.model_dump(by_alias=True),
        "secondaryAction": None,
    }
    return json.dumps(payload, ensure_ascii=False)


_TEMPLATE_ID_TO_CASE_ID: dict[str, str] = {
    "watch.POST_EXERCISE": "mild_fever_after_exercise",
    "warning.RESP_RESTING": "respiratory_rate_high_resting",
    "watch.DATA_MISSING": "missing_vitals",
    "warning.USER_DEVICE_CONFLICT": "conflict_user_normal_sensor_fever",
    "emergency.EMERGENCY_RESPIRATORY": "emergency_breathing_difficulty",
}


def _find_case_input_by_template_id(
    user_content: str, dataset: object
) -> dict[str, Any]:
    """从 prompt JSON 中的 templateId 映射 case input。"""
    for template_id, case_id in _TEMPLATE_ID_TO_CASE_ID.items():
        if template_id in user_content:
            return dataset.case_by_id(case_id).input  # type: ignore[attr-defined]
    return dataset.case_by_id("mild_fever_after_exercise").input  # type: ignore[attr-defined]


async def _mock_create_completion(**kwargs: Any) -> SimpleNamespace:
    """OpenAI create 替身：按 user 消息中的 templateId 返回 DraftCopyJSON。"""
    messages = kwargs["messages"]
    user_content = messages[-1]["content"]
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    ds = load_health_triage_dataset(cases_path)
    case_input = _find_case_input_by_template_id(user_content, ds)
    return SimpleNamespace(
        id="chat-test",
        model="qwen-plus",
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=_draft_json_for_case(case_input),
                ),
                finish_reason="stop",
            ),
        ],
        usage=SimpleNamespace(
            prompt_tokens=1,
            completion_tokens=1,
            total_tokens=2,
        ),
    )


@pytest.fixture
def mock_qwen_client(qwen_settings: QwenClientSettings) -> AsyncQwenClient:
    """返回固定 DraftCopyJSON 的 mock 通义客户端。"""
    openai_client = MagicMock()
    openai_client.chat = MagicMock()
    openai_client.chat.completions = MagicMock()
    openai_client.chat.completions.create = AsyncMock(
        side_effect=_mock_create_completion
    )
    openai_client.close = AsyncMock()
    return AsyncQwenClient(qwen_settings, openai_client=openai_client)


@pytest.mark.asyncio
async def test_copy_llm_smoke_batch_with_mock_qwen(
    dataset: object,
    mock_qwen_client: AsyncQwenClient,
) -> None:
    """冒烟 5 case 在 mock 通义下应全部解析通过。"""
    config = CopyLlmBatchConfig(mode=CopyLlmBatchMode.SMOKE.value)
    report = await run_copy_llm_batch_async(
        config,
        dataset=dataset,  # type: ignore[arg-type]
        qwen_client=mock_qwen_client,
    )
    assert report.total == len(COPY_LLM_SMOKE_CASE_IDS)
    assert report.passed == report.total
    assert report.failed == 0
    assert not report.skipped_llm


@pytest.mark.asyncio
async def test_copy_llm_mechanical_full_batch(dataset: object) -> None:
    """use_mechanical 全量 20 case 应无 API Key 产出 DraftCopyJSON。"""
    config = CopyLlmBatchConfig(
        mode=CopyLlmBatchMode.FULL.value,
        use_mechanical=True,
    )
    report = await run_copy_llm_batch_async(
        config,
        dataset=dataset,  # type: ignore[arg-type]
    )
    assert report.used_mechanical is True
    assert report.passed == report.total
    assert report.failed == 0
    for record in report.records:
        assert record.result.generator == "mechanical"
        assert record.result.draft is not None


@pytest.mark.asyncio
async def test_copy_llm_skip_llm_marks_failed(dataset: object) -> None:
    """skip_llm 时不应计为通过（硬门槛要求真实调用）。"""
    config = CopyLlmBatchConfig(
        mode=CopyLlmBatchMode.SMOKE.value,
        skip_llm=True,
    )
    report = await run_copy_llm_batch_async(
        config,
        dataset=dataset,  # type: ignore[arg-type]
    )
    assert report.skipped_llm is True
    assert report.passed == 0
    assert report.failed == report.total
