"""L1-02 输入归一化器（WP1）。

在契约校验通过后统一 input 的表示形式，**只改写法、不改医学语义**。
"""

from __future__ import annotations

from datetime import datetime

from xiaozhua_health_agent.schemas import (
    AgentInput,
    Context,
    DeviceState,
    HealthEvidence,
    HealthSignal,
    PetProfile,
    UserReport,
)

from xiaozhua_health_agent.parse.parse_types import (
    DEFAULT_NORMALIZATION_PROFILE,
    NormalizationProfile,
)

# ---------------------------------------------------------------------------
# 内部工具
# ---------------------------------------------------------------------------


def _normalize_optional_string(
    value: str | None,
    *,
    trim: bool,
) -> str | None:
    """归一化可选字符串字段。

    :param value: 原始字符串或 ``None``。
    :type value: str | None
    :param trim: 是否裁剪首尾空白。
    :type trim: bool
    :returns: 归一化后的字符串；``None`` 保持 ``None``，空字符串不改为默认值。
    :rtype: str | None
    """
    if value is None:
        return None
    if not trim:
        return value
    return value.strip()


def _normalize_required_string(
    value: str,
    *,
    trim: bool,
) -> str:
    """归一化必填字符串字段。

    :param value: 原始字符串。
    :type value: str
    :param trim: 是否裁剪首尾空白。
    :type trim: bool
    :returns: 归一化后的字符串。
    :rtype: str
    """
    if not trim:
        return value
    return value.strip()


def _normalize_string_list(
    items: list[str],
    *,
    dedupe: bool,
    sort_items: bool,
) -> list[str]:
    """归一化字符串数组：可选去重与稳定排序。

    :param items: 原始字符串列表。
    :type items: list[str]
    :param dedupe: 是否去重（保留首次出现顺序的基础上去重）。
    :type dedupe: bool
    :param sort_items: 是否按字典序稳定排序。
    :type sort_items: bool
    :returns: 归一化后的列表；空列表保持 ``[]``。
    :rtype: list[str]
    """
    normalized: list[str] = [
        item.strip() if isinstance(item, str) else item for item in items
    ]

    if dedupe:
        seen: set[str] = set()
        unique: list[str] = []
        for item in normalized:
            if item not in seen:
                seen.add(item)
                unique.append(item)
        normalized = unique

    if sort_items:
        normalized = sorted(normalized)

    return normalized


def _normalize_pet_profile(
    pet: PetProfile,
    *,
    profile: NormalizationProfile,
) -> PetProfile:
    """归一化宠物档案子对象。

    :param pet: 原始宠物档案。
    :type pet: PetProfile
    :param profile: 归一化配置。
    :type profile: NormalizationProfile
    :returns: 归一化后的宠物档案副本。
    :rtype: PetProfile
    """
    return pet.model_copy(
        update={
            "name": _normalize_required_string(
                pet.name,
                trim=profile.trim_strings,
            ),
            "breed": _normalize_optional_string(
                pet.breed,
                trim=profile.trim_strings,
            ),
            "chronic_conditions": _normalize_string_list(
                pet.chronic_conditions,
                dedupe=profile.dedupe_string_arrays,
                sort_items=profile.sort_string_arrays,
            ),
            "medications": _normalize_string_list(
                pet.medications,
                dedupe=profile.dedupe_string_arrays,
                sort_items=profile.sort_string_arrays,
            ),
            "allergies": _normalize_string_list(
                pet.allergies,
                dedupe=profile.dedupe_string_arrays,
                sort_items=profile.sort_string_arrays,
            ),
        },
    )


def _normalize_device_state(
    device: DeviceState,
    *,
    profile: NormalizationProfile,
) -> DeviceState:
    """归一化设备状态子对象。

    :param device: 原始设备状态。
    :type device: DeviceState
    :param profile: 归一化配置。
    :type profile: NormalizationProfile
    :returns: 归一化后的设备状态副本。
    :rtype: DeviceState
    """
    return device.model_copy(
        update={
            "collar_id": _normalize_optional_string(
                device.collar_id,
                trim=profile.trim_strings,
            ),
            "warning_text": _normalize_optional_string(
                device.warning_text,
                trim=profile.trim_strings,
            ),
        },
    )


def _normalize_health_signal(
    signal: HealthSignal,
    *,
    profile: NormalizationProfile,
) -> HealthSignal:
    """归一化单条上游健康信号。

    :param signal: 原始信号。
    :type signal: HealthSignal
    :param profile: 归一化配置。
    :type profile: NormalizationProfile
    :returns: 归一化后的信号副本。
    :rtype: HealthSignal
    """
    return signal.model_copy(
        update={
            "label": _normalize_required_string(
                signal.label,
                trim=profile.trim_strings,
            ),
            "reason": _normalize_required_string(
                signal.reason,
                trim=profile.trim_strings,
            ),
            "unit": _normalize_optional_string(
                signal.unit,
                trim=profile.trim_strings,
            ),
        },
    )


def _normalize_health_evidence(
    evidence: HealthEvidence,
    *,
    profile: NormalizationProfile,
) -> HealthEvidence:
    """归一化上游健康证据子对象。

    :param evidence: 原始 healthEvidence。
    :type evidence: HealthEvidence
    :param profile: 归一化配置。
    :type profile: NormalizationProfile
    :returns: 归一化后的证据副本。
    :rtype: HealthEvidence
    """
    return evidence.model_copy(
        update={
            "risk_label": _normalize_required_string(
                evidence.risk_label,
                trim=profile.trim_strings,
            ),
            "display_claim": _normalize_required_string(
                evidence.display_claim,
                trim=profile.trim_strings,
            ),
            "recommendation_text": _normalize_required_string(
                evidence.recommendation_text,
                trim=profile.trim_strings,
            ),
            "signals": [
                _normalize_health_signal(signal, profile=profile)
                for signal in evidence.signals
            ],
        },
    )


def _normalize_user_report(
    user_report: UserReport,
    *,
    profile: NormalizationProfile,
) -> UserReport:
    """归一化用户自述子对象。

    :param user_report: 原始用户自述。
    :type user_report: UserReport
    :param profile: 归一化配置。
    :type profile: NormalizationProfile
    :returns: 归一化后的用户自述副本。
    :rtype: UserReport
    """
    return user_report.model_copy(
        update={
            "text": _normalize_required_string(
                user_report.text,
                trim=profile.trim_strings,
            ),
            "duration": _normalize_optional_string(
                user_report.duration,
                trim=profile.trim_strings,
            ),
            "symptoms": _normalize_string_list(
                user_report.symptoms,
                dedupe=profile.dedupe_string_arrays,
                sort_items=profile.sort_string_arrays,
            ),
        },
    )


def _normalize_context(
    context: Context,
    *,
    profile: NormalizationProfile,
) -> Context:
    """归一化情境子对象。

    :param context: 原始情境信息。
    :type context: Context
    :param profile: 归一化配置。
    :type profile: NormalizationProfile
    :returns: 归一化后的情境副本。
    :rtype: Context
    """
    return context.model_copy(
        update={
            "notes": _normalize_string_list(
                context.notes,
                dedupe=profile.dedupe_string_arrays,
                sort_items=profile.sort_string_arrays,
            ),
        },
    )


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


def normalize_agent_input(
    agent_input: AgentInput,
    *,
    profile: NormalizationProfile = DEFAULT_NORMALIZATION_PROFILE,
) -> AgentInput:
    """对已通过契约校验的入参执行表示归一化。

    归一化规则（与架构 L1-02 对齐）：

    - 字符串 ``trim``（不把 ``null`` 改为默认值）
    - 字符串数组去重 + 稳定排序
    - 数值与布尔保持原值，不四舍五入、不把 ``null`` 填为 ``0``

    :param agent_input: 已通过 ``validate_input`` 的强类型入参。
    :type agent_input: AgentInput
    :param profile: 归一化配置；默认 ``DEFAULT_NORMALIZATION_PROFILE``。
    :type profile: NormalizationProfile
    :returns: 结构等价、表示统一的入参副本。
    :rtype: AgentInput
    """
    return agent_input.model_copy(
        update={
            "case_id": _normalize_required_string(
                agent_input.case_id,
                trim=profile.trim_strings,
            ),
            "pet": _normalize_pet_profile(agent_input.pet, profile=profile),
            "device": _normalize_device_state(agent_input.device, profile=profile),
            "vitals": agent_input.vitals.model_copy(),
            "health_evidence": _normalize_health_evidence(
                agent_input.health_evidence,
                profile=profile,
            ),
            "user_report": _normalize_user_report(
                agent_input.user_report,
                profile=profile,
            ),
            "context": _normalize_context(agent_input.context, profile=profile),
            "missing_data": _normalize_string_list(
                list(agent_input.missing_data),
                dedupe=profile.dedupe_string_arrays,
                sort_items=profile.sort_string_arrays,
            ),
        },
    )


def timestamp_to_epoch_ms(timestamp: datetime) -> int:
    """将请求时间转为 Unix 毫秒时间戳。

    :param timestamp: 请求时间（须为 timezone-aware 或 naive 一致处理）。
    :type timestamp: datetime
    :returns: Unix 毫秒整数。
    :rtype: int
    """
    return int(timestamp.timestamp() * 1000)
