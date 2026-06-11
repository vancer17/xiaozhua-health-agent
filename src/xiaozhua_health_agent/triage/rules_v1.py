"""Triage Core V1 规则表（``rules[]`` 机器真源）。

对应 ``case-rule-mapping.md`` §四；when 为结构化条件块，由 ``eval_when`` 求值。
"""

from __future__ import annotations

from xiaozhua_health_agent.triage.triage_types import RuleThen, TriageRule


def _then(payload: dict[str, object]) -> RuleThen:
    """将规则 emit 字典校验为 ``RuleThen``（mypy 友好）。"""
    return RuleThen.model_validate(payload)


NOT_EXERCISE = {"not": {"fact": "hasExerciseContext"}}
RESTING = {"fact": "isResting"}


def _ctx01_when() -> dict:
    clinical_cat = {
        "all": [
            {"field": "pet.species", "eq": "cat"},
            {"field": "vitals.temperatureC", "gte": 40.0},
            {
                "any": [
                    {"field": "userReport.energy", "in": ["lower", "very_low"]},
                    {"field": "userReport.appetite", "eq": "reduced"},
                ],
            },
        ],
    }
    clinical_dog = {
        "all": [
            {"field": "pet.species", "eq": "dog"},
            {"field": "vitals.temperatureC", "gte": 39.8},
            {
                "any": [
                    {"field": "userReport.energy", "in": ["lower", "very_low"]},
                    {"field": "userReport.appetite", "eq": "reduced"},
                ],
            },
        ],
    }
    absolute_floor = {"field": "vitals.temperatureC", "gte": 40.0}
    return {
        "all": [
            RESTING,
            NOT_EXERCISE,
            {"any": [clinical_cat, clinical_dog, absolute_floor]},
        ],
    }


def _ctx02_when() -> dict:
    branch_a = {
        "all": [
            {"field": "vitals.respiratoryRateBpm", "gte": 45},
            {
                "any": [
                    {"field": "userReport.breathingDifficulty", "eq": True},
                    {"signal": {"id": "respiratory", "riskGte": "warning"}},
                ],
            },
        ],
    }
    branch_b = {"field": "vitals.respiratoryRateBpm", "gte": 50}
    return {
        "all": [
            RESTING,
            NOT_EXERCISE,
            {"any": [branch_a, branch_b]},
            {
                "not": {
                    "all": [
                        {"fact": "hasChronicHeart"},
                        {"fact": "hasRestingTachypnea"},
                    ],
                },
            },
        ],
    }


TRIAGE_RULES_V1: tuple[TriageRule, ...] = (
    # --- EMG ---
    TriageRule(
        id="EMG-01",
        layer="EMG",
        name="用户报告抽搐",
        when={"field": "userReport.seizure", "eq": True},
        then=_then(
            {
                "risk": "emergency",
                "primaryFlag": "EMERGENCY_SEIZURE",
            }
        ),
        caseIds=["emergency_seizure"],
    ),
    TriageRule(
        id="EMG-02",
        layer="EMG",
        name="上游呼吸 emergency 信号",
        when={
            "any": [
                {"derived": "maxSignalRisk", "eq": "emergency"},
                {"derived": "upstreamRisk", "eq": "emergency"},
            ],
        },
        then=_then(
            {
                "risk": "emergency",
                "primaryFlag": "EMERGENCY_RESPIRATORY",
            }
        ),
        caseIds=["emergency_breathing_difficulty"],
    ),
    TriageRule(
        id="EMG-03",
        layer="EMG",
        name="严重创伤",
        when={"field": "userReport.trauma", "eq": True},
        then=_then(
            {
                "risk": "emergency",
                "primaryFlag": "EMERGENCY_TRAUMA",
            }
        ),
        caseIds=[],
    ),
    TriageRule(
        id="EMG-04",
        layer="EMG",
        name="呼吸困难紧急阈值",
        when={
            "all": [
                {"field": "userReport.breathingDifficulty", "eq": True},
                {
                    "any": [
                        {"fact": "severeRestingResp"},
                        {"fact": "openMouthBreathingReported"},
                        {
                            "all": [
                                {"fact": "isBrachycephalic"},
                                {"field": "vitals.respiratoryRateBpm", "gte": 55},
                            ],
                        },
                    ],
                },
            ],
        },
        then=_then(
            {
                "risk": "emergency",
                "primaryFlag": "EMERGENCY_RESPIRATORY",
            }
        ),
        caseIds=["emergency_breathing_difficulty"],
    ),
    # --- DQ ---
    TriageRule(
        id="DQ-01",
        layer="DQ",
        name="数据缺失门禁",
        when={
            "any": [
                {"field": "device.dataQuality", "eq": "missing"},
                {"fact": "vitalsCoreMissing"},
            ],
        },
        then=_then(
            {
                "risk": "watch",
                "riskFloor": "watch",
                "primaryFlag": "DATA_MISSING",
            }
        ),
        caseIds=["missing_vitals"],
    ),
    TriageRule(
        id="DQ-02",
        layer="DQ",
        name="数据过期门禁",
        when={"field": "device.dataQuality", "eq": "stale"},
        then=_then(
            {
                "risk": "watch",
                "riskFloor": "watch",
                "primaryFlag": "DATA_STALE",
            }
        ),
        caseIds=["stale_device_data"],
    ),
    TriageRule(
        id="DQ-03",
        layer="DQ",
        name="部分数据（零 emit）",
        when={"field": "device.dataQuality", "eq": "partial"},
        then=None,
        caseIds=[
            "limping_pain_watch",
            "emergency_seizure",
            "senior_cat_low_energy",
            "persistent_vomiting_warning",
        ],
    ),
    # --- CTX ---
    TriageRule(
        id="CTX-01",
        layer="CTX",
        priority=10,
        name="安静态高热",
        when=_ctx01_when(),
        then=_then({"risk": "warning", "primaryFlag": "FEVER_RESTING"}),
        caseIds=["high_fever_resting"],
    ),
    TriageRule(
        id="CTX-02",
        layer="CTX",
        priority=20,
        name="安静态呼吸偏高",
        when=_ctx02_when(),
        then=_then({"risk": "warning", "primaryFlag": "RESP_RESTING"}),
        caseIds=["respiratory_rate_high_resting"],
    ),
    TriageRule(
        id="CTX-03",
        layer="CTX",
        priority=30,
        name="慢病+安静心率异常",
        when={
            "all": [
                {"fact": "hasChronicHeart"},
                {"fact": "hasRestingTachycardia"},
            ],
        },
        then=_then({"risk": "warning", "primaryFlag": "HR_RESTING_CHRONIC"}),
        caseIds=["heart_rate_high_resting_warning"],
    ),
    TriageRule(
        id="CTX-04",
        layer="CTX",
        priority=40,
        name="慢病+安静呼吸异常",
        when={
            "all": [
                {"fact": "hasChronicHeart"},
                {"fact": "hasRestingTachypnea"},
            ],
        },
        then=_then({"risk": "warning", "primaryFlag": "CHRONIC_HEART_RESP"}),
        caseIds=["chronic_heart_resp_warning"],
    ),
    TriageRule(
        id="CTX-05",
        layer="CTX",
        priority=50,
        name="用户/设备冲突",
        when={
            "all": [
                {"fact": "userSaysNormal"},
                {"fact": "deviceShowsRestingFever"},
            ],
        },
        then=_then({"risk": "warning", "primaryFlag": "USER_DEVICE_CONFLICT"}),
        caseIds=["conflict_user_normal_sensor_fever"],
    ),
    TriageRule(
        id="CTX-06",
        layer="CTX",
        priority=60,
        name="反复呕吐",
        when={"field": "userReport.vomiting", "eq": "repeated"},
        then=_then({"risk": "warning", "primaryFlag": "REPEATED_VOMITING"}),
        caseIds=["persistent_vomiting_warning"],
    ),
    TriageRule(
        id="CTX-07",
        layer="CTX",
        priority=70,
        name="老年精神食欲下降",
        when={
            "all": [
                {"fact": "isSenior"},
                {"field": "userReport.energy", "in": ["lower", "very_low"]},
                {"field": "userReport.appetite", "eq": "reduced"},
                {"fact": "hasChronicConditions"},
            ],
        },
        then=_then({"risk": "warning", "primaryFlag": "SENIOR_DECLINE"}),
        caseIds=["senior_cat_low_energy"],
    ),
    TriageRule(
        id="CTX-08",
        layer="CTX",
        priority=80,
        name="幼犬发热",
        when={
            "all": [
                {"fact": "isPuppyKitten"},
                RESTING,
                {"field": "vitals.temperatureC", "gte": 39.5},
                {"field": "userReport.energy", "in": ["lower", "very_low"]},
            ],
        },
        then=_then({"risk": "warning", "primaryFlag": "PUPPY_FEVER"}),
        caseIds=["puppy_fever_high_risk"],
    ),
    TriageRule(
        id="CTX-09a",
        layer="CTX",
        priority=90,
        name="运动后体温偏高",
        when={
            "all": [
                {"fact": "hasExerciseContext"},
                {"field": "vitals.temperatureC", "gte": 39.0},
                {"signal": {"id": "temperature", "riskEq": "watch"}},
            ],
        },
        then=_then({"risk": "watch", "primaryFlag": "POST_EXERCISE"}),
        caseIds=["mild_fever_after_exercise"],
    ),
    TriageRule(
        id="CTX-09b",
        layer="CTX",
        priority=91,
        name="运动后心率偏高",
        when={
            "all": [
                {"fact": "hasExerciseContext"},
                {"signal": {"id": "heart_rate", "riskEq": "watch"}},
            ],
        },
        then=_then({"risk": "watch", "primaryFlag": "POST_EXERCISE"}),
        caseIds=["heart_rate_high_after_play"],
    ),
    TriageRule(
        id="CTX-10",
        layer="CTX",
        priority=100,
        name="HRV 压力",
        when={
            "all": [
                {"signal": {"id": "hrv", "riskGte": "watch"}},
                {"fact": "hasStressContext"},
            ],
        },
        then=_then({"risk": "watch", "primaryFlag": "HRV_STRESS"}),
        caseIds=["hrv_stress_watch"],
    ),
    TriageRule(
        id="CTX-11",
        layer="CTX",
        priority=110,
        name="跛行/疼痛",
        when={
            "any": [
                {"field": "userReport.limping", "eq": True},
                {"field": "userReport.pain", "eq": True},
                {"signal": {"id": "pain", "riskGte": "watch"}},
            ],
        },
        then=_then({"risk": "watch", "primaryFlag": "LIMPING_PAIN"}),
        caseIds=["limping_pain_watch"],
    ),
    TriageRule(
        id="CTX-12",
        layer="CTX",
        priority=120,
        name="恢复慢",
        when={
            "any": [
                {"signal": {"id": "recovery", "riskGte": "watch"}},
                {"fact": "hasSlowRecoveryContext"},
            ],
        },
        then=_then({"risk": "watch", "primaryFlag": "SLOW_RECOVERY"}),
        caseIds=["recovery_slow_watch"],
    ),
    TriageRule(
        id="CTX-13",
        layer="CTX",
        priority=130,
        name="轻度腹泻",
        when={
            "all": [
                {"field": "userReport.diarrhea", "eq": "mild"},
                {"field": "userReport.energy", "eq": "normal"},
            ],
        },
        then=_then({"risk": "watch", "primaryFlag": "MILD_DIARRHEA"}),
        caseIds=["mild_diarrhea_watch"],
    ),
    TriageRule(
        id="CTX-14",
        layer="CTX",
        priority=140,
        name="疫苗后疲倦",
        when={
            "all": [
                {"field": "context.recentVaccination", "eq": True},
                {"field": "userReport.energy", "eq": "lower"},
            ],
        },
        then=_then({"risk": "watch", "primaryFlag": "POST_VACCINE"}),
        caseIds=["post_vaccine_tired_watch"],
    ),
    TriageRule(
        id="CTX-15",
        layer="CTX",
        priority=200,
        name="多源一致正常",
        when={
            "all": [
                {"derived": "upstreamRisk", "eq": "normal"},
                {"fact": "maxSignalRiskAtMostNormal"},
                {"field": "device.dataQuality", "eq": "good"},
                {"not": {"field": "userReport.seizure", "eq": True}},
                {"not": {"field": "userReport.trauma", "eq": True}},
                {"not": {"field": "userReport.vomiting", "eq": "repeated"}},
            ],
        },
        then=_then({"risk": "normal", "primaryFlag": "NORMAL_DAILY"}),
        caseIds=["normal_dog_daily_check"],
    ),
)

BUNDLE_VERSION: str = "1.0.0"
