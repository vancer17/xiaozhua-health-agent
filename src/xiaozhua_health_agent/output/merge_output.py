"""WP5 ⑤ MergeOutput — 将 ② 裁决字段与 ③ 文案草稿合并为 ``AgentOutput``。

对应 ``pipeline-design.md`` §7.1：``riskLevel`` / ``confidence`` / ``scene`` /
``missingData`` 来自 ``TriageCoreResult``；文案字段来自 ``DraftCopyJSON``；
``primaryAction`` / ``secondaryAction`` **原样**沿用草稿（深拷贝），不在此阶段
重新调用 KB-ACTION 映射。
"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from xiaozhua_health_agent.copy import DraftCopyJSON
from xiaozhua_health_agent.output.merge_types import (
    DEFAULT_OPTIONAL_SAFETY_NOTICE,
    MergeOutputError,
)
from xiaozhua_health_agent.schemas import (
    ActionItem,
    AgentOutput,
    SceneLiteral,
)
from xiaozhua_health_agent.triage import TriageCoreResult

__all__ = [
    "merge_agent_output",
    "merge_agent_output_to_alias_dict",
]

_DEFAULT_SCENE: SceneLiteral = "health_triage"


def merge_agent_output(
    *,
    triage: TriageCoreResult,
    draft: DraftCopyJSON,
    scene: SceneLiteral = _DEFAULT_SCENE,
) -> AgentOutput:
    """将锁定的分诊结论与文案草稿合并为完整 ``AgentOutput``。

    合并规则（与开发计划 WP5 §合并与兜底 对齐）：

    - **来自 ②（锁定）**：``riskLevel``、``confidence``、``missingData``
    - **来自 ③（文案）**：``title``、``summary``、``evidence``、
      ``recommendation``、``whenToSeeVet``、``safetyNotice``、
      ``primaryAction``、``secondaryAction``
    - **固定**：``scene``（默认 ``health_triage``）
    - **行动项**：``primaryAction`` / ``secondaryAction`` 对 ``draft`` 中的
      ``ActionItem`` 做深拷贝，**不**重新查 KB-ACTION

    :param triage: 步骤 ② 产出的锁定分诊结论与文案约束包。
    :type triage: TriageCoreResult
    :param draft: 步骤 ③ 产出的文案草稿（机械或 LLM，经回填后）。
    :type draft: DraftCopyJSON
    :param scene: 分诊场景；V1 固定为 ``health_triage``。
    :type scene: SceneLiteral
    :returns: 与 ``output_schema.v1`` 对齐的完整结构化输出。
    :rtype: AgentOutput
    :raises MergeOutputError: 必填免责声明缺失或 Pydantic 出站校验失败时抛出。
    """
    safety_notice = _resolve_safety_notice_for_merge(draft=draft, triage=triage)
    primary_action = _passthrough_action_item(draft.primary_action)
    secondary_action = (
        _passthrough_action_item(draft.secondary_action)
        if draft.secondary_action is not None
        else None
    )

    payload: dict[str, Any] = {
        "riskLevel": triage.final_risk_level,
        "scene": scene,
        "title": draft.title,
        "summary": draft.summary,
        "evidence": list(draft.evidence),
        "recommendation": draft.recommendation,
        "whenToSeeVet": draft.when_to_see_vet,
        "missingData": list(triage.missing_data_user),
        "confidence": triage.confidence,
        "safetyNotice": safety_notice,
        "primaryAction": primary_action.model_dump(by_alias=True, mode="json"),
        "secondaryAction": (
            secondary_action.model_dump(by_alias=True, mode="json")
            if secondary_action is not None
            else None
        ),
    }

    try:
        return AgentOutput.model_validate(payload)
    except ValidationError as exc:
        msg = f"合并后的 AgentOutput 未通过契约校验（{exc.error_count()} 项错误）。"
        raise MergeOutputError(msg) from exc


def merge_agent_output_to_alias_dict(
    *,
    triage: TriageCoreResult,
    draft: DraftCopyJSON,
    scene: SceneLiteral = _DEFAULT_SCENE,
) -> dict[str, Any]:
    """合并并导出 camelCase 键的出站 JSON 字典。

    :param triage: 步骤 ② 锁定分诊结果。
    :type triage: TriageCoreResult
    :param draft: 步骤 ③ 文案草稿。
    :type draft: DraftCopyJSON
    :param scene: 分诊场景。
    :type scene: SceneLiteral
    :returns: 与 App / 批跑 JSON 对齐的出站字典。
    :rtype: dict[str, Any]
    :raises MergeOutputError: 同 :func:`merge_agent_output`。
    """
    output = merge_agent_output(triage=triage, draft=draft, scene=scene)
    return output.model_dump(by_alias=True, mode="json")


def _passthrough_action_item(action: ActionItem) -> ActionItem:
    """深拷贝行动项，确保合并阶段不 mutate 草稿内对象。

    :param action: ③ 草稿中的主/次行动项。
    :type action: ActionItem
    :returns: 与输入语义相同的新 ``ActionItem`` 实例。
    :rtype: ActionItem
    """
    return action.model_copy(deep=True)


def _resolve_safety_notice_for_merge(
    *,
    draft: DraftCopyJSON,
    triage: TriageCoreResult,
) -> str:
    """解析出站 ``safetyNotice`` 字符串。

    优先使用 ``draft.safety_notice``；若 ② 要求免责声明但草稿为空则报错；
    若未要求且草稿为空则使用通用可选免责声明以满足 ``AgentOutput`` 最小长度。

    :param draft: 文案草稿。
    :type draft: DraftCopyJSON
    :param triage: 分诊结论（读取 ``safetyNoticeRequired``）。
    :type triage: TriageCoreResult
    :returns: 非空免责声明文本。
    :rtype: str
    :raises MergeOutputError: ``safetyNoticeRequired=true`` 但草稿为空时抛出。
    """
    stripped = draft.safety_notice.strip()
    if stripped:
        return stripped

    if triage.safety_notice_required:
        msg = (
            "safetyNoticeRequired 为 true，但 DraftCopyJSON.safetyNotice 为空；"
            "应在 ③ 阶段写入免责声明片段后再合并。"
        )
        raise MergeOutputError(msg)

    return DEFAULT_OPTIONAL_SAFETY_NOTICE
