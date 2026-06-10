"""DerivedFacts 阈值与配置常量（WP2）。

集中管理物种相对体温、呼吸/心率阈值与月龄分界，便于单测覆盖与日后迁入决策表 ``meta``。
"""

from __future__ import annotations

from dataclasses import dataclass

from xiaozhua_health_agent.schemas import SpeciesLiteral

# ---------------------------------------------------------------------------
# 慢病 / 品种标签
# ---------------------------------------------------------------------------

CHRONIC_HEART_CONDITION_TAGS: frozenset[str] = frozenset(
    {
        "heart_murmur_history",
        "heart_disease",
    },
)
"""计入 ``has_chronic_heart`` 的慢病标签（``brachycephalic`` 单独由 ``is_brachycephalic`` 处理）。"""

BRACHYCEPHALIC_CONDITION_TAG: str = "brachycephalic"
"""短鼻体质慢病标签。"""

BRACHYCEPHALIC_BREED_KEYWORDS: frozenset[str] = frozenset(
    {
        "pug",
        "french bulldog",
        "bulldog",
        "pekingese",
        "shih tzu",
    },
)
"""品种名（小写）命中即视为短鼻体质的参考列表。"""

# ---------------------------------------------------------------------------
# 数值阈值
# ---------------------------------------------------------------------------

DEVICE_RESTING_FEVER_THRESHOLD_DOG_C: float = 39.5
"""``device_shows_resting_fever`` 犬只安静发热设备侧阈值（°C）。"""

DEVICE_RESTING_FEVER_THRESHOLD_CAT_C: float = 39.8
"""``device_shows_resting_fever`` 猫只安静发热设备侧阈值（°C）。"""

SEVERE_RESTING_RESPIRATORY_RATE_BPM: float = 60.0
"""``severe_resting_resp`` 安静态极高呼吸率阈值（bpm）。"""

RESTING_TACHYPNEA_RESPIRATORY_RATE_BPM: float = 40.0
"""``has_resting_tachypnea`` 呼吸率兜底阈值（bpm）。"""

RESTING_TACHYCARDIA_HEART_RATE_BPM: float = 170.0
"""``has_resting_tachycardia`` 心率兜底阈值（bpm）。"""

SENIOR_AGE_MONTHS_CAT: float = 84.0
"""猫只老年月龄下限（含）。"""

SENIOR_AGE_MONTHS_DOG: float = 96.0
"""犬只老年月龄下限（含）。"""

PUPPY_KITTEN_MAX_AGE_MONTHS: float = 6.0
"""幼宠月龄上限（含）。"""


@dataclass(frozen=True, slots=True)
class DerivedFactsThresholds:
    """DerivedFacts 计算所需的全部可调阈值快照。"""

    device_resting_fever_dog_c: float = DEVICE_RESTING_FEVER_THRESHOLD_DOG_C
    device_resting_fever_cat_c: float = DEVICE_RESTING_FEVER_THRESHOLD_CAT_C
    severe_resting_resp_bpm: float = SEVERE_RESTING_RESPIRATORY_RATE_BPM
    resting_tachypnea_rr_bpm: float = RESTING_TACHYPNEA_RESPIRATORY_RATE_BPM
    resting_tachycardia_hr_bpm: float = RESTING_TACHYCARDIA_HEART_RATE_BPM
    senior_age_months_cat: float = SENIOR_AGE_MONTHS_CAT
    senior_age_months_dog: float = SENIOR_AGE_MONTHS_DOG
    puppy_kitten_max_age_months: float = PUPPY_KITTEN_MAX_AGE_MONTHS


DEFAULT_DERIVED_FACTS_THRESHOLDS: DerivedFactsThresholds = DerivedFactsThresholds()
"""默认阈值单例。"""


def device_resting_fever_threshold_c(
    species: SpeciesLiteral,
    *,
    thresholds: DerivedFactsThresholds = DEFAULT_DERIVED_FACTS_THRESHOLDS,
) -> float | None:
    """按物种返回安静设备发热判定阈值。

    :param species: 宠物物种。
    :type species: SpeciesLiteral
    :param thresholds: 阈值配置快照。
    :type thresholds: DerivedFactsThresholds
    :returns: 阈值（°C）；``unknown`` 物种时 ``None``（不判定发热）。
    :rtype: float | None
    """
    if species == "dog":
        return thresholds.device_resting_fever_dog_c
    if species == "cat":
        return thresholds.device_resting_fever_cat_c
    return None


def senior_age_threshold_months(
    species: SpeciesLiteral,
    *,
    thresholds: DerivedFactsThresholds = DEFAULT_DERIVED_FACTS_THRESHOLDS,
) -> float | None:
    """按物种返回老年月龄下限。

    :param species: 宠物物种。
    :type species: SpeciesLiteral
    :param thresholds: 阈值配置快照。
    :type thresholds: DerivedFactsThresholds
    :returns: 月龄下限；``unknown`` 时 ``None``。
    :rtype: float | None
    """
    if species == "dog":
        return thresholds.senior_age_months_dog
    if species == "cat":
        return thresholds.senior_age_months_cat
    return None
