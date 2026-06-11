"""③-1 内联规则：在模板提纲上追加情境句子（取代 overlay-snippets）。"""

from __future__ import annotations

from xiaozhua_health_agent.parse import FactSheet

_PARTIAL_DATA_APPENDIX: str = "部分监测数据可能不完整，结论请结合线下观察。"
"""``device.dataQuality=partial`` 时追加到 summaryOutline 的句子。"""


def apply_inline_summary_rules(
    *,
    summary_outline: tuple[str, ...],
    fact_sheet: FactSheet,
) -> tuple[str, ...]:
    """按 FactSheet 情境对 ``summaryOutline`` 应用内联追加规则。

    对应 ``kb-tpl-template-spec.md`` §九。

    :param summary_outline: 模板原始提纲列表。
    :type summary_outline: tuple[str, ...]
    :param fact_sheet: 事实清单。
    :type fact_sheet: FactSheet
    :returns: 可能追加句子后的新提纲元组。
    :rtype: tuple[str, ...]
    """
    lines = list(summary_outline)
    if fact_sheet.device.data_quality == "partial":
        if _PARTIAL_DATA_APPENDIX not in lines:
            lines.append(_PARTIAL_DATA_APPENDIX)
    return tuple(lines)
