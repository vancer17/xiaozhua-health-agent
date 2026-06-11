"""WP4 ③-2 LLM 响应解析与文案草稿回填。

从通义千问（或其它 LLM）返回的文本中提取 JSON，按 ``CopyTemplateResolved`` 锁定字段
回填 ``primaryAction`` / ``safetyNotice`` / ``evidence``，产出 ``DraftCopyJSON``。

对应 ``pipeline-design.md`` §5.3、§6.1 与 ``kb-tpl-template-spec.md`` §14.1。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final, TypeAlias

from pydantic import ValidationError

from xiaozhua_health_agent.copy.copy_types import CopyTemplateResolved
from xiaozhua_health_agent.copy.draft_types import DraftCopyJSON

__all__ = [
    "DraftParseError",
    "DraftParseResult",
    "DraftParseWarning",
    "DraftParseWarningCode",
    "DraftParseWarningCodeLiteral",
    "backfill_draft_payload",
    "extract_json_object_text",
    "parse_draft_copy_from_model_text",
    "parse_json_object_from_text",
]

DraftParseWarningCodeLiteral: TypeAlias = str

_JSON_FENCE_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"```(?:json)?\s*([\s\S]*?)\s*```",
    re.IGNORECASE,
)
"""Markdown 围栏代码块提取（贪婪非跨块）。"""

_STRIPPED_RULING_FIELD_NAMES: Final[frozenset[str]] = frozenset(
    {
        "riskLevel",
        "risk_level",
        "confidence",
        "scene",
        "missingData",
        "missing_data",
    },
)
"""LLM 偶发输出的医学裁决字段（解析时丢弃）。"""


class DraftParseWarningCode(StrEnum):
    """文案草稿解析阶段的非致命警告码。"""

    STRIPPED_RULING_FIELDS = "STRIPPED_RULING_FIELDS"
    PRIMARY_ACTION_BACKFILLED = "PRIMARY_ACTION_BACKFILLED"
    PRIMARY_ACTION_ROUTE_CORRECTED = "PRIMARY_ACTION_ROUTE_CORRECTED"
    PRIMARY_ACTION_LABEL_CORRECTED = "PRIMARY_ACTION_LABEL_CORRECTED"
    SECONDARY_ACTION_BACKFILLED = "SECONDARY_ACTION_BACKFILLED"
    SECONDARY_ACTION_ROUTE_CORRECTED = "SECONDARY_ACTION_ROUTE_CORRECTED"
    SECONDARY_ACTION_LABEL_CORRECTED = "SECONDARY_ACTION_LABEL_CORRECTED"
    SECONDARY_ACTION_PRESENCE_CORRECTED = "SECONDARY_ACTION_PRESENCE_CORRECTED"
    SAFETY_NOTICE_BACKFILLED = "SAFETY_NOTICE_BACKFILLED"
    EVIDENCE_BACKFILLED = "EVIDENCE_BACKFILLED"
    EVIDENCE_NORMALIZED = "EVIDENCE_NORMALIZED"
    JSON_EXTRACTED_FROM_FENCE = "JSON_EXTRACTED_FROM_FENCE"
    JSON_EXTRACTED_BY_BRACE_SCAN = "JSON_EXTRACTED_BY_BRACE_SCAN"


@dataclass(frozen=True, slots=True)
class DraftParseWarning:
    """单条解析警告（供批跑报告与 WP5 审计）。

    :ivar code: 警告码。
    :vartype code: DraftParseWarningCode
    :ivar message: 人类可读说明。
    :vartype message: str
    :ivar field: 关联字段名（若有）。
    :vartype field: str | None
    """

    code: DraftParseWarningCode
    message: str
    field: str | None = None


@dataclass(frozen=True, slots=True)
class DraftParseResult:
    """``DraftCopyJSON`` 解析成功结果。

    :ivar draft: 校验后的文案草稿。
    :vartype draft: DraftCopyJSON
    :ivar warnings: 回填或规范化产生的警告列表。
    :vartype warnings: tuple[DraftParseWarning, ...]
    :ivar stripped_ruling_fields: 从原始 JSON 中移除的裁决字段名。
    :vartype stripped_ruling_fields: tuple[str, ...]
    """

    draft: DraftCopyJSON
    warnings: tuple[DraftParseWarning, ...]
    stripped_ruling_fields: tuple[str, ...]


class DraftParseError(Exception):
    """LLM 响应无法解析为合法 ``DraftCopyJSON``。

    :ivar message: 错误说明。
    :vartype message: str
    :ivar raw_excerpt: 原始文本摘要（便于日志）。
    :vartype raw_excerpt: str | None
    """

    def __init__(
        self,
        message: str,
        *,
        raw_excerpt: str | None = None,
    ) -> None:
        """构造解析错误。

        :param message: 人类可读错误说明。
        :type message: str
        :param raw_excerpt: 可选原始文本截断摘要。
        :type raw_excerpt: str | None
        """
        super().__init__(message)
        self.raw_excerpt = raw_excerpt


def extract_json_object_text(
    raw_text: str,
) -> tuple[str, tuple[DraftParseWarning, ...]]:
    """从模型原始正文中提取 JSON 对象字符串。

    处理顺序：

    1. 去除首尾空白；
    2. 若存在 Markdown `` ```json `` 围栏，取围栏内文本；
    3. 若以 ``{`` 开头尝试整体解析；
    4. 否则扫描首个平衡 ``{ ... }`` 子串。

    :param raw_text: LLM ``message.content`` 原文。
    :type raw_text: str
    :returns: 提取出的 JSON 文本与提取过程警告。
    :rtype: tuple[str, tuple[DraftParseWarning, ...]]
    :raises DraftParseError: 正文为空或无法定位 JSON 对象时抛出。
    """
    if not raw_text or not raw_text.strip():
        msg = "模型响应正文为空，无法提取 JSON。"
        raise DraftParseError(msg, raw_excerpt=raw_text)

    warnings: list[DraftParseWarning] = []
    stripped = raw_text.strip()

    fence_match = _JSON_FENCE_PATTERN.search(stripped)
    if fence_match is not None:
        inner = fence_match.group(1).strip()
        if inner:
            warnings.append(
                DraftParseWarning(
                    code=DraftParseWarningCode.JSON_EXTRACTED_FROM_FENCE,
                    message="从 Markdown 代码围栏中提取 JSON。",
                ),
            )
            return inner, tuple(warnings)

    if stripped.startswith("{"):
        return stripped, tuple(warnings)

    brace_extracted = _extract_first_balanced_json_object(stripped)
    if brace_extracted is not None:
        warnings.append(
            DraftParseWarning(
                code=DraftParseWarningCode.JSON_EXTRACTED_BY_BRACE_SCAN,
                message="通过花括号扫描定位 JSON 对象子串。",
            ),
        )
        return brace_extracted, tuple(warnings)

    excerpt = _truncate_excerpt(stripped)
    msg = "无法在模型响应中定位 JSON 对象。"
    raise DraftParseError(msg, raw_excerpt=excerpt)


def parse_json_object_from_text(raw_text: str) -> dict[str, Any]:
    """提取并 ``json.loads`` 为对象字典。

    :param raw_text: LLM 原始正文。
    :type raw_text: str
    :returns: 解析后的 JSON 对象（顶层必须为 dict）。
    :rtype: dict[str, Any]
    :raises DraftParseError: 提取失败、JSON 语法错误或根节点非对象时抛出。
    """
    json_text, _warnings = extract_json_object_text(raw_text)
    try:
        parsed: Any = json.loads(json_text)
    except json.JSONDecodeError as exc:
        excerpt = _truncate_excerpt(json_text)
        msg = f"JSON 语法错误：{exc.msg}（位置 {exc.pos}）。"
        raise DraftParseError(msg, raw_excerpt=excerpt) from exc

    if not isinstance(parsed, dict):
        msg = f"文案 JSON 根节点必须为对象，实际为 {type(parsed).__name__}。"
        raise DraftParseError(msg, raw_excerpt=_truncate_excerpt(json_text))
    return parsed


def backfill_draft_payload(
    payload: dict[str, Any],
    resolved: CopyTemplateResolved,
    *,
    enforce_locked_actions: bool = True,
    lock_action_label: bool = True,
) -> tuple[dict[str, Any], tuple[DraftParseWarning, ...]]:
    """按 ③-1 锁定字段回填 LLM 草稿 JSON。

    回填策略（与 ``pipeline-design.md`` §7.1 对齐）：

    - 移除 ``riskLevel`` / ``confidence`` / ``scene`` / ``missingData``；
    - ``primaryAction`` 缺失或 ``label`` 空 → ``primary_action_draft``；
    - ``secondaryAction`` 缺失 → ``secondary_action_draft`` 或 ``null``；
    - ``primaryAction`` / ``secondaryAction`` 的 ``route``（及可选 ``label``）与 draft 不一致
      且 ``enforce_locked_actions=True`` 时整对象回写 draft；
    - ``safetyNotice`` 空且 ``safety_notice_snippet`` 非空 → 写入 snippet；
    - ``evidence`` 非字符串列表 → 降级为 ``evidence_bullets`` 原文。

    :param payload: LLM 解析后的对象字典（将被浅拷贝修改）。
    :type payload: dict[str, Any]
    :param resolved: 步骤 ③-1 产出的模板解析包。
    :type resolved: CopyTemplateResolved
    :param enforce_locked_actions: 是否强制回写与 draft 不一致的主/次行动。
    :type enforce_locked_actions: bool
    :param lock_action_label: 回写/检测时是否同时锁定 ``label``。
    :type lock_action_label: bool
    :returns: 回填后的 payload 与警告列表。
    :rtype: tuple[dict[str, Any], tuple[DraftParseWarning, ...]]
    """
    working: dict[str, Any] = dict(payload)
    warnings: list[DraftParseWarning] = []

    stripped_fields = _strip_ruling_fields(working)
    if stripped_fields:
        warnings.append(
            DraftParseWarning(
                code=DraftParseWarningCode.STRIPPED_RULING_FIELDS,
                message=f"已丢弃模型输出的裁决字段：{', '.join(stripped_fields)}。",
            ),
        )

    if _needs_primary_action_backfill(working):
        working["primaryAction"] = resolved.primary_action_draft.model_dump(
            by_alias=True,
            mode="json",
        )
        warnings.append(
            DraftParseWarning(
                code=DraftParseWarningCode.PRIMARY_ACTION_BACKFILLED,
                message="primaryAction 由 ③-1 草稿回填。",
                field="primaryAction",
            ),
        )

    if "secondaryAction" not in working or working.get("secondaryAction") is None:
        if resolved.secondary_action_draft is not None:
            working["secondaryAction"] = resolved.secondary_action_draft.model_dump(
                by_alias=True,
                mode="json",
            )
            warnings.append(
                DraftParseWarning(
                    code=DraftParseWarningCode.SECONDARY_ACTION_BACKFILLED,
                    message="secondaryAction 由 ③-1 草稿回填。",
                    field="secondaryAction",
                ),
            )
        else:
            working["secondaryAction"] = None

    safety_snippet = resolved.safety_notice_snippet.strip()
    current_safety = working.get("safetyNotice", working.get("safety_notice", ""))
    if safety_snippet and (
        not isinstance(current_safety, str) or not current_safety.strip()
    ):
        working["safetyNotice"] = safety_snippet
        warnings.append(
            DraftParseWarning(
                code=DraftParseWarningCode.SAFETY_NOTICE_BACKFILLED,
                message="safetyNotice 由免责声明片段回填。",
                field="safetyNotice",
            ),
        )

    evidence_value = working.get("evidence")
    normalized_evidence, evidence_warnings = _normalize_evidence_field(
        evidence_value,
        fallback_bullets=resolved.evidence_bullets,
    )
    working["evidence"] = normalized_evidence
    warnings.extend(evidence_warnings)

    from xiaozhua_health_agent.copy.action_lock_enforcer import (
        ActionLockOptions,
        enforce_locked_actions as apply_action_lock,
    )

    lock_options = ActionLockOptions(
        enforce=enforce_locked_actions,
        lock_label=lock_action_label,
    )
    working, lock_warnings = apply_action_lock(
        working,
        resolved,
        options=lock_options,
    )
    warnings.extend(lock_warnings)

    return working, tuple(warnings)


def parse_draft_copy_from_model_text(
    raw_text: str,
    *,
    resolved: CopyTemplateResolved,
    enforce_locked_actions: bool = True,
    lock_action_label: bool = True,
) -> DraftParseResult:
    """将 LLM 原始正文解析为 ``DraftCopyJSON``（提取 JSON + 回填 + Pydantic 校验）。

    :param raw_text: 通义千问 ``QwenChatCompletionResponse.content``。
    :type raw_text: str
    :param resolved: 同次请求的 ``CopyTemplateResolved``（回填真源）。
    :type resolved: CopyTemplateResolved
    :param enforce_locked_actions: 是否强制回写与 draft 不一致的主/次行动 ``route``/``label``。
    :type enforce_locked_actions: bool
    :param lock_action_label: 是否同时锁定 ``label``。
    :type lock_action_label: bool
    :returns: 校验后的草稿与警告。
    :rtype: DraftParseResult
    :raises DraftParseError: JSON 提取/语法失败，或字段校验仍不通过时抛出。
    """
    json_text, extract_warnings = extract_json_object_text(raw_text)
    try:
        payload: dict[str, Any] = json.loads(json_text)
    except json.JSONDecodeError as exc:
        msg = f"JSON 语法错误：{exc.msg}（位置 {exc.pos}）。"
        raise DraftParseError(msg, raw_excerpt=_truncate_excerpt(json_text)) from exc

    if not isinstance(payload, dict):
        msg = f"文案 JSON 根节点必须为对象，实际为 {type(payload).__name__}。"
        raise DraftParseError(msg, raw_excerpt=_truncate_excerpt(json_text))

    stripped_fields = _strip_ruling_fields(payload)
    backfilled, backfill_warnings = backfill_draft_payload(
        payload,
        resolved,
        enforce_locked_actions=enforce_locked_actions,
        lock_action_label=lock_action_label,
    )

    all_warnings: list[DraftParseWarning] = [
        *extract_warnings,
        *backfill_warnings,
    ]
    if stripped_fields and not any(
        warning.code == DraftParseWarningCode.STRIPPED_RULING_FIELDS
        for warning in backfill_warnings
    ):
        all_warnings.insert(
            0,
            DraftParseWarning(
                code=DraftParseWarningCode.STRIPPED_RULING_FIELDS,
                message=f"已丢弃模型输出的裁决字段：{', '.join(stripped_fields)}。",
            ),
        )

    try:
        draft = DraftCopyJSON.from_alias_dict(backfilled)
    except ValidationError as exc:
        excerpt = _truncate_excerpt(json.dumps(backfilled, ensure_ascii=False))
        msg = f"DraftCopyJSON 字段校验失败：{exc.error_count()} 项错误。"
        raise DraftParseError(msg, raw_excerpt=excerpt) from exc

    return DraftParseResult(
        draft=draft,
        warnings=tuple(all_warnings),
        stripped_ruling_fields=stripped_fields,
    )


def _strip_ruling_fields(payload: dict[str, Any]) -> tuple[str, ...]:
    """从 payload 中移除医学裁决字段并返回被移除的键名。

    :param payload: 可变文案 JSON 对象。
    :type payload: dict[str, Any]
    :returns: 被移除的字段名（保持发现顺序）。
    :rtype: tuple[str, ...]
    """
    removed: list[str] = []
    for key in list(payload.keys()):
        if key in _STRIPPED_RULING_FIELD_NAMES:
            del payload[key]
            removed.append(key)
    return tuple(removed)


def _needs_primary_action_backfill(payload: dict[str, Any]) -> bool:
    """判断 ``primaryAction`` 是否需要由 ③-1 草稿回填。

    :param payload: 文案 JSON 对象。
    :type payload: dict[str, Any]
    :returns: 缺失或 label 无效时返回 ``True``。
    :rtype: bool
    """
    action_raw = payload.get("primaryAction", payload.get("primary_action"))
    if action_raw is None:
        return True
    if not isinstance(action_raw, dict):
        return True
    label = action_raw.get("label")
    return not isinstance(label, str) or not label.strip()


def _normalize_evidence_field(
    evidence_value: Any,
    *,
    fallback_bullets: tuple[str, ...],
) -> tuple[list[str], list[DraftParseWarning]]:
    """规范化 ``evidence`` 字段为字符串列表。

    :param evidence_value: LLM 输出的 evidence 原始值。
    :type evidence_value: Any
    :param fallback_bullets: ② 产出的证据 bullets。
    :type fallback_bullets: tuple[str, ...]
    :returns: 规范化列表与警告。
    :rtype: tuple[list[str], list[DraftParseWarning]]
    """
    warnings: list[DraftParseWarning] = []

    if evidence_value is None:
        if fallback_bullets:
            warnings.append(
                DraftParseWarning(
                    code=DraftParseWarningCode.EVIDENCE_BACKFILLED,
                    message="evidence 缺失，使用 evidenceBullets 原文。",
                    field="evidence",
                ),
            )
        return list(fallback_bullets), warnings

    if isinstance(evidence_value, str):
        stripped = evidence_value.strip()
        if stripped:
            warnings.append(
                DraftParseWarning(
                    code=DraftParseWarningCode.EVIDENCE_NORMALIZED,
                    message="evidence 单字符串已规范为单元素列表。",
                    field="evidence",
                ),
            )
            return [stripped], warnings
        if fallback_bullets:
            warnings.append(
                DraftParseWarning(
                    code=DraftParseWarningCode.EVIDENCE_BACKFILLED,
                    message="evidence 为空字符串，使用 evidenceBullets 原文。",
                    field="evidence",
                ),
            )
        return list(fallback_bullets), warnings

    if not isinstance(evidence_value, list):
        warnings.append(
            DraftParseWarning(
                code=DraftParseWarningCode.EVIDENCE_BACKFILLED,
                message=(
                    f"evidence 类型非法（{type(evidence_value).__name__}），"
                    "使用 evidenceBullets 原文。"
                ),
                field="evidence",
            ),
        )
        return list(fallback_bullets), warnings

    normalized: list[str] = []
    has_invalid_element = False
    for index, item in enumerate(evidence_value):
        if not isinstance(item, str):
            has_invalid_element = True
            continue
        stripped = item.strip()
        if not stripped:
            has_invalid_element = True
            continue
        normalized.append(stripped)

    if has_invalid_element or not normalized:
        warnings.append(
            DraftParseWarning(
                code=DraftParseWarningCode.EVIDENCE_BACKFILLED,
                message="evidence 列表含非法或空元素，使用 evidenceBullets 原文。",
                field="evidence",
            ),
        )
        return list(fallback_bullets), warnings

    return normalized, warnings


def _extract_first_balanced_json_object(text: str) -> str | None:
    """扫描文本中首个花括号平衡的 JSON 对象子串。

    :param text: 待扫描文本。
    :type text: str
    :returns: 子串或 ``None``。
    :rtype: str | None
    """
    start = text.find("{")
    if start < 0:
        return None

    depth = 0
    in_string = False
    escape = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _truncate_excerpt(text: str, *, max_length: int = 240) -> str:
    """截断文本用于错误摘要。

    :param text: 原始文本。
    :type text: str
    :param max_length: 最大长度。
    :type max_length: int
    :returns: 截断后的摘要。
    :rtype: str
    """
    stripped = text.strip()
    if len(stripped) <= max_length:
        return stripped
    return stripped[:max_length] + "…"
