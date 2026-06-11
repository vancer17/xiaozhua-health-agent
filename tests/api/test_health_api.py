"""WP6 阶段 2 — FastAPI 机械分诊 HTTP API 测试。"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from xiaozhua_health_agent.api import HealthApiSettings, create_app
from xiaozhua_health_agent.copy import load_copy_knowledge_bundle
from xiaozhua_health_agent.eval import (
    OutputValidationMode,
    load_health_triage_dataset,
    validate_output,
)

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
    return load_health_triage_dataset(cases_path)


@pytest.fixture
def knowledge_bundle() -> object:
    """加载 copy 知识资产聚合包。

    :returns: ``CopyKnowledgeBundle`` 实例。
    :rtype: object
    """
    return load_copy_knowledge_bundle()


@pytest.fixture
def api_app(knowledge_bundle: object) -> FastAPI:
    """构造注入知识包、跳过 lifespan 的测试用 FastAPI 应用。

    :param knowledge_bundle: 预加载 KB-TPL 包。
    :type knowledge_bundle: object
    :returns: FastAPI 应用实例。
    :rtype: FastAPI
    """
    settings = HealthApiSettings(
        preload_copy_bundle=False,
        internal_prefix="/internal",
    )
    return create_app(
        settings=settings,
        copy_bundle=knowledge_bundle,  # type: ignore[arg-type]
        skip_lifespan=True,
    )


@pytest.fixture
def client(api_app: FastAPI) -> TestClient:
    """构造同步 HTTP 测试客户端。

    :param api_app: 测试用 FastAPI 应用。
    :type api_app: FastAPI
    :returns: Starlette TestClient 上下文管理器内实例。
    :rtype: TestClient
    """
    with TestClient(api_app) as test_client:
        yield test_client


def test_healthz_returns_ok(client: TestClient) -> None:
    """``GET /internal/healthz`` 应返回存活状态。"""
    response = client.get("/internal/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readyz_returns_ready_when_bundle_injected(client: TestClient) -> None:
    """``GET /internal/readyz`` 在预注入知识包时应为就绪。"""
    response = client.get("/internal/readyz")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["copyBundleReady"] is True


def test_post_health_emergency_case_returns_output_schema(
    client: TestClient,
    dataset: object,
) -> None:
    """``POST /health`` 对合法 case 应返回 200 与完整 output 字段。"""
    case = dataset.case_by_id("emergency_seizure")  # type: ignore[attr-defined]
    response = client.post(
        "/health", json=case.input.model_dump(by_alias=True, mode="json")
    )

    assert response.status_code == 200
    body = response.json()
    assert body["riskLevel"] == "emergency"
    assert body["scene"] == "health_triage"
    assert body["title"]
    assert body["safetyNotice"]

    schema_check = validate_output(body, mode=OutputValidationMode.FULL)
    assert schema_check.passed is True


def test_post_health_all_cases_return_200(
    client: TestClient,
    dataset: object,
) -> None:
    """20 case 均应通过 HTTP 机械管道返回 200。"""
    for case in dataset.cases:  # type: ignore[attr-defined]
        response = client.post(
            "/health",
            json=case.input.model_dump(by_alias=True, mode="json"),
        )
        assert response.status_code == 200, (
            f"case {case.case_id} failed: {response.text}"
        )
        assert response.json()["riskLevel"] == case.expected.risk_level


def test_post_health_invalid_input_returns_400(client: TestClient) -> None:
    """缺必填字段的入参应返回 400 与结构化错误体。"""
    response = client.post("/health", json={"caseId": "invalid-only"})

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "input_validation_failed"
    assert body["stage"] == "parse"
    assert len(body["violations"]) > 0


def test_post_health_risk_matches_triage_core(
    client: TestClient,
    dataset: object,
) -> None:
    """HTTP 响应 riskLevel 应与 case expected 一致（② 锁定）。"""
    case = dataset.case_by_id("high_fever_resting")  # type: ignore[attr-defined]
    response = client.post(
        "/health", json=case.input.model_dump(by_alias=True, mode="json")
    )

    assert response.status_code == 200
    assert response.json()["riskLevel"] == "warning"
    assert response.json()["confidence"] == "high"
