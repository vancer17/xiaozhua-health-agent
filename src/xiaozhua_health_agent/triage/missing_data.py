"""missingDataUser 翻译（WP3 postProcess）。"""

from __future__ import annotations

from xiaozhua_health_agent.parse import FactSheet
from xiaozhua_health_agent.triage.policy_data import MISSING_DATA_USER_MAP


def translate_missing_data(fact_sheet: FactSheet) -> tuple[str, ...]:
    """将 ``missingData`` 枚举翻译为用户可读说明。

    :param fact_sheet: 客观事实清单。
    :type fact_sheet: FactSheet
    :returns: 去重保序的用户可读缺失说明。
    :rtype: tuple[str, ...]
    """
    if not fact_sheet.missing_data:
        return ()
    seen: set[str] = set()
    result: list[str] = []
    for item in fact_sheet.missing_data:
        text = MISSING_DATA_USER_MAP.get(item, f"{item} 数据暂不可用")
        if text not in seen:
            seen.add(text)
            result.append(text)
    return tuple(result)
