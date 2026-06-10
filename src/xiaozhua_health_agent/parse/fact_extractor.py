"""L3-01 事实清单提取器子集（WP1）。

从归一化后的 ``AgentInput`` 构建 ``FactSheet`` 与 ``fact_index``，不做医学判断。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from xiaozhua_health_agent.schemas import AgentInput, HealthSignal

from xiaozhua_health_agent.parse.normalizer import timestamp_to_epoch_ms
from xiaozhua_health_agent.parse.parse_types import (
    DEFAULT_NORMALIZATION_PROFILE,
    FACT_INDEX_PREFIX,
    ContextFacts,
    DeviceFacts,
    FactSheet,
    IdentityFacts,
    NormalizationProfile,
    ProfileFacts,
    UpstreamFacts,
    UserReportFacts,
    VitalsFacts,
)

# ---------------------------------------------------------------------------
# fact_index 构建
# ---------------------------------------------------------------------------


def _index_key(*parts: str) -> str:
    """拼接稳定事实路径键。

    :param parts: 路径片段（不含前缀）。
    :type parts: str
    :returns: 形如 ``fact.vitals.temperatureC`` 的键。
    :rtype: str
    """
    return f"{FACT_INDEX_PREFIX}." + ".".join(parts)


def _set_index_value(
    index: dict[str, Any],
    key: str,
    value: Any,
) -> None:
    """向索引写入单条事实（显式保留 ``None``）。

    :param index: 可变事实索引字典。
    :type index: dict[str, Any]
    :param key: 稳定路径键。
    :type key: str
    :param value: 原始值（可为 ``None``）。
    :type value: Any
    :rtype: None
    """
    index[key] = value


def _index_identity(
    index: dict[str, Any],
    *,
    case_id: str,
    pet_id: str,
    pet_name: str,
    species: str,
    age_months: float | None,
    breed: str | None,
) -> None:
    """写入标识类事实索引。

    :param index: 可变事实索引字典。
    :type index: dict[str, Any]
    :param case_id: 请求 case 标识。
    :type case_id: str
    :param pet_id: 宠物标识。
    :type pet_id: str
    :param pet_name: 宠物名称。
    :type pet_name: str
    :param species: 物种枚举值。
    :type species: str
    :param age_months: 月龄或 ``None``。
    :type age_months: float | None
    :param breed: 品种或 ``None``。
    :type breed: str | None
    :rtype: None
    """
    _set_index_value(index, _index_key("caseId"), case_id)
    _set_index_value(index, _index_key("pet", "petId"), pet_id)
    _set_index_value(index, _index_key("pet", "name"), pet_name)
    _set_index_value(index, _index_key("pet", "species"), species)
    _set_index_value(index, _index_key("pet", "ageMonths"), age_months)
    _set_index_value(index, _index_key("pet", "breed"), breed)


def _index_profile(
    index: dict[str, Any],
    *,
    sex: str | None,
    weight_kg: float | None,
    neutered: bool | None,
    chronic_conditions: list[str],
    medications: list[str],
    allergies: list[str],
) -> None:
    """写入档案类事实索引。

    :param index: 可变事实索引字典。
    :type index: dict[str, Any]
    :param sex: 性别或 ``None``。
    :type sex: str | None
    :param weight_kg: 体重或 ``None``。
    :type weight_kg: float | None
    :param neutered: 是否绝育或 ``None``。
    :type neutered: bool | None
    :param chronic_conditions: 慢病史列表。
    :type chronic_conditions: list[str]
    :param medications: 用药列表。
    :type medications: list[str]
    :param allergies: 过敏史列表。
    :type allergies: list[str]
    :rtype: None
    """
    _set_index_value(index, _index_key("pet", "sex"), sex)
    _set_index_value(index, _index_key("pet", "weightKg"), weight_kg)
    _set_index_value(index, _index_key("pet", "neutered"), neutered)
    _set_index_value(
        index, _index_key("pet", "chronicConditions"), list(chronic_conditions)
    )
    _set_index_value(index, _index_key("pet", "medications"), list(medications))
    _set_index_value(index, _index_key("pet", "allergies"), list(allergies))


def _index_device(
    index: dict[str, Any],
    *,
    device_online: bool,
    battery_level: float | None,
    data_quality: str,
    last_seen_at: datetime | None,
    collar_id: str | None,
    warning_text: str | None,
) -> None:
    """写入设备类事实索引。

    :param index: 可变事实索引字典。
    :type index: dict[str, Any]
    :param device_online: 设备是否在线。
    :type device_online: bool
    :param battery_level: 电量或 ``None``。
    :type battery_level: float | None
    :param data_quality: 数据质量枚举值。
    :type data_quality: str
    :param last_seen_at: 最近上报时间或 ``None``。
    :type last_seen_at: datetime | None
    :param collar_id: 项圈 ID 或 ``None``。
    :type collar_id: str | None
    :param warning_text: 告警文案或 ``None``。
    :type warning_text: str | None
    :rtype: None
    """
    _set_index_value(index, _index_key("device", "deviceOnline"), device_online)
    _set_index_value(index, _index_key("device", "batteryLevel"), battery_level)
    _set_index_value(index, _index_key("device", "dataQuality"), data_quality)
    _set_index_value(index, _index_key("device", "lastSeenAt"), last_seen_at)
    _set_index_value(index, _index_key("device", "collarId"), collar_id)
    _set_index_value(index, _index_key("device", "warningText"), warning_text)


def _index_vitals(
    index: dict[str, Any],
    *,
    temperature_c: float | None,
    heart_rate_bpm: float | None,
    respiratory_rate_bpm: float | None,
    hrv_ms: float | None,
    steps_today: float | None,
    activity_level: str,
    sleep_quality: str,
    updated_at: datetime | None,
) -> None:
    """写入体征类事实索引。

    :param index: 可变事实索引字典。
    :type index: dict[str, Any]
    :param temperature_c: 体温或 ``None``。
    :type temperature_c: float | None
    :param heart_rate_bpm: 心率或 ``None``。
    :type heart_rate_bpm: float | None
    :param respiratory_rate_bpm: 呼吸率或 ``None``。
    :type respiratory_rate_bpm: float | None
    :param hrv_ms: HRV 或 ``None``。
    :type hrv_ms: float | None
    :param steps_today: 步数或 ``None``。
    :type steps_today: float | None
    :param activity_level: 活动强度枚举值。
    :type activity_level: str
    :param sleep_quality: 睡眠质量枚举值。
    :type sleep_quality: str
    :param updated_at: 体征更新时间或 ``None``。
    :type updated_at: datetime | None
    :rtype: None
    """
    _set_index_value(index, _index_key("vitals", "temperatureC"), temperature_c)
    _set_index_value(index, _index_key("vitals", "heartRateBpm"), heart_rate_bpm)
    _set_index_value(
        index, _index_key("vitals", "respiratoryRateBpm"), respiratory_rate_bpm
    )
    _set_index_value(index, _index_key("vitals", "hrvMs"), hrv_ms)
    _set_index_value(index, _index_key("vitals", "stepsToday"), steps_today)
    _set_index_value(index, _index_key("vitals", "activityLevel"), activity_level)
    _set_index_value(index, _index_key("vitals", "sleepQuality"), sleep_quality)
    _set_index_value(index, _index_key("vitals", "updatedAt"), updated_at)


def _index_upstream(
    index: dict[str, Any],
    *,
    risk_level: str,
    risk_label: str,
    display_claim: str,
    recommendation_text: str,
    confidence: str,
    signals: list[HealthSignal],
) -> None:
    """写入上游 healthEvidence 事实索引。

    :param index: 可变事实索引字典。
    :type index: dict[str, Any]
    :param risk_level: 上游综合风险等级。
    :type risk_level: str
    :param risk_label: 上游风险标签。
    :type risk_label: str
    :param display_claim: 上游展示结论。
    :type display_claim: str
    :param recommendation_text: 上游建议文案。
    :type recommendation_text: str
    :param confidence: 上游置信度。
    :type confidence: str
    :param signals: 上游信号列表。
    :type signals: list[HealthSignal]
    :rtype: None
    """
    _set_index_value(index, _index_key("healthEvidence", "riskLevel"), risk_level)
    _set_index_value(index, _index_key("healthEvidence", "riskLabel"), risk_label)
    _set_index_value(index, _index_key("healthEvidence", "displayClaim"), display_claim)
    _set_index_value(
        index,
        _index_key("healthEvidence", "recommendationText"),
        recommendation_text,
    )
    _set_index_value(index, _index_key("healthEvidence", "confidence"), confidence)
    for idx, signal in enumerate(signals):
        prefix = f"healthEvidence.signals.{idx}"
        _set_index_value(index, _index_key(prefix, "id"), signal.id)
        _set_index_value(index, _index_key(prefix, "riskLevel"), signal.risk_level)
        _set_index_value(index, _index_key(prefix, "value"), signal.value)
        _set_index_value(index, _index_key(prefix, "baseline"), signal.baseline)
        _set_index_value(index, _index_key(prefix, "reason"), signal.reason)


def _index_user_report(
    index: dict[str, Any],
    *,
    text: str,
    duration: str | None,
    symptoms: list[str],
    appetite: str,
    drinking: str,
    energy: str,
    vomiting: str,
    diarrhea: str,
    coughing: bool | None,
    breathing_difficulty: bool | None,
    pain: bool | None,
    limping: bool | None,
    seizure: bool | None,
    trauma: bool | None,
) -> None:
    """写入用户自述事实索引。

    :param index: 可变事实索引字典。
    :type index: dict[str, Any]
    :param text: 用户自由文本。
    :type text: str
    :param duration: 持续时间或 ``None``。
    :type duration: str | None
    :param symptoms: 症状关键词列表。
    :type symptoms: list[str]
    :param appetite: 食欲枚举值。
    :type appetite: str
    :param drinking: 饮水枚举值。
    :type drinking: str
    :param energy: 精力枚举值。
    :type energy: str
    :param vomiting: 呕吐枚举值。
    :type vomiting: str
    :param diarrhea: 腹泻枚举值。
    :type diarrhea: str
    :param coughing: 是否咳嗽或 ``None``。
    :type coughing: bool | None
    :param breathing_difficulty: 是否呼吸困难或 ``None``。
    :type breathing_difficulty: bool | None
    :param pain: 是否疼痛或 ``None``。
    :type pain: bool | None
    :param limping: 是否跛行或 ``None``。
    :type limping: bool | None
    :param seizure: 是否抽搐或 ``None``。
    :type seizure: bool | None
    :param trauma: 是否外伤或 ``None``。
    :type trauma: bool | None
    :rtype: None
    """
    _set_index_value(index, _index_key("userReport", "text"), text)
    _set_index_value(index, _index_key("userReport", "duration"), duration)
    _set_index_value(index, _index_key("userReport", "symptoms"), list(symptoms))
    _set_index_value(index, _index_key("userReport", "appetite"), appetite)
    _set_index_value(index, _index_key("userReport", "drinking"), drinking)
    _set_index_value(index, _index_key("userReport", "energy"), energy)
    _set_index_value(index, _index_key("userReport", "vomiting"), vomiting)
    _set_index_value(index, _index_key("userReport", "diarrhea"), diarrhea)
    _set_index_value(index, _index_key("userReport", "coughing"), coughing)
    _set_index_value(
        index,
        _index_key("userReport", "breathingDifficulty"),
        breathing_difficulty,
    )
    _set_index_value(index, _index_key("userReport", "pain"), pain)
    _set_index_value(index, _index_key("userReport", "limping"), limping)
    _set_index_value(index, _index_key("userReport", "seizure"), seizure)
    _set_index_value(index, _index_key("userReport", "trauma"), trauma)


def _index_context(
    index: dict[str, Any],
    *,
    environment_temp_c: float | None,
    recent_exercise: str,
    recent_vaccination: bool | None,
    recent_meal: bool | None,
    age_risk: str,
    notes: list[str],
) -> None:
    """写入情境类事实索引。

    :param index: 可变事实索引字典。
    :type index: dict[str, Any]
    :param environment_temp_c: 环境温度或 ``None``。
    :type environment_temp_c: float | None
    :param recent_exercise: 近期运动枚举值。
    :type recent_exercise: str
    :param recent_vaccination: 是否近期疫苗或 ``None``。
    :type recent_vaccination: bool | None
    :param recent_meal: 是否近期进食或 ``None``。
    :type recent_meal: bool | None
    :param age_risk: 年龄风险档枚举值。
    :type age_risk: str
    :param notes: 情境备注列表。
    :type notes: list[str]
    :rtype: None
    """
    _set_index_value(
        index, _index_key("context", "environmentTempC"), environment_temp_c
    )
    _set_index_value(index, _index_key("context", "recentExercise"), recent_exercise)
    _set_index_value(
        index, _index_key("context", "recentVaccination"), recent_vaccination
    )
    _set_index_value(index, _index_key("context", "recentMeal"), recent_meal)
    _set_index_value(index, _index_key("context", "ageRisk"), age_risk)
    _set_index_value(index, _index_key("context", "notes"), list(notes))


def build_fact_index(fact_sheet: FactSheet) -> dict[str, Any]:
    """从 ``FactSheet`` 构建稳定路径事实索引。

    :param fact_sheet: 已组装的客观事实清单。
    :type fact_sheet: FactSheet
    :returns: 路径 → 原始值映射，显式包含 ``None``。
    :rtype: dict[str, Any]
    """
    index: dict[str, Any] = {}

    _index_identity(
        index,
        case_id=fact_sheet.identity.case_id,
        pet_id=fact_sheet.identity.pet_id,
        pet_name=fact_sheet.identity.pet_name,
        species=fact_sheet.identity.species,
        age_months=fact_sheet.identity.age_months,
        breed=fact_sheet.identity.breed,
    )
    _index_profile(
        index,
        sex=fact_sheet.profile.sex,
        weight_kg=fact_sheet.profile.weight_kg,
        neutered=fact_sheet.profile.neutered,
        chronic_conditions=fact_sheet.profile.chronic_conditions,
        medications=fact_sheet.profile.medications,
        allergies=fact_sheet.profile.allergies,
    )
    _index_device(
        index,
        device_online=fact_sheet.device.device_online,
        battery_level=fact_sheet.device.battery_level,
        data_quality=fact_sheet.device.data_quality,
        last_seen_at=fact_sheet.device.last_seen_at,
        collar_id=fact_sheet.device.collar_id,
        warning_text=fact_sheet.device.warning_text,
    )
    _index_vitals(
        index,
        temperature_c=fact_sheet.vitals.temperature_c,
        heart_rate_bpm=fact_sheet.vitals.heart_rate_bpm,
        respiratory_rate_bpm=fact_sheet.vitals.respiratory_rate_bpm,
        hrv_ms=fact_sheet.vitals.hrv_ms,
        steps_today=fact_sheet.vitals.steps_today,
        activity_level=fact_sheet.vitals.activity_level,
        sleep_quality=fact_sheet.vitals.sleep_quality,
        updated_at=fact_sheet.vitals.updated_at,
    )
    _index_upstream(
        index,
        risk_level=fact_sheet.upstream.risk_level,
        risk_label=fact_sheet.upstream.risk_label,
        display_claim=fact_sheet.upstream.display_claim,
        recommendation_text=fact_sheet.upstream.recommendation_text,
        confidence=fact_sheet.upstream.confidence,
        signals=fact_sheet.upstream.signals,
    )
    _index_user_report(
        index,
        text=fact_sheet.user_report.text,
        duration=fact_sheet.user_report.duration,
        symptoms=fact_sheet.user_report.symptoms,
        appetite=fact_sheet.user_report.appetite,
        drinking=fact_sheet.user_report.drinking,
        energy=fact_sheet.user_report.energy,
        vomiting=fact_sheet.user_report.vomiting,
        diarrhea=fact_sheet.user_report.diarrhea,
        coughing=fact_sheet.user_report.coughing,
        breathing_difficulty=fact_sheet.user_report.breathing_difficulty,
        pain=fact_sheet.user_report.pain,
        limping=fact_sheet.user_report.limping,
        seizure=fact_sheet.user_report.seizure,
        trauma=fact_sheet.user_report.trauma,
    )
    _index_context(
        index,
        environment_temp_c=fact_sheet.context.environment_temp_c,
        recent_exercise=fact_sheet.context.recent_exercise,
        recent_vaccination=fact_sheet.context.recent_vaccination,
        recent_meal=fact_sheet.context.recent_meal,
        age_risk=fact_sheet.context.age_risk,
        notes=fact_sheet.context.notes,
    )
    _set_index_value(index, _index_key("missingData"), list(fact_sheet.missing_data))
    _set_index_value(index, _index_key("timestamp"), fact_sheet.timestamp)
    _set_index_value(index, _index_key("scene"), fact_sheet.scene)

    return index


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def extract_fact_sheet(
    agent_input: AgentInput,
    *,
    profile: NormalizationProfile = DEFAULT_NORMALIZATION_PROFILE,
) -> FactSheet:
    """从归一化入参提取客观事实清单。

    纯提取、不推断、不补全 ``null``；上游 healthEvidence 原样作为「声称」保留。

    :param agent_input: 已归一化的 ``AgentInput``。
    :type agent_input: AgentInput
    :param profile: 归一化配置（用于 ``timestamp_epoch_ms`` 开关）。
    :type profile: NormalizationProfile
    :returns: 供 ②③④ 消费的 ``FactSheet``。
    :rtype: FactSheet
    """
    pet = agent_input.pet
    device = agent_input.device
    vitals = agent_input.vitals
    evidence = agent_input.health_evidence
    user_report = agent_input.user_report
    context = agent_input.context

    timestamp_epoch_ms: int | None = None
    if profile.attach_timestamp_epoch_ms:
        timestamp_epoch_ms = timestamp_to_epoch_ms(agent_input.timestamp)

    fact_sheet = FactSheet(
        scene=agent_input.scene,
        timestamp=agent_input.timestamp,
        timestamp_epoch_ms=timestamp_epoch_ms,
        identity=IdentityFacts(
            case_id=agent_input.case_id,
            pet_id=pet.pet_id,
            pet_name=pet.name,
            species=pet.species,
            age_months=pet.age_months,
            breed=pet.breed,
        ),
        profile=ProfileFacts(
            sex=pet.sex,
            weight_kg=pet.weight_kg,
            neutered=pet.neutered,
            chronic_conditions=list(pet.chronic_conditions),
            medications=list(pet.medications),
            allergies=list(pet.allergies),
        ),
        device=DeviceFacts(
            device_online=device.device_online,
            battery_level=device.battery_level,
            data_quality=device.data_quality,
            last_seen_at=device.last_seen_at,
            collar_id=device.collar_id,
            warning_text=device.warning_text,
        ),
        vitals=VitalsFacts(
            temperature_c=vitals.temperature_c,
            heart_rate_bpm=vitals.heart_rate_bpm,
            respiratory_rate_bpm=vitals.respiratory_rate_bpm,
            hrv_ms=vitals.hrv_ms,
            steps_today=vitals.steps_today,
            activity_level=vitals.activity_level,
            sleep_quality=vitals.sleep_quality,
            updated_at=vitals.updated_at,
        ),
        upstream=UpstreamFacts(
            risk_level=evidence.risk_level,
            risk_label=evidence.risk_label,
            display_claim=evidence.display_claim,
            recommendation_text=evidence.recommendation_text,
            confidence=evidence.confidence,
            signals=list(evidence.signals),
        ),
        user_report=UserReportFacts(
            text=user_report.text,
            duration=user_report.duration,
            symptoms=list(user_report.symptoms),
            appetite=user_report.appetite,
            drinking=user_report.drinking,
            energy=user_report.energy,
            vomiting=user_report.vomiting,
            diarrhea=user_report.diarrhea,
            coughing=user_report.coughing,
            breathing_difficulty=user_report.breathing_difficulty,
            pain=user_report.pain,
            limping=user_report.limping,
            seizure=user_report.seizure,
            trauma=user_report.trauma,
        ),
        context=ContextFacts(
            environment_temp_c=context.environment_temp_c,
            recent_exercise=context.recent_exercise,
            recent_vaccination=context.recent_vaccination,
            recent_meal=context.recent_meal,
            age_risk=context.age_risk,
            notes=list(context.notes),
        ),
        missing_data=list(agent_input.missing_data),
        fact_index={},
    )

    return fact_sheet.model_copy(
        update={"fact_index": build_fact_index(fact_sheet)},
    )


def get_fact_value(
    fact_sheet: FactSheet,
    path: str,
) -> Any:
    """按稳定路径读取事实索引中的值。

    :param fact_sheet: 事实清单。
    :type fact_sheet: FactSheet
    :param path: 完整路径键（如 ``fact.vitals.temperatureC``）或不含前缀的相对路径。
    :type path: str
    :returns: 索引中的原始值；路径不存在时返回 ``None``。
    :rtype: Any
    """
    key = path if path.startswith(FACT_INDEX_PREFIX) else _index_key(path)
    return fact_sheet.fact_index.get(key)


def fact_index_contains(
    fact_sheet: FactSheet,
    path: str,
) -> bool:
    """判断事实索引是否包含指定路径（含显式 ``None`` 值）。

    :param fact_sheet: 事实清单。
    :type fact_sheet: FactSheet
    :param path: 完整或相对路径键。
    :type path: str
    :returns: 路径存在于索引中时为 ``True``。
    :rtype: bool
    """
    key = path if path.startswith(FACT_INDEX_PREFIX) else _index_key(path)
    return key in fact_sheet.fact_index
