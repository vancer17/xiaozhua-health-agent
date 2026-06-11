"""KB-TPL / KB-SYN / KB-FORBID / KB-ACTION 制品完整性校验。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xiaozhua_health_agent.eval.action_matrix import load_validated_action_matrix
from xiaozhua_health_agent.eval.case_dataset import (
    EXPECTED_CASE_COUNT,
    load_health_triage_dataset,
)
from xiaozhua_health_agent.eval.forbidden_patterns import merge_forbidden_patterns
from xiaozhua_health_agent.eval.synonym_map import load_synonym_map
from xiaozhua_health_agent.paths import (
    default_forbidden_patterns_path,
    default_kb_action_path,
    default_action_matrix_path,
    default_kb_tpl_config_dir,
    default_synonym_map_path,
)
from xiaozhua_health_agent.triage.triage_types import PrimaryFlagLiteral

_EXPECTED_TEMPLATE_IDS: frozenset[str] = frozenset(
    {
        "normal.NORMAL_DAILY",
        "watch.POST_EXERCISE",
        "warning.FEVER_RESTING",
        "warning.RESP_RESTING",
        "warning.HR_RESTING_CHRONIC",
        "warning.CHRONIC_HEART_RESP",
        "warning.USER_DEVICE_CONFLICT",
        "warning.REPEATED_VOMITING",
        "warning.SENIOR_DECLINE",
        "warning.PUPPY_FEVER",
        "watch.HRV_STRESS",
        "watch.LIMPING_PAIN",
        "watch.SLOW_RECOVERY",
        "watch.MILD_DIARRHEA",
        "watch.POST_VACCINE",
        "watch.DATA_MISSING",
        "watch.DATA_STALE",
        "emergency.EMERGENCY_RESPIRATORY",
        "emergency.EMERGENCY_SEIZURE",
        "emergency.EMERGENCY_TRAUMA",
    }
)

_PRIMARY_FLAGS: frozenset[str] = frozenset(
    {
        "NORMAL_DAILY",
        "POST_EXERCISE",
        "FEVER_RESTING",
        "RESP_RESTING",
        "HR_RESTING_CHRONIC",
        "CHRONIC_HEART_RESP",
        "USER_DEVICE_CONFLICT",
        "REPEATED_VOMITING",
        "SENIOR_DECLINE",
        "PUPPY_FEVER",
        "HRV_STRESS",
        "LIMPING_PAIN",
        "SLOW_RECOVERY",
        "MILD_DIARRHEA",
        "POST_VACCINE",
        "DATA_MISSING",
        "DATA_STALE",
        "EMERGENCY_SEIZURE",
        "EMERGENCY_RESPIRATORY",
        "EMERGENCY_TRAUMA",
    }
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def kb_tpl_dir() -> Path:
    return default_kb_tpl_config_dir()


def test_kb_tpl_config_files_exist(kb_tpl_dir: Path) -> None:
    for name in (
        "templates.v1.json",
        "slots.v1.json",
        "tone-by-risk.v1.json",
        "safety-notices.v1.json",
        "fallback-by-risk.v1.json",
    ):
        assert (kb_tpl_dir / name).is_file(), f"缺少 {name}"


def test_templates_cover_20_grid(kb_tpl_dir: Path) -> None:
    payload = _load_json(kb_tpl_dir / "templates.v1.json")
    templates = payload["templates"]
    assert set(templates) == _EXPECTED_TEMPLATE_IDS

    for template_id, entry in templates.items():
        meta = entry["meta"]
        assert meta["templateId"] == template_id
        risk, flag = template_id.split(".", 1)
        assert meta["riskLevel"] == risk
        assert meta["primaryFlag"] == flag
        assert entry["copy"]["titlePattern"]
        assert len(entry["copy"]["summaryOutline"]) >= 2
        assert entry["guidance"]["llmInstructions"]
        for slot_id in entry["binding"]["slots"]:
            assert (
                slot_id in _load_json(kb_tpl_dir / "slots.v1.json")["slots"]
                or slot_id == "primaryVital"
            )


def test_fallback_covers_all_risk_levels(kb_tpl_dir: Path) -> None:
    fallbacks = _load_json(kb_tpl_dir / "fallback-by-risk.v1.json")["fallbacks"]
    for key in ("normal", "watch", "warning", "emergency", "DEFAULT"):
        assert key in fallbacks


def test_safety_notices_resolve_rules(kb_tpl_dir: Path) -> None:
    payload = _load_json(kb_tpl_dir / "safety-notices.v1.json")
    assert "SNIP-GENERAL" in payload["snippets"]
    assert len(payload["resolveRules"]) >= 3


def test_kb_syn_loads_and_covers_primary_flags() -> None:
    synonym_map = load_synonym_map(default_synonym_map_path())
    for flag in _PRIMARY_FLAGS:
        assert flag in synonym_map.by_primary_flag, f"kb-syn 缺少 primaryFlag: {flag}"


def test_kb_forbid_aligns_with_eval_defaults() -> None:
    payload = _load_json(default_forbidden_patterns_path())
    merged = merge_forbidden_patterns(
        schema_patterns=tuple(payload["schemaPatterns"]),
        extended_patterns=tuple(payload["extendedPatterns"]),
    )
    assert "确诊为" in merged
    assert "继续观察即可" in merged


def test_kb_action_has_all_hints() -> None:
    payload = _load_json(default_kb_action_path())
    actions = payload["actions"]
    for hint in ("emergency_now", "contact_vet", "check_device", "rest_observe"):
        assert hint in actions
        assert actions[hint]["label"]
        assert actions[hint]["route"]


def test_primary_flags_match_triage_types() -> None:
    """模板 primaryFlag 与 triage_types.PrimaryFlagLiteral 一致。"""
    type_flags = set(PrimaryFlagLiteral.__args__)  # type: ignore[attr-defined]
    assert _PRIMARY_FLAGS == type_flags


def test_action_matrix_fixture_integrity() -> None:
    """action 矩阵制品应可加载且条目数与 cases 一致。"""
    cases_path = (
        Path(__file__).resolve().parents[2] / "docs/cases/health_triage_cases.v1.json"
    )
    dataset = load_health_triage_dataset(cases_path)
    fixture = load_validated_action_matrix(
        path=default_action_matrix_path(), dataset=dataset
    )
    assert fixture.meta.expected_case_count == EXPECTED_CASE_COUNT
    assert len(fixture.entries) == EXPECTED_CASE_COUNT
    assert default_action_matrix_path().is_file()
