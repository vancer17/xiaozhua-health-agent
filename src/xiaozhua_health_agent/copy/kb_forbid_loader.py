"""KB-FORBID 制品加载器。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from xiaozhua_health_agent.copy.copy_types import KbForbidBundle
from xiaozhua_health_agent.eval import merge_forbidden_patterns
from xiaozhua_health_agent.paths import default_forbidden_patterns_path


class KbForbidLoadError(Exception):
    """KB-FORBID 制品加载或校验失败。"""


def load_kb_forbid_bundle_from_json(payload: dict[str, Any]) -> KbForbidBundle:
    """从 JSON 根对象构建 ``KbForbidBundle``。

    :param payload: ``forbidden_patterns.v1.json`` 根对象。
    :type payload: dict[str, Any]
    :returns: 合并后的禁止 pattern 聚合包。
    :rtype: KbForbidBundle
    :raises KbForbidLoadError: 根结构不符合预期时抛出。
    """
    schema_raw = payload.get("schemaPatterns")
    extended_raw = payload.get("extendedPatterns")

    if not isinstance(schema_raw, list) or not all(
        isinstance(item, str) for item in schema_raw
    ):
        msg = "forbidden_patterns.v1.json 缺少 schemaPatterns 字符串数组。"
        raise KbForbidLoadError(msg)
    if not isinstance(extended_raw, list) or not all(
        isinstance(item, str) for item in extended_raw
    ):
        msg = "forbidden_patterns.v1.json 缺少 extendedPatterns 字符串数组。"
        raise KbForbidLoadError(msg)

    merged = merge_forbidden_patterns(
        schema_patterns=tuple(schema_raw),
        extended_patterns=tuple(extended_raw),
    )

    meta = payload.get("meta", {})
    bundle_version = "unknown"
    if isinstance(meta, dict):
        raw_version = meta.get("bundleVersion")
        if isinstance(raw_version, str):
            bundle_version = raw_version

    return KbForbidBundle(
        bundle_version=bundle_version,
        forbidden_patterns=merged,
    )


def load_kb_forbid_bundle(path: Path | str | None = None) -> KbForbidBundle:
    """从文件加载 KB-FORBID 制品。

    :param path: JSON 文件路径；``None`` 时使用 ``default_forbidden_patterns_path()``。
    :type path: pathlib.Path | str | None
    :returns: KB-FORBID 聚合包。
    :rtype: KbForbidBundle
    :raises KbForbidLoadError: 文件不存在或解析失败时抛出。
    """
    resolved = Path(path) if path is not None else default_forbidden_patterns_path()
    if not resolved.is_file():
        msg = f"KB-FORBID 文件不存在：{resolved}"
        raise KbForbidLoadError(msg)
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"读取 KB-FORBID 文件失败：{resolved}（{exc}）"
        raise KbForbidLoadError(msg) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"KB-FORBID JSON 解析失败：{exc.msg}"
        raise KbForbidLoadError(msg) from exc
    if not isinstance(payload, dict):
        msg = "KB-FORBID 根节点必须为对象。"
        raise KbForbidLoadError(msg)
    return load_kb_forbid_bundle_from_json(payload)
