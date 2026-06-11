"""Triage Core V1 PolicyTables、Evidence 与 postProcess 数据。"""

from __future__ import annotations

from xiaozhua_health_agent.triage.triage_types import (
    PrimaryActionHintLiteral,
    PrimaryFlagLiteral,
)

BUNDLE_VERSION = "1.0.0"

GLOBAL_FORBIDDEN_THEMES: tuple[str, ...] = (
    "确诊为",
    "就是",
    "肯定是",
    "一定是",
    "一定没事",
    "保证",
    "百分百",
    "不用担心",
    "肯定能好",
    "不用看医生",
    "无需就医",
    "不必就医",
    "不需要看兽医",
    "继续观察即可",
    "先等等",
    "明天再看",
    "不着急",
)

FORCED_MENTIONS_BY_FLAG: dict[PrimaryFlagLiteral, tuple[str, ...]] = {
    "NORMAL_DAILY": ("状态平稳", "日常观察"),
    "POST_EXERCISE": ("休息", "补水", "复查"),
    "FEVER_RESTING": ("体温", "联系兽医", "精神状态"),
    "RESP_RESTING": ("呼吸", "安静状态", "联系兽医"),
    "HR_RESTING_CHRONIC": ("安静状态", "既往史", "联系兽医"),
    "CHRONIC_HEART_RESP": ("心脏病史", "安静呼吸", "联系兽医"),
    "USER_DEVICE_CONFLICT": ("用户描述", "体温", "复查"),
    "REPEATED_VOMITING": ("反复呕吐", "联系兽医", "不要自行用药"),
    "SENIOR_DECLINE": ("老年", "食欲", "联系兽医"),
    "PUPPY_FEVER": ("幼犬", "体温", "联系兽医"),
    "HRV_STRESS": ("压力", "睡眠", "环境变化"),
    "LIMPING_PAIN": ("减少运动", "观察步态", "持续或加重"),
    "SLOW_RECOVERY": ("恢复", "睡眠", "降低活动强度"),
    "MILD_DIARRHEA": ("腹泻", "观察", "精神"),
    "POST_VACCINE": ("疫苗", "观察", "食欲"),
    "DATA_MISSING": ("数据不足", "设备", "不能判断"),
    "DATA_STALE": ("数据过期", "设备在线", "不能依据旧数据判断"),
    "EMERGENCY_SEIZURE": ("抽搐", "立即", "兽医"),
    "EMERGENCY_RESPIRATORY": ("立即", "兽医", "就医"),
    "EMERGENCY_TRAUMA": ("立即", "兽医", "就医"),
}

FORBIDDEN_BY_FLAG: dict[PrimaryFlagLiteral, tuple[str, ...]] = {
    "NORMAL_DAILY": ("确诊", "立即就医"),
    "POST_EXERCISE": ("确诊",),
    "FEVER_RESTING": ("确诊", "一定没事"),
    "RESP_RESTING": ("确诊", "不用看医生"),
    "HR_RESTING_CHRONIC": ("确诊",),
    "CHRONIC_HEART_RESP": ("确诊", "自行调整药量", "自行停药", "加量", "减量"),
    "USER_DEVICE_CONFLICT": ("确诊", "忽略设备数据", "以用户感受为准", "设备不可信"),
    "REPEATED_VOMITING": ("确诊", "一定没事"),
    "SENIOR_DECLINE": ("确诊", "只是正常老化", "老了都这样"),
    "PUPPY_FEVER": ("确诊", "继续观察即可", "再等等"),
    "HRV_STRESS": ("确诊",),
    "LIMPING_PAIN": ("确诊",),
    "SLOW_RECOVERY": ("确诊",),
    "MILD_DIARRHEA": ("确诊",),
    "POST_VACCINE": ("确诊",),
    "DATA_MISSING": ("确诊", "正常", "一定没事", "目前健康", "一切正常"),
    "DATA_STALE": ("确诊", "当前正常", "一切正常", "现在很正常", "目前正常"),
    "EMERGENCY_SEIZURE": ("确诊", "继续观察即可", "不用看医生", "先观察", "不着急"),
    "EMERGENCY_RESPIRATORY": ("确诊", "继续观察即可", "不用看医生", "先观察", "不着急"),
    "EMERGENCY_TRAUMA": ("确诊", "继续观察即可", "不用看医生", "先观察", "不着急"),
}

SAFETY_BY_FLAG: dict[PrimaryFlagLiteral, bool] = {
    "NORMAL_DAILY": False,
    "POST_EXERCISE": True,
    "FEVER_RESTING": True,
    "RESP_RESTING": True,
    "HR_RESTING_CHRONIC": True,
    "CHRONIC_HEART_RESP": True,
    "USER_DEVICE_CONFLICT": True,
    "REPEATED_VOMITING": True,
    "SENIOR_DECLINE": True,
    "PUPPY_FEVER": True,
    "HRV_STRESS": False,
    "LIMPING_PAIN": True,
    "SLOW_RECOVERY": False,
    "MILD_DIARRHEA": True,
    "POST_VACCINE": True,
    "DATA_MISSING": False,
    "DATA_STALE": False,
    "EMERGENCY_SEIZURE": True,
    "EMERGENCY_RESPIRATORY": True,
    "EMERGENCY_TRAUMA": True,
}

ACTION_BY_FLAG: dict[PrimaryFlagLiteral, PrimaryActionHintLiteral] = {
    "NORMAL_DAILY": "rest_observe",
    "POST_EXERCISE": "rest_observe",
    "FEVER_RESTING": "contact_vet",
    "RESP_RESTING": "contact_vet",
    "HR_RESTING_CHRONIC": "contact_vet",
    "CHRONIC_HEART_RESP": "contact_vet",
    "USER_DEVICE_CONFLICT": "contact_vet",
    "REPEATED_VOMITING": "contact_vet",
    "SENIOR_DECLINE": "contact_vet",
    "PUPPY_FEVER": "contact_vet",
    "HRV_STRESS": "rest_observe",
    "LIMPING_PAIN": "contact_vet",
    "SLOW_RECOVERY": "rest_observe",
    "MILD_DIARRHEA": "contact_vet",
    "POST_VACCINE": "rest_observe",
    "DATA_MISSING": "check_device",
    "DATA_STALE": "check_device",
    "EMERGENCY_SEIZURE": "emergency_now",
    "EMERGENCY_RESPIRATORY": "emergency_now",
    "EMERGENCY_TRAUMA": "emergency_now",
}

MISSING_DATA_USER_MAP: dict[str, str] = {
    "temperature": "体温数据暂不可用",
    "heart_rate": "心率数据暂不可用",
    "respiratory_rate": "呼吸率数据暂不可用",
    "hrv": "HRV 数据暂不可用",
    "activity": "活动数据暂不可用",
    "user_report": "用户自述信息不完整",
    "device_freshness": "设备数据可能不是最新的",
    "pet_profile": "宠物档案信息不完整",
    "other": "部分健康信息暂不可用",
}

# 叙事层级（索引越小 rank 越高）
PRIMARY_FLAG_TIERS: tuple[tuple[PrimaryFlagLiteral, ...], ...] = (
    ("EMERGENCY_SEIZURE", "EMERGENCY_RESPIRATORY", "EMERGENCY_TRAUMA"),
    ("DATA_MISSING", "DATA_STALE"),
    ("USER_DEVICE_CONFLICT",),
    (
        "FEVER_RESTING",
        "RESP_RESTING",
        "HR_RESTING_CHRONIC",
        "CHRONIC_HEART_RESP",
        "SENIOR_DECLINE",
        "PUPPY_FEVER",
        "REPEATED_VOMITING",
    ),
    ("POST_EXERCISE", "POST_VACCINE"),
    ("HRV_STRESS", "LIMPING_PAIN", "SLOW_RECOVERY", "MILD_DIARRHEA"),
    ("NORMAL_DAILY",),
)

# primaryFlag → FactSheet 字段路径（fact_index 相对路径，camelCase）
EVIDENCE_PATHS_BY_FLAG: dict[PrimaryFlagLiteral, tuple[str, ...]] = {
    "NORMAL_DAILY": (
        "healthEvidence.riskLevel",
        "vitals.activityLevel",
        "userReport.text",
    ),
    "POST_EXERCISE": (
        "vitals.temperatureC",
        "vitals.heartRateBpm",
        "context.recentExercise",
        "userReport.text",
    ),
    "FEVER_RESTING": (
        "vitals.temperatureC",
        "vitals.activityLevel",
        "userReport.energy",
        "userReport.appetite",
    ),
    "RESP_RESTING": (
        "vitals.respiratoryRateBpm",
        "vitals.activityLevel",
        "userReport.text",
        "userReport.breathingDifficulty",
    ),
    "HR_RESTING_CHRONIC": (
        "vitals.heartRateBpm",
        "profile.chronicConditions",
        "userReport.text",
    ),
    "CHRONIC_HEART_RESP": (
        "profile.chronicConditions",
        "vitals.respiratoryRateBpm",
        "profile.medications",
        "userReport.text",
    ),
    "USER_DEVICE_CONFLICT": (
        "userReport.text",
        "vitals.temperatureC",
        "device.dataQuality",
    ),
    "REPEATED_VOMITING": (
        "userReport.vomiting",
        "userReport.text",
        "userReport.appetite",
    ),
    "SENIOR_DECLINE": (
        "identity.ageMonths",
        "userReport.energy",
        "userReport.appetite",
        "profile.chronicConditions",
    ),
    "PUPPY_FEVER": (
        "identity.ageMonths",
        "vitals.temperatureC",
        "userReport.text",
    ),
    "HRV_STRESS": (
        "vitals.hrvMs",
        "userReport.text",
        "context.notes",
    ),
    "LIMPING_PAIN": (
        "userReport.limping",
        "userReport.pain",
        "userReport.text",
        "vitals.stepsToday",
    ),
    "SLOW_RECOVERY": (
        "vitals.sleepQuality",
        "vitals.hrvMs",
        "userReport.text",
    ),
    "MILD_DIARRHEA": (
        "userReport.diarrhea",
        "userReport.energy",
        "userReport.text",
    ),
    "POST_VACCINE": (
        "context.recentVaccination",
        "userReport.energy",
        "vitals.temperatureC",
    ),
    "DATA_MISSING": (
        "device.dataQuality",
        "device.warningText",
        "missingData",
    ),
    "DATA_STALE": (
        "device.dataQuality",
        "device.lastSeenAt",
        "device.warningText",
    ),
    "EMERGENCY_SEIZURE": (
        "userReport.seizure",
        "userReport.text",
    ),
    "EMERGENCY_RESPIRATORY": (
        "vitals.respiratoryRateBpm",
        "userReport.breathingDifficulty",
        "userReport.symptoms",
        "userReport.text",
    ),
    "EMERGENCY_TRAUMA": (
        "userReport.trauma",
        "userReport.text",
    ),
}
