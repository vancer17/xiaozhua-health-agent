"""WP3 确定性分诊核（Triage Core）公开 API。"""

from __future__ import annotations

from xiaozhua_health_agent.triage.batch import (
    make_triage_output_provider,
    run_triage_risk_batch,
    triage_output_for_input,
)
from xiaozhua_health_agent.triage.policy_data import BUNDLE_VERSION
from xiaozhua_health_agent.triage.triage_core import run_triage_core
from xiaozhua_health_agent.triage.triage_types import TriageCoreResult

__all__ = [
    "BUNDLE_VERSION",
    "TriageCoreResult",
    "make_triage_output_provider",
    "run_triage_core",
    "run_triage_risk_batch",
    "triage_output_for_input",
]
