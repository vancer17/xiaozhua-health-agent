"""EvidenceBuilder（WP3）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from xiaozhua_health_agent.parse import FactSheet, get_fact_value
from xiaozhua_health_agent.triage.policy_data import EVIDENCE_PATHS_BY_FLAG
from xiaozhua_health_agent.triage.triage_types import PrimaryFlagLiteral

_FIELD_LABELS: dict[str, str] = {
    "healthEvidence.riskLevel": "上游风险等级",
    "vitals.temperatureC": "当前体温",
    "vitals.heartRateBpm": "当前心率",
    "vitals.respiratoryRateBpm": "当前呼吸率",
    "vitals.hrvMs": "当前 HRV",
    "vitals.activityLevel": "活动状态",
    "vitals.stepsToday": "今日步数",
    "vitals.sleepQuality": "睡眠质量",
    "userReport.text": "用户描述",
    "userReport.energy": "精力状态",
    "userReport.appetite": "食欲状态",
    "userReport.vomiting": "呕吐情况",
    "userReport.diarrhea": "腹泻情况",
    "userReport.breathingDifficulty": "呼吸困难",
    "userReport.limping": "跛行",
    "userReport.pain": "疼痛",
    "userReport.seizure": "抽搐",
    "userReport.trauma": "外伤",
    "userReport.symptoms": "报告症状",
    "profile.chronicConditions": "慢性病史",
    "profile.medications": "当前用药",
    "identity.ageMonths": "宠物月龄",
    "context.recentExercise": "近期运动",
    "context.recentVaccination": "近期疫苗",
    "context.notes": "情境备注",
    "device.dataQuality": "数据质量",
    "device.warningText": "设备提示",
    "device.lastSeenAt": "最近上报时间",
    "missingData": "缺失数据项",
}


def build_evidence_bullets(
    primary_flag: PrimaryFlagLiteral,
    fact_sheet: FactSheet,
    *,
    missing_data_user: tuple[str, ...],
    max_bullets: int = 5,
) -> tuple[str, ...]:
    """从 FactSheet 路径组装可核对证据句。

    :param primary_flag: 叙事主键。
    :type primary_flag: PrimaryFlagLiteral
    :param fact_sheet: 客观事实。
    :type fact_sheet: FactSheet
    :param missing_data_user: 已翻译的缺失说明。
    :type missing_data_user: tuple[str, ...]
    :param max_bullets: 最大条数。
    :type max_bullets: int
    :returns: 证据 bullet 列表。
    :rtype: tuple[str, ...]
    """
    paths = EVIDENCE_PATHS_BY_FLAG.get(primary_flag, ())
    bullets: list[str] = []

    for path in paths:
        value = get_fact_value(fact_sheet, f"fact.{path}")
        sentence = _format_evidence_sentence(path, value)
        if sentence and sentence not in bullets:
            bullets.append(sentence)
        if len(bullets) >= max_bullets:
            break

    for missing_text in missing_data_user:
        sentence = f"数据说明：{missing_text}"
        if sentence not in bullets:
            bullets.append(sentence)
        if len(bullets) >= max_bullets:
            break

    return tuple(bullets[:max_bullets])


def _format_evidence_sentence(path: str, value: Any) -> str | None:
    """将字段值格式化为简短事实句。"""
    if value is None:
        return None
    label = _FIELD_LABELS.get(path, path)

    if isinstance(value, bool):
        if not value and path not in {
            "userReport.breathingDifficulty",
            "userReport.limping",
            "userReport.pain",
            "userReport.seizure",
            "userReport.trauma",
        }:
            return None
        return f"{label}：{'是' if value else '否'}"

    if isinstance(value, datetime):
        return f"{label}：{value.isoformat()}"

    if isinstance(value, list):
        if not value:
            return None
        joined = "、".join(str(item) for item in value)
        return f"{label}：{joined}"

    if isinstance(value, (int, float)) and path == "vitals.temperatureC":
        return f"{label}：{value}°C"
    if isinstance(value, (int, float)) and "Bpm" in path:
        return f"{label}：{value} 次/分"
    if isinstance(value, (int, float)) and path == "vitals.hrvMs":
        return f"{label}：{value} ms"

    return f"{label}：{value}"
