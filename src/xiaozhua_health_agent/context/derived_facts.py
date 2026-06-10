"""DerivedFacts 预计算（WP2）。

在步骤 ② 规则引擎入口对 ``FactSheet`` 一次性推导派生事实，
对应 ``kb-rule-derived-facts-spec.md``。
"""

from __future__ import annotations

from xiaozhua_health_agent.context.context_types import (
    DerivedFacts,
    MaxSignalRiskLiteral,
)
from xiaozhua_health_agent.context.risk_order import max_risk_level, risk_gte
from xiaozhua_health_agent.context.text_matchers import (
    breed_matches_brachycephalic,
    notes_indicate_exercise_context,
    reports_open_mouth_breathing,
    signal_reasons_indicate_exercise_context,
    user_text_says_normal,
)
from xiaozhua_health_agent.context.thresholds import (
    BRACHYCEPHALIC_CONDITION_TAG,
    CHRONIC_HEART_CONDITION_TAGS,
    DEFAULT_DERIVED_FACTS_THRESHOLDS,
    DerivedFactsThresholds,
    device_resting_fever_threshold_c,
    senior_age_threshold_months,
)
from xiaozhua_health_agent.parse import FactSheet
from xiaozhua_health_agent.schemas import SignalRiskLevelLiteral

# JSON ``{ "fact": "isResting" }`` → DerivedFacts 属性名
DERIVED_FACT_JSON_NAMES: dict[str, str] = {
    "isResting": "is_resting",
    "isActive": "is_active",
    "hasExerciseContext": "has_exercise_context",
    "vitalsCoreMissing": "vitals_core_missing",
    "maxSignalRisk": "max_signal_risk",
    "upstreamRisk": "upstream_risk",
    "userSaysNormal": "user_says_normal",
    "deviceShowsRestingFever": "device_shows_resting_fever",
    "hasChronicHeart": "has_chronic_heart",
    "isSenior": "is_senior",
    "isPuppyKitten": "is_puppy_kitten",
    "isBrachycephalic": "is_brachycephalic",
    "openMouthBreathingReported": "open_mouth_breathing_reported",
    "severeRestingResp": "severe_resting_resp",
    "hasRestingTachycardia": "has_resting_tachycardia",
    "hasRestingTachypnea": "has_resting_tachypnea",
}


def compute_derived_facts(
    fact_sheet: FactSheet,
    *,
    thresholds: DerivedFactsThresholds = DEFAULT_DERIVED_FACTS_THRESHOLDS,
) -> DerivedFacts:
    """从 ``FactSheet`` 一次性预计算全部派生事实。

    :param fact_sheet: 步骤 ① 产出的客观事实清单。
    :type fact_sheet: FactSheet
    :param thresholds: 阈值配置快照。
    :type thresholds: DerivedFactsThresholds
    :returns: 不可变派生事实对象。
    :rtype: DerivedFacts
    """
    upstream = fact_sheet.upstream
    user_report = fact_sheet.user_report

    is_active = _compute_is_active(fact_sheet)
    is_resting = _compute_is_resting(fact_sheet)
    has_exercise_context = _compute_has_exercise_context(
        fact_sheet,
        is_active=is_active,
    )
    vitals_core_missing = _compute_vitals_core_missing(fact_sheet)
    max_signal_risk = _compute_max_signal_risk(fact_sheet)
    upstream_risk = upstream.risk_level
    user_says_normal = _compute_user_says_normal(fact_sheet)
    device_shows_resting_fever = _compute_device_shows_resting_fever(
        fact_sheet,
        is_resting=is_resting,
        thresholds=thresholds,
    )
    has_chronic_heart = _compute_has_chronic_heart(fact_sheet)
    is_senior = _compute_is_senior(fact_sheet, thresholds=thresholds)
    is_puppy_kitten = _compute_is_puppy_kitten(fact_sheet, thresholds=thresholds)
    is_brachycephalic = _compute_is_brachycephalic(fact_sheet)
    open_mouth_breathing_reported = reports_open_mouth_breathing(
        text=user_report.text,
        symptoms=user_report.symptoms,
    )
    severe_resting_resp = _compute_severe_resting_resp(
        fact_sheet,
        is_resting=is_resting,
        thresholds=thresholds,
    )
    has_resting_tachycardia = _compute_has_resting_tachycardia(
        fact_sheet,
        is_resting=is_resting,
        has_exercise_context=has_exercise_context,
        thresholds=thresholds,
    )
    has_resting_tachypnea = _compute_has_resting_tachypnea(
        fact_sheet,
        is_resting=is_resting,
        has_exercise_context=has_exercise_context,
        thresholds=thresholds,
    )

    return DerivedFacts(
        is_resting=is_resting,
        is_active=is_active,
        has_exercise_context=has_exercise_context,
        vitals_core_missing=vitals_core_missing,
        max_signal_risk=max_signal_risk,
        upstream_risk=upstream_risk,
        user_says_normal=user_says_normal,
        device_shows_resting_fever=device_shows_resting_fever,
        has_chronic_heart=has_chronic_heart,
        is_senior=is_senior,
        is_puppy_kitten=is_puppy_kitten,
        is_brachycephalic=is_brachycephalic,
        open_mouth_breathing_reported=open_mouth_breathing_reported,
        severe_resting_resp=severe_resting_resp,
        has_resting_tachycardia=has_resting_tachycardia,
        has_resting_tachypnea=has_resting_tachypnea,
    )


def get_derived_fact_by_json_name(
    derived: DerivedFacts,
    json_name: str,
) -> bool | str | None:
    """按决策表 JSON 中的 ``fact`` / ``derived`` 名读取派生事实值。

    :param derived: 派生事实快照。
    :type derived: DerivedFacts
    :param json_name: camelCase 符号名（如 ``isResting``、``maxSignalRisk``）。
    :type json_name: str
    :returns: 对应字段值。
    :rtype: bool | str | None
    :raises KeyError: 未知符号名。
    """
    attr_name = DERIVED_FACT_JSON_NAMES.get(json_name)
    if attr_name is None:
        msg = f"未知 DerivedFacts 符号: {json_name!r}"
        raise KeyError(msg)
    return getattr(derived, attr_name)


def _compute_is_resting(fact_sheet: FactSheet) -> bool:
    """计算 ``is_resting``。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :returns: 安静/非运动情境时为 ``True``。
    :rtype: bool
    """
    activity = fact_sheet.vitals.activity_level
    exercise = fact_sheet.context.recent_exercise
    return activity in {"resting", "unknown"} and exercise in {"none", "unknown"}


def _compute_is_active(fact_sheet: FactSheet) -> bool:
    """计算 ``is_active``。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :returns: 活动/运动情境时为 ``True``。
    :rtype: bool
    """
    activity = fact_sheet.vitals.activity_level
    exercise = fact_sheet.context.recent_exercise
    return activity in {"active", "intense"} or exercise in {"moderate", "intense"}


def _compute_has_exercise_context(
    fact_sheet: FactSheet,
    *,
    is_active: bool,
) -> bool:
    """计算 ``has_exercise_context``（宽口径运动情境）。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :param is_active: 已计算的 ``is_active``。
    :type is_active: bool
    :returns: 存在运动/玩耍上下文时为 ``True``。
    :rtype: bool
    """
    if is_active:
        return True
    signal_reasons = [signal.reason for signal in fact_sheet.upstream.signals]
    if notes_indicate_exercise_context(fact_sheet.context.notes):
        return True
    return signal_reasons_indicate_exercise_context(signal_reasons)


def _compute_vitals_core_missing(fact_sheet: FactSheet) -> bool:
    """计算 ``vitals_core_missing``。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :returns: 体温、心率、呼吸率均为 null 时为 ``True``。
    :rtype: bool
    """
    vitals = fact_sheet.vitals
    return (
        vitals.temperature_c is None
        and vitals.heart_rate_bpm is None
        and vitals.respiratory_rate_bpm is None
    )


def _compute_max_signal_risk(fact_sheet: FactSheet) -> MaxSignalRiskLiteral:
    """计算 ``max_signal_risk``。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :returns: signals 最高风险档；无信号时 ``None``。
    :rtype: MaxSignalRiskLiteral
    """
    signals = fact_sheet.upstream.signals
    if not signals:
        return None
    levels: list[SignalRiskLevelLiteral] = [signal.risk_level for signal in signals]
    return max_risk_level(levels)


def _compute_user_says_normal(fact_sheet: FactSheet) -> bool:
    """计算 ``user_says_normal``。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :returns: 用户主观认为正常且无矛盾结构化字段时为 ``True``。
    :rtype: bool
    """
    user_report = fact_sheet.user_report
    if user_report.symptoms:
        return False
    if user_report.energy != "normal":
        return False
    return user_text_says_normal(user_report.text)


def _compute_device_shows_resting_fever(
    fact_sheet: FactSheet,
    *,
    is_resting: bool,
    thresholds: DerivedFactsThresholds,
) -> bool:
    """计算 ``device_shows_resting_fever``。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :param is_resting: 已计算的 ``is_resting``。
    :type is_resting: bool
    :param thresholds: 阈值配置。
    :type thresholds: DerivedFactsThresholds
    :returns: 安静态下设备测得偏高体温时为 ``True``。
    :rtype: bool
    """
    if not is_resting:
        return False
    temperature = fact_sheet.vitals.temperature_c
    if temperature is None:
        return False
    threshold = device_resting_fever_threshold_c(
        fact_sheet.identity.species,
        thresholds=thresholds,
    )
    if threshold is None:
        return False
    return temperature >= threshold


def _compute_has_chronic_heart(fact_sheet: FactSheet) -> bool:
    """计算 ``has_chronic_heart``。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :returns: 存在心脏相关慢病标签时为 ``True``。
    :rtype: bool
    """
    conditions = set(fact_sheet.profile.chronic_conditions)
    return bool(conditions & CHRONIC_HEART_CONDITION_TAGS)


def _compute_is_senior(
    fact_sheet: FactSheet,
    *,
    thresholds: DerivedFactsThresholds,
) -> bool:
    """计算 ``is_senior``。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :param thresholds: 阈值配置。
    :type thresholds: DerivedFactsThresholds
    :returns: 老年宠物时为 ``True``。
    :rtype: bool
    """
    if fact_sheet.context.age_risk == "senior":
        return True
    age_months = fact_sheet.identity.age_months
    if age_months is None:
        return False
    threshold = senior_age_threshold_months(
        fact_sheet.identity.species,
        thresholds=thresholds,
    )
    if threshold is None:
        return False
    return age_months >= threshold


def _compute_is_puppy_kitten(
    fact_sheet: FactSheet,
    *,
    thresholds: DerivedFactsThresholds,
) -> bool:
    """计算 ``is_puppy_kitten``。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :param thresholds: 阈值配置。
    :type thresholds: DerivedFactsThresholds
    :returns: 幼宠时为 ``True``。
    :rtype: bool
    """
    if fact_sheet.context.age_risk == "puppy_kitten":
        return True
    age_months = fact_sheet.identity.age_months
    if age_months is None:
        return False
    return age_months <= thresholds.puppy_kitten_max_age_months


def _compute_is_brachycephalic(fact_sheet: FactSheet) -> bool:
    """计算 ``is_brachycephalic``。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :returns: 短鼻体质标签或品种命中时为 ``True``。
    :rtype: bool
    """
    if BRACHYCEPHALIC_CONDITION_TAG in fact_sheet.profile.chronic_conditions:
        return True
    return breed_matches_brachycephalic(fact_sheet.identity.breed)


def _compute_severe_resting_resp(
    fact_sheet: FactSheet,
    *,
    is_resting: bool,
    thresholds: DerivedFactsThresholds,
) -> bool:
    """计算 ``severe_resting_resp``。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :param is_resting: 已计算的 ``is_resting``。
    :type is_resting: bool
    :param thresholds: 阈值配置。
    :type thresholds: DerivedFactsThresholds
    :returns: 安静态呼吸率极高时为 ``True``。
    :rtype: bool
    """
    if not is_resting:
        return False
    rr = fact_sheet.vitals.respiratory_rate_bpm
    if rr is None:
        return False
    return rr >= thresholds.severe_resting_resp_bpm


def _signal_matches_id_and_risk(
    fact_sheet: FactSheet,
    *,
    signal_id: str,
    minimum_risk: SignalRiskLevelLiteral,
) -> bool:
    """判断是否存在指定 id 且风险不低于下限的 signal。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :param signal_id: 信号类型标识。
    :type signal_id: str
    :param minimum_risk: 风险下限。
    :type minimum_risk: SignalRiskLevelLiteral
    :returns: 存在匹配 signal 时为 ``True``。
    :rtype: bool
    """
    for signal in fact_sheet.upstream.signals:
        if signal.id != signal_id:
            continue
        if risk_gte(signal.risk_level, minimum_risk):
            return True
    return False


def _compute_has_resting_tachycardia(
    fact_sheet: FactSheet,
    *,
    is_resting: bool,
    has_exercise_context: bool,
    thresholds: DerivedFactsThresholds,
) -> bool:
    """计算 ``has_resting_tachycardia``。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :param is_resting: 已计算的 ``is_resting``。
    :type is_resting: bool
    :param has_exercise_context: 已计算的 ``has_exercise_context``。
    :type has_exercise_context: bool
    :param thresholds: 阈值配置。
    :type thresholds: DerivedFactsThresholds
    :returns: 安静非运动窗口内心率异常时为 ``True``。
    :rtype: bool
    """
    if not is_resting or has_exercise_context:
        return False
    if _signal_matches_id_and_risk(
        fact_sheet,
        signal_id="heart_rate",
        minimum_risk="warning",
    ):
        return True
    hr = fact_sheet.vitals.heart_rate_bpm
    if hr is None:
        return False
    return hr >= thresholds.resting_tachycardia_hr_bpm


def _compute_has_resting_tachypnea(
    fact_sheet: FactSheet,
    *,
    is_resting: bool,
    has_exercise_context: bool,
    thresholds: DerivedFactsThresholds,
) -> bool:
    """计算 ``has_resting_tachypnea``。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :param is_resting: 已计算的 ``is_resting``。
    :type is_resting: bool
    :param has_exercise_context: 已计算的 ``has_exercise_context``。
    :type has_exercise_context: bool
    :param thresholds: 阈值配置。
    :type thresholds: DerivedFactsThresholds
    :returns: 安静非运动窗口内呼吸异常时为 ``True``。
    :rtype: bool
    """
    if not is_resting or has_exercise_context:
        return False
    if _signal_matches_id_and_risk(
        fact_sheet,
        signal_id="respiratory",
        minimum_risk="warning",
    ):
        return True
    rr = fact_sheet.vitals.respiratory_rate_bpm
    if rr is None:
        return False
    return rr >= thresholds.resting_tachypnea_rr_bpm
