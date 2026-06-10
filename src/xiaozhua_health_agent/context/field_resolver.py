"""FactSheet 点分路径字段解析（WP2）。

将决策表 ``when`` 中的 camelCase 路径（如 ``userReport.seizure``）
解析为 ``FactSheet`` 上的 Python 属性值，供 ``eval_when`` 的 ``field`` 原子使用。
"""

from __future__ import annotations

from typing import Any

from xiaozhua_health_agent.parse import FactSheet, get_fact_value

# when JSON 路径 → FactSheet 相对 fact_index 路径（camelCase）
_FIELD_PATH_ALIASES: dict[str, str] = {
    "caseId": "identity.caseId",
    "petId": "identity.petId",
    "pet.name": "identity.name",
    "pet.species": "identity.species",
    "pet.ageMonths": "identity.ageMonths",
    "pet.breed": "identity.breed",
    "pet.chronicConditions": "profile.chronicConditions",
    "pet.medications": "profile.medications",
    "pet.sex": "profile.sex",
    "pet.weightKg": "profile.weightKg",
    "pet.neutered": "profile.neutered",
    "device.deviceOnline": "device.deviceOnline",
    "device.dataQuality": "device.dataQuality",
    "device.lastSeenAt": "device.lastSeenAt",
    "device.warningText": "device.warningText",
    "vitals.temperatureC": "vitals.temperatureC",
    "vitals.heartRateBpm": "vitals.heartRateBpm",
    "vitals.respiratoryRateBpm": "vitals.respiratoryRateBpm",
    "vitals.hrvMs": "vitals.hrvMs",
    "vitals.activityLevel": "vitals.activityLevel",
    "vitals.sleepQuality": "vitals.sleepQuality",
    "healthEvidence.riskLevel": "healthEvidence.riskLevel",
    "userReport.text": "userReport.text",
    "userReport.symptoms": "userReport.symptoms",
    "userReport.appetite": "userReport.appetite",
    "userReport.drinking": "userReport.drinking",
    "userReport.energy": "userReport.energy",
    "userReport.vomiting": "userReport.vomiting",
    "userReport.diarrhea": "userReport.diarrhea",
    "userReport.coughing": "userReport.coughing",
    "userReport.breathingDifficulty": "userReport.breathingDifficulty",
    "userReport.pain": "userReport.pain",
    "userReport.limping": "userReport.limping",
    "userReport.seizure": "userReport.seizure",
    "userReport.trauma": "userReport.trauma",
    "context.recentExercise": "context.recentExercise",
    "context.recentVaccination": "context.recentVaccination",
    "context.ageRisk": "context.ageRisk",
    "context.notes": "context.notes",
    "missingData": "missingData",
}


def resolve_field_path(path: str) -> str:
    """将 when 中的逻辑路径规范化为 fact_index 相对路径。

    :param path: 原始点分路径（camelCase）。
    :type path: str
    :returns: 规范化后的路径键（不含 ``fact.`` 前缀）。
    :rtype: str
    """
    return _FIELD_PATH_ALIASES.get(path, path)


def resolve_field_value(fact_sheet: FactSheet, path: str) -> Any:
    """按点分路径从 ``FactSheet`` 读取字段值。

    优先通过强类型属性访问常见路径；未映射路径回退 ``get_fact_value``。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :param path: when JSON 中的点分路径。
    :type path: str
    :returns: 字段原始值；路径不存在时 ``None``。
    :rtype: Any
    """
    direct = _resolve_via_attributes(fact_sheet, path)
    if direct is not _SENTINEL_MISSING:
        return direct
    return get_fact_value(fact_sheet, resolve_field_path(path))


_SENTINEL_MISSING: object = object()


def _resolve_via_attributes(fact_sheet: FactSheet, path: str) -> Any:
    """通过 ``FactSheet`` 嵌套属性解析已知路径。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :param path: when JSON 点分路径。
    :type path: str
    :returns: 解析到的值；未知路径返回内部哨兵。
    :rtype: Any
    """
    identity = fact_sheet.identity
    profile = fact_sheet.profile
    device = fact_sheet.device
    vitals = fact_sheet.vitals
    upstream = fact_sheet.upstream
    user_report = fact_sheet.user_report
    context = fact_sheet.context

    attribute_map: dict[str, Any] = {
        "caseId": identity.case_id,
        "petId": identity.pet_id,
        "pet.name": identity.pet_name,
        "pet.species": identity.species,
        "pet.ageMonths": identity.age_months,
        "pet.breed": identity.breed,
        "pet.chronicConditions": profile.chronic_conditions,
        "pet.medications": profile.medications,
        "pet.sex": profile.sex,
        "pet.weightKg": profile.weight_kg,
        "pet.neutered": profile.neutered,
        "device.deviceOnline": device.device_online,
        "device.dataQuality": device.data_quality,
        "device.lastSeenAt": device.last_seen_at,
        "device.warningText": device.warning_text,
        "vitals.temperatureC": vitals.temperature_c,
        "vitals.heartRateBpm": vitals.heart_rate_bpm,
        "vitals.respiratoryRateBpm": vitals.respiratory_rate_bpm,
        "vitals.hrvMs": vitals.hrv_ms,
        "vitals.activityLevel": vitals.activity_level,
        "vitals.sleepQuality": vitals.sleep_quality,
        "healthEvidence.riskLevel": upstream.risk_level,
        "userReport.text": user_report.text,
        "userReport.symptoms": user_report.symptoms,
        "userReport.appetite": user_report.appetite,
        "userReport.drinking": user_report.drinking,
        "userReport.energy": user_report.energy,
        "userReport.vomiting": user_report.vomiting,
        "userReport.diarrhea": user_report.diarrhea,
        "userReport.coughing": user_report.coughing,
        "userReport.breathingDifficulty": user_report.breathing_difficulty,
        "userReport.pain": user_report.pain,
        "userReport.limping": user_report.limping,
        "userReport.seizure": user_report.seizure,
        "userReport.trauma": user_report.trauma,
        "context.recentExercise": context.recent_exercise,
        "context.recentVaccination": context.recent_vaccination,
        "context.ageRisk": context.age_risk,
        "context.notes": context.notes,
        "missingData": fact_sheet.missing_data,
    }

    if path in attribute_map:
        return attribute_map[path]
    return _SENTINEL_MISSING
