"""``POST /intelligent`` 占位 API 测试（方案 A）。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from xiaozhua_health_agent.api import HealthApiSettings, create_app

if TYPE_CHECKING:
    from fastapi import FastAPI


@pytest.fixture
def dataset() -> object:
    """加载 V1 mock case 数据集。

    :returns: ``HealthTriageDataset`` 实例。
    :rtype: object
    """
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    from xiaozhua_health_agent.eval import load_health_triage_dataset

    return load_health_triage_dataset(cases_path)


@pytest.fixture
def api_app() -> FastAPI:
    """构造启用 intelligent 且跳过 lifespan 的测试应用。

    :returns: FastAPI 应用实例。
    :rtype: FastAPI
    """
    settings = HealthApiSettings(
        preload_copy_bundle=False,
        intelligent_enabled=True,
        internal_prefix="/internal",
    )
    return create_app(settings=settings, skip_lifespan=True)


@pytest.fixture
def disabled_intelligent_app() -> FastAPI:
    """构造关闭 intelligent 的测试应用。

    :returns: FastAPI 应用实例。
    :rtype: FastAPI
    """
    settings = HealthApiSettings(
        preload_copy_bundle=False,
        intelligent_enabled=False,
        internal_prefix="/internal",
    )
    return create_app(settings=settings, skip_lifespan=True)


@pytest.fixture
def client(api_app: FastAPI) -> TestClient:
    """HTTP 测试客户端。

    :param api_app: 测试用 FastAPI 应用。
    :type api_app: FastAPI
    :returns: TestClient 实例。
    :rtype: TestClient
    """
    with TestClient(api_app) as test_client:
        yield test_client


def test_post_intelligent_returns_placeholder_envelope(
    client: TestClient,
    dataset: object,
) -> None:
    """合法入参应返回 200 占位信封，且不含分诊结果。"""
    case = dataset.case_by_id("normal_dog_daily_check")  # type: ignore[attr-defined]
    response = client.post(
        "/intelligent",
        headers={"X-Session-Id": "sess-placeholder-001"},
        json=case.input.model_dump(by_alias=True, mode="json"),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "placeholder"
    assert body["sessionId"] == "sess-placeholder-001"
    assert body["triage"] is None
    assert body["triageStatus"] == "not_run"
    assert body["caseId"] == case.case_id  # type: ignore[attr-defined]
    assert body["messages"]
    assert body["suggestedPrompts"]
    assert body["meta"]["placeholder"] is True


def test_post_intelligent_invalid_input_returns_400(client: TestClient) -> None:
    """缺必填字段应返回 400。"""
    response = client.post("/intelligent", json={"caseId": "invalid-only"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "input_validation_failed"
    assert body["stage"] == "parse"


def test_post_intelligent_disabled_returns_404(
    disabled_intelligent_app: FastAPI,
) -> None:
    """关闭开关时应返回 404。"""
    with TestClient(disabled_intelligent_app) as disabled_client:
        response = disabled_client.post("/intelligent", json={"caseId": "x"})
    assert response.status_code == 404
    assert response.json()["error"] == "intelligent_endpoint_disabled"


def test_post_intelligent_does_not_require_copy_bundle(
    dataset: object,
) -> None:
    """占位端点不应依赖 KB-TPL 预加载（service_ready 可为 False）。"""
    settings = HealthApiSettings(
        preload_copy_bundle=False,
        intelligent_enabled=True,
    )
    app = create_app(settings=settings, skip_lifespan=True)
    case = dataset.case_by_id("high_fever_resting")  # type: ignore[attr-defined]

    with TestClient(app) as bare_client:
        response = bare_client.post(
            "/intelligent",
            json=case.input.model_dump(by_alias=True, mode="json"),
        )

    assert response.status_code == 200
    assert response.json()["triage"] is None
