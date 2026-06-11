"""WP4 ③-2 文案生成中间类型定义。

``DraftCopyJSON`` 与 ``schemas.AgentOutput`` 的文案字段子集对齐（camelCase alias），
不含 ``riskLevel`` / ``confidence`` / ``scene`` / ``missingData``（由 WP5 从 ② 合并）。

对应 ``pipeline-design.md`` §5.3 与 ``kb-tpl-template-spec.md`` §14.1。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from xiaozhua_health_agent.schemas import ActionItem

__all__ = [
    "DraftCopyJSON",
]


class DraftCopyJSON(BaseModel):
    """步骤 ③-2 产出的文案草稿 JSON（可重试；不含医学裁决字段）。

    字段名与 ``output_schema.v1`` / ``AgentOutput`` 文案部分一致，便于 WP5 直接合并。
    ``safetyNotice`` 在 ``safetyNoticeRequired=false`` 时允许为空串；完整出站由 WP5 校验。

    :ivar title: 卡片短标题。
    :vartype title: str
    :ivar summary: 面向用户的风险解释摘要。
    :vartype summary: str
    :ivar evidence: 可核对证据列表；事实须来自 ② ``evidenceBullets``。
    :vartype evidence: list[str]
    :ivar recommendation: 建议的下一步行动。
    :vartype recommendation: str
    :ivar when_to_see_vet: 何时必须就医的升级条件。
    :vartype when_to_see_vet: str
    :ivar safety_notice: 医疗安全边界声明；未要求时可空。
    :vartype safety_notice: str
    :ivar primary_action: 首要行动入口。
    :vartype primary_action: ActionItem
    :ivar secondary_action: 可选次要行动。
    :vartype secondary_action: ActionItem | None
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    title: str = Field(
        min_length=1,
        description="卡片短标题，概括当前风险与主题。",
    )
    summary: str = Field(
        min_length=1,
        description="面向用户的风险解释摘要，不得编造未提供事实。",
    )
    evidence: list[str] = Field(
        description="可核对证据列表，每条应为简短事实句。",
    )
    recommendation: str = Field(
        min_length=1,
        description="建议的下一步行动（观察、休息、联系兽医等）。",
    )
    when_to_see_vet: str = Field(
        alias="whenToSeeVet",
        min_length=1,
        description="何时必须就医的明确升级条件。",
    )
    safety_notice: str = Field(
        alias="safetyNotice",
        default="",
        description="医疗安全边界声明；safetyNoticeRequired=false 时可为空串。",
    )
    primary_action: ActionItem = Field(
        alias="primaryAction",
        description="首要行动入口，与 riskLevel 匹配（label/route 由 ③-1 草稿回填）。",
    )
    secondary_action: ActionItem | None = Field(
        default=None,
        alias="secondaryAction",
        description="可选次要行动，如检查设备或记录症状。",
    )

    @field_validator("evidence", mode="before")
    @classmethod
    def _normalize_evidence(cls, value: object) -> list[str]:
        """将 evidence 规范为非空字符串列表（允许空列表）。

        :param value: 原始输入（列表或单字符串）。
        :type value: object
        :returns: 规范化后的证据字符串列表。
        :rtype: list[str]
        :raises TypeError: 元素非字符串时抛出。
        :raises ValueError: 列表中含空字符串时抛出。
        """
        if value is None:
            return []
        if isinstance(value, str):
            stripped = value.strip()
            return [stripped] if stripped else []
        if not isinstance(value, list):
            msg = "evidence 必须为字符串列表。"
            raise TypeError(msg)
        normalized: list[str] = []
        for index, item in enumerate(value):
            if not isinstance(item, str):
                msg = f"evidence[{index}] 必须为字符串。"
                raise TypeError(msg)
            stripped = item.strip()
            if not stripped:
                msg = f"evidence[{index}] 不能为空字符串。"
                raise ValueError(msg)
            normalized.append(stripped)
        return normalized

    def to_alias_dict(self) -> dict[str, Any]:
        """导出为 camelCase 键的字典（与 App / LLM JSON 输出对齐）。

        :returns: 使用字段 alias 的序列化字典；``None`` 的 ``secondaryAction`` 保留为 ``null``。
        :rtype: dict[str, Any]
        """
        return self.model_dump(by_alias=True, mode="json")

    @classmethod
    def from_alias_dict(cls, payload: dict[str, Any]) -> DraftCopyJSON:
        """从 camelCase 键的字典解析（LLM / API 响应入口）。

        :param payload: 含 ``title``、``summary``、``evidence`` 等键的对象。
        :type payload: dict[str, Any]
        :returns: 校验后的文案草稿模型。
        :rtype: DraftCopyJSON
        :raises pydantic.ValidationError: 字段缺失或类型不符时由 Pydantic 抛出。
        """
        return cls.model_validate(payload)
