"""WP4 ③-2 Prompt 组装（通义千问 chat messages）。

将 ``CopyTemplateResolved`` 转为窄上下文 JSON user 消息与固定 system 约束，
产出 ``QwenChatCompletionRequest``（``response_format=json_object``）。

对应 ``pipeline-design.md`` §5.3 与 ``kb-tpl-template-spec.md`` §十三。
"""

from __future__ import annotations

import json
from typing import Any, Final

from xiaozhua_health_agent.copy.copy_types import CopyTemplateResolved, ToneProfile
from xiaozhua_health_agent.copy.qwen_client import (
    QwenChatCompletionRequest,
    QwenChatMessage,
)

__all__ = [
    "DRAFT_COPY_JSON_FIELD_NAMES",
    "build_draft_chat_completion_request",
    "build_draft_prompt_user_payload",
    "build_draft_system_prompt",
]

DRAFT_COPY_JSON_FIELD_NAMES: Final[tuple[str, ...]] = (
    "title",
    "summary",
    "evidence",
    "recommendation",
    "whenToSeeVet",
    "safetyNotice",
    "primaryAction",
    "secondaryAction",
)
"""③-2 LLM 允许输出的 JSON 字段名（camelCase）。"""

_SYSTEM_PROMPT_HEADER: Final[
    str
] = """你是宠物健康分诊文案助手，负责将结构化模板包改写为面向主人的简短中文说明。

硬性规则：
1. 你不是兽医，不得确诊、不得保证治愈、不得替代面诊。
2. 只根据用户消息中的 templatePack 写作，不得编造 templatePack 中未出现的数值、时间或趋势。
3. 只输出一个 JSON 对象，字段名严格为：title, summary, evidence, recommendation, whenToSeeVet, safetyNotice, primaryAction, secondaryAction。
4. evidence 必须是字符串数组；primaryAction 为 {"label": "...", "route": "..." 或 null}；无次要行动时 secondaryAction 为 null。
5. 禁止输出 riskLevel、confidence、scene、missingData。
6. evidence 只能改写 templatePack.evidenceBullets 中的事实，不可新增数字或监测项。
7. primaryAction 与 secondaryAction 的 route（及 label）必须与 templatePack 中 primaryActionDraft / secondaryActionDraft 完全一致，不得修改 route。
"""


def build_draft_system_prompt(resolved: CopyTemplateResolved) -> str:
    """构建 ③-2 system 消息（固定规则 + 动态合规块）。

    :param resolved: 步骤 ③-1 产出的模板解析包。
    :type resolved: CopyTemplateResolved
    :returns: system 角色正文。
    :rtype: str
    """
    sections: list[str] = [_SYSTEM_PROMPT_HEADER.strip(), ""]

    tone_section = _format_tone_section(resolved.tone_profile)
    if tone_section:
        sections.append(tone_section)
        sections.append("")

    if resolved.required_mentions:
        mentions = "、".join(resolved.required_mentions)
        sections.append(
            f"必提主题（须在 title/summary/recommendation 中体现语义，可换说法）：{mentions}",
        )
        sections.append("")

    if resolved.forbidden:
        forbidden = "、".join(resolved.forbidden)
        sections.append(f"禁止表述或同义表达：{forbidden}")
        sections.append("")

    if resolved.llm_instructions.strip():
        sections.append(f"场景指令：{resolved.llm_instructions.strip()}")
        sections.append("")

    evidence_rule = _format_evidence_style_rule(
        resolved.evidence_style,
        resolved.evidence_instruction,
    )
    sections.append(evidence_rule)
    sections.append("")

    snippet = resolved.safety_notice_snippet.strip()
    if snippet:
        sections.append(
            "safetyNotice 须保留以下免责声明含义，可轻微润色但不可删除核心边界：\n"
            f"{snippet}",
        )
        sections.append("")

    sections.append(
        "emergency 场景必须体现紧迫就医导向；DATA_* 场景禁止写「目前健康正常」「一切正常」。",
    )

    return "\n".join(sections).strip()


def build_draft_prompt_user_payload(resolved: CopyTemplateResolved) -> dict[str, Any]:
    """构建窄上下文 templatePack（作为 user 消息 JSON 体）。

    :param resolved: 步骤 ③-1 产出的模板解析包。
    :type resolved: CopyTemplateResolved
    :returns: 可 ``json.dumps`` 的 templatePack 对象。
    :rtype: dict[str, Any]
    """
    primary_action = resolved.primary_action_draft.model_dump(
        by_alias=True, mode="json"
    )
    secondary_action: dict[str, Any] | None
    if resolved.secondary_action_draft is None:
        secondary_action = None
    else:
        secondary_action = resolved.secondary_action_draft.model_dump(
            by_alias=True,
            mode="json",
        )

    return {
        "templateId": resolved.template_id,
        "toneProfileId": resolved.tone_profile_id,
        "titlePattern": resolved.title_pattern,
        "summaryOutline": list(resolved.summary_outline),
        "recommendationTemplate": resolved.recommendation_template,
        "whenToSeeVetTemplate": resolved.when_to_see_vet_template,
        "filledSlots": dict(resolved.filled_slots),
        "evidenceBullets": list(resolved.evidence_bullets),
        "evidenceInstruction": resolved.evidence_instruction,
        "evidenceStyle": resolved.evidence_style,
        "primaryActionDraft": primary_action,
        "secondaryActionDraft": secondary_action,
        "safetyNoticeSnippet": resolved.safety_notice_snippet,
        "outputSchema": {
            "fields": list(DRAFT_COPY_JSON_FIELD_NAMES),
            "draftCopyJsonExample": _draft_copy_json_schema_hint(),
        },
    }


def build_draft_chat_completion_request(
    resolved: CopyTemplateResolved,
) -> QwenChatCompletionRequest:
    """组装通义千问聊天补全请求（system + user JSON templatePack）。

    :param resolved: 步骤 ③-1 产出的模板解析包。
    :type resolved: CopyTemplateResolved
    :returns: 可直接传入 ``AsyncQwenClient.create_chat_completion`` 的请求。
    :rtype: QwenChatCompletionRequest
    """
    system_content = build_draft_system_prompt(resolved)
    user_payload = build_draft_prompt_user_payload(resolved)
    user_content = json.dumps(
        {"templatePack": user_payload},
        ensure_ascii=False,
        indent=2,
    )

    return QwenChatCompletionRequest(
        messages=(
            QwenChatMessage(role="system", content=system_content),
            QwenChatMessage(
                role="user",
                content=(
                    "请根据以下 templatePack 生成 DraftCopyJSON（仅输出 JSON 对象，无其它文字）：\n"
                    f"{user_content}"
                ),
            ),
        ),
        response_format="json_object",
    )


def _format_tone_section(tone_profile: ToneProfile | None) -> str:
    """格式化语气 profile 段落。

    :param tone_profile: 可选语气配置。
    :type tone_profile: ToneProfile | None
    :returns: 段落文本；无 profile 时返回空串。
    :rtype: str
    """
    if tone_profile is None:
        return ""
    preferred = (
        "、".join(tone_profile.preferred_phrases)
        if tone_profile.preferred_phrases
        else "（无）"
    )
    avoid = (
        "、".join(tone_profile.avoid_phrases)
        if tone_profile.avoid_phrases
        else "（无）"
    )
    return f"语气（{tone_profile.tone}）：倾向用语 {preferred}；避免用语 {avoid}。"


def _format_evidence_style_rule(
    evidence_style: str,
    evidence_instruction: str | None,
) -> str:
    """格式化 evidence 改写规则说明。

    :param evidence_style: ``bullets_as_is`` 或 ``bullets_light_polish``。
    :type evidence_style: str
    :param evidence_instruction: 模板内可选补充说明。
    :type evidence_instruction: str | None
    :returns: 规则文本。
    :rtype: str
    """
    if evidence_style == "bullets_as_is":
        base = "evidence：尽量保持 evidenceBullets 原文，仅做标点微调。"
    else:
        base = "evidence：可轻度合并润色 evidenceBullets，但不得增删事实点或数字。"

    if evidence_instruction and evidence_instruction.strip():
        return f"{base} 补充：{evidence_instruction.strip()}"
    return base


def _draft_copy_json_schema_hint() -> dict[str, Any]:
    """返回 DraftCopyJSON 字段类型提示（嵌入 user JSON，非 JSON Schema 真源）。

    :returns: 字段说明字典。
    :rtype: dict[str, Any]
    """
    return {
        "title": "string",
        "summary": "string",
        "evidence": ["string"],
        "recommendation": "string",
        "whenToSeeVet": "string",
        "safetyNotice": "string",
        "primaryAction": {"label": "string", "route": "string|null"},
        "secondaryAction": "object|null",
    }
