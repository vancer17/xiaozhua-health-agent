"""Triage Core 批跑集成（WP3 + WP0）。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from xiaozhua_health_agent.eval import (
    RiskEvalOptions,
    RiskEvalReport,
    load_health_triage_dataset,
    run_risk_only_evaluation_with_provider,
)
from xiaozhua_health_agent.eval.case_dataset import HealthTriageDataset
from xiaozhua_health_agent.eval.risk_evaluator import (
    ActualOutputPayload,
    TriageOutputProvider,
)
from xiaozhua_health_agent.parse import parse_input
from xiaozhua_health_agent.schemas import AgentInput
from xiaozhua_health_agent.triage.policy_data import BUNDLE_VERSION
from xiaozhua_health_agent.triage.triage_core import run_triage_core


def triage_output_for_input(
    agent_input: AgentInput | Mapping[str, Any],
) -> ActualOutputPayload:
    """对单条 input 执行 parse → triage，返回 risk-only output dict。

    :param agent_input: App / case 输入 JSON。
    :type agent_input: AgentInput | Mapping[str, Any]
    :returns: minimal output；解析失败时 ``None``。
    :rtype: ActualOutputPayload
    """
    parsed = parse_input(agent_input)
    if not parsed.passed or parsed.fact_sheet is None:
        return None
    result = run_triage_core(parsed.fact_sheet)
    return result.to_risk_only_output()


def make_triage_output_provider() -> TriageOutputProvider:
    """构造供 ``run_risk_only_evaluation_with_provider`` 使用的回调。"""
    return triage_output_for_input


def run_triage_risk_batch(
    dataset: HealthTriageDataset | None = None,
    *,
    options: RiskEvalOptions | None = None,
) -> RiskEvalReport:
    """对 20 case 执行 Triage Core risk-only 批跑评测。

    :param dataset: case 数据集；省略时加载默认路径。
    :type dataset: HealthTriageDataset | None
    :param options: 评测配置。
    :type options: RiskEvalOptions | None
    :returns: risk-only 评测报告。
    :rtype: RiskEvalReport
    """
    resolved_dataset = dataset if dataset is not None else load_health_triage_dataset()
    resolved_options = (
        options
        if options is not None
        else RiskEvalOptions(
            bundle_version=BUNDLE_VERSION,
        )
    )
    if resolved_options.bundle_version is None:
        resolved_options = resolved_options.model_copy(
            update={"bundle_version": BUNDLE_VERSION},
        )
    return run_risk_only_evaluation_with_provider(
        resolved_dataset,
        make_triage_output_provider(),
        options=resolved_options,
    )
