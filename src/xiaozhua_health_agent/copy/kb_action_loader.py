"""KB-ACTION 制品加载器。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from xiaozhua_health_agent.copy.copy_types import ActionMappingEntry, KbActionBundle
from xiaozhua_health_agent.paths import default_kb_action_path


class KbActionLoadError(Exception):
    """KB-ACTION 制品加载或校验失败。"""


def load_kb_action_bundle_from_json(payload: dict[str, Any]) -> KbActionBundle:
    """从 JSON 根对象构建 ``KbActionBundle``。

    :param payload: ``actions.v1.json`` 根对象。
    :type payload: dict[str, Any]
    :returns: 校验后的 KB-ACTION 聚合包。
    :rtype: KbActionBundle
    :raises KbActionLoadError: 根结构不符合预期时抛出。
    :raises pydantic.ValidationError: 字段类型不符合模型时由 Pydantic 抛出。
    """
    actions_raw = payload.get("actions")
    secondary_raw = payload.get("secondaryActions")
    by_flag_raw = payload.get("secondaryByPrimaryFlag")

    if not isinstance(actions_raw, dict):
        msg = "actions.v1.json 缺少 actions 对象。"
        raise KbActionLoadError(msg)
    if not isinstance(secondary_raw, dict):
        msg = "actions.v1.json 缺少 secondaryActions 对象。"
        raise KbActionLoadError(msg)
    if not isinstance(by_flag_raw, dict):
        msg = "actions.v1.json 缺少 secondaryByPrimaryFlag 对象。"
        raise KbActionLoadError(msg)

    actions: dict[str, ActionMappingEntry] = {}
    for hint, entry_raw in actions_raw.items():
        if not isinstance(entry_raw, dict):
            msg = f"actions[{hint!r}] 必须为对象。"
            raise KbActionLoadError(msg)
        actions[hint] = ActionMappingEntry.model_validate(entry_raw)

    secondary_actions: dict[str, ActionMappingEntry] = {}
    for action_id, entry_raw in secondary_raw.items():
        if not isinstance(entry_raw, dict):
            msg = f"secondaryActions[{action_id!r}] 必须为对象。"
            raise KbActionLoadError(msg)
        secondary_actions[action_id] = ActionMappingEntry.model_validate(entry_raw)

    secondary_by_flag: dict[str, str] = {}
    for flag, action_id in by_flag_raw.items():
        if not isinstance(flag, str) or not isinstance(action_id, str):
            msg = "secondaryByPrimaryFlag 键值必须均为字符串。"
            raise KbActionLoadError(msg)
        secondary_by_flag[flag] = action_id

    meta = payload.get("meta", {})
    bundle_version = "unknown"
    if isinstance(meta, dict):
        raw_version = meta.get("bundleVersion")
        if isinstance(raw_version, str):
            bundle_version = raw_version

    return KbActionBundle(
        bundle_version=bundle_version,
        actions=actions,
        secondary_actions=secondary_actions,
        secondary_by_primary_flag=secondary_by_flag,
    )


def load_kb_action_bundle(path: Path | str | None = None) -> KbActionBundle:
    """从文件加载 KB-ACTION 制品。

    :param path: JSON 文件路径；``None`` 时使用 ``default_kb_action_path()``。
    :type path: pathlib.Path | str | None
    :returns: KB-ACTION 聚合包。
    :rtype: KbActionBundle
    :raises KbActionLoadError: 文件不存在或解析失败时抛出。
    """
    resolved = Path(path) if path is not None else default_kb_action_path()
    if not resolved.is_file():
        msg = f"KB-ACTION 文件不存在：{resolved}"
        raise KbActionLoadError(msg)
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"读取 KB-ACTION 文件失败：{resolved}（{exc}）"
        raise KbActionLoadError(msg) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"KB-ACTION JSON 解析失败：{exc.msg}"
        raise KbActionLoadError(msg) from exc
    if not isinstance(payload, dict):
        msg = "KB-ACTION 根节点必须为对象。"
        raise KbActionLoadError(msg)
    return load_kb_action_bundle_from_json(payload)
