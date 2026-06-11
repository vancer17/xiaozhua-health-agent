"""``/intelligent`` 占位静态文案模板（方案 A）。

不含医学裁决逻辑；文案为通用引导语，避免编造具体体征数值。
"""

from __future__ import annotations

from typing import Final

__all__ = [
    "DEFAULT_SUGGESTED_PROMPTS",
    "PLACEHOLDER_ASSISTANT_GREETING",
    "PLACEHOLDER_ASSISTANT_GUIDANCE",
    "PLACEHOLDER_SYSTEM_NOTICE",
    "build_placeholder_messages",
]

PLACEHOLDER_SYSTEM_NOTICE: Final[str] = (
    "当前为智能对话占位模式：回复为固定模板，未执行健康分诊分析。"
    "如需查看风险结论，请使用「健康分诊」入口（/health）。"
)
"""``system`` 角色占位说明。"""

PLACEHOLDER_ASSISTANT_GREETING: Final[str] = (
    "你好，我是小爪健康助手（对话占位）。"
    "你可以描述宠物的症状或选择下方快捷问题；"
    "完整健康评估请前往健康分诊卡片。"
)
"""``assistant`` 首条欢迎语。"""

PLACEHOLDER_ASSISTANT_GUIDANCE: Final[str] = (
    "温馨提示：本对话尚未连接真实分诊引擎，请勿仅凭此处内容判断病情。"
    "若宠物出现呼吸困难、抽搐、持续呕吐等紧急情况，请立即联系兽医。"
)
"""``assistant`` 第二条安全引导语。"""

DEFAULT_SUGGESTED_PROMPTS: Final[tuple[str, ...]] = (
    "今天精神状态怎么样？",
    "有没有呕吐或腹泻？",
    "项圈数据看起来正常吗？",
    "什么情况下需要去看兽医？",
)
"""入口快捷提问建议（静态）。"""


def build_placeholder_messages(
    *,
    pet_name: str | None,
) -> tuple[str, str]:
    """根据可选宠物名生成两条 ``assistant`` 占位正文（同步纯函数）。

    :param pet_name: 入参校验通过时的宠物昵称；``None`` 时使用通用称呼。
    :type pet_name: str | None
    :returns: ``(greeting, guidance)`` 二元组。
    :rtype: tuple[str, str]
    """
    if pet_name:
        greeting = (
            f"你好，我是小爪健康助手（对话占位）。"
            f"正在为你和{pet_name}提供对话入口演示；"
            f"完整健康评估请前往健康分诊卡片。"
        )
    else:
        greeting = PLACEHOLDER_ASSISTANT_GREETING

    return greeting, PLACEHOLDER_ASSISTANT_GUIDANCE
