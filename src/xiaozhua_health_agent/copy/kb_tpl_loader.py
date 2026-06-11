"""KB-TPL 制品加载器（templates / slots / fallback / tone / safety-notices）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from xiaozhua_health_agent.copy.copy_types import (
    FallbackTemplateEntry,
    KbTplBundle,
    SafetyNoticeRule,
    SlotDefinition,
    TemplateEntry,
    ToneProfile,
)
from xiaozhua_health_agent.paths import default_kb_tpl_config_dir


class KbTplLoadError(Exception):
    """KB-TPL 制品加载或校验失败。"""


def load_kb_tpl_bundle_from_json(
    *,
    templates_payload: dict[str, Any],
    slots_payload: dict[str, Any],
    fallback_payload: dict[str, Any],
    tone_payload: dict[str, Any],
    safety_payload: dict[str, Any],
) -> KbTplBundle:
    """从已解析的 JSON 对象构建 ``KbTplBundle``。

    :param templates_payload: ``templates.v1.json`` 根对象。
    :type templates_payload: dict[str, Any]
    :param slots_payload: ``slots.v1.json`` 根对象。
    :type slots_payload: dict[str, Any]
    :param fallback_payload: ``fallback-by-risk.v1.json`` 根对象。
    :type fallback_payload: dict[str, Any]
    :param tone_payload: ``tone-by-risk.v1.json`` 根对象。
    :type tone_payload: dict[str, Any]
    :param safety_payload: ``safety-notices.v1.json`` 根对象。
    :type safety_payload: dict[str, Any]
    :returns: 校验后的 KB-TPL 聚合包。
    :rtype: KbTplBundle
    :raises KbTplLoadError: 根结构不符合预期时抛出。
    :raises pydantic.ValidationError: 字段类型不符合模型时由 Pydantic 抛出。
    """
    templates_raw = templates_payload.get("templates")
    slots_raw = slots_payload.get("slots")
    fallbacks_raw = fallback_payload.get("fallbacks")
    profiles_raw = tone_payload.get("profiles")
    snippets_raw = safety_payload.get("snippets")
    rules_raw = safety_payload.get("resolveRules")

    if not isinstance(templates_raw, dict):
        msg = "templates.v1.json 缺少 templates 对象。"
        raise KbTplLoadError(msg)
    if not isinstance(slots_raw, dict):
        msg = "slots.v1.json 缺少 slots 对象。"
        raise KbTplLoadError(msg)
    if not isinstance(fallbacks_raw, dict):
        msg = "fallback-by-risk.v1.json 缺少 fallbacks 对象。"
        raise KbTplLoadError(msg)
    if not isinstance(profiles_raw, dict):
        msg = "tone-by-risk.v1.json 缺少 profiles 对象。"
        raise KbTplLoadError(msg)
    if not isinstance(snippets_raw, dict):
        msg = "safety-notices.v1.json 缺少 snippets 对象。"
        raise KbTplLoadError(msg)
    if not isinstance(rules_raw, list):
        msg = "safety-notices.v1.json 缺少 resolveRules 数组。"
        raise KbTplLoadError(msg)

    templates: dict[str, TemplateEntry] = {}
    for template_id, entry_raw in templates_raw.items():
        if not isinstance(entry_raw, dict):
            msg = f"templates[{template_id!r}] 必须为对象。"
            raise KbTplLoadError(msg)
        entry = TemplateEntry.model_validate(entry_raw)
        if entry.meta.template_id != template_id:
            msg = (
                f"模板键 {template_id!r} 与 meta.templateId "
                f"{entry.meta.template_id!r} 不一致。"
            )
            raise KbTplLoadError(msg)
        templates[template_id] = entry

    slots: dict[str, SlotDefinition] = {}
    for slot_id, slot_raw in slots_raw.items():
        if not isinstance(slot_raw, dict):
            msg = f"slots[{slot_id!r}] 必须为对象。"
            raise KbTplLoadError(msg)
        slots[slot_id] = SlotDefinition.model_validate(slot_raw)

    fallbacks: dict[str, FallbackTemplateEntry] = {}
    for key, fb_raw in fallbacks_raw.items():
        if not isinstance(fb_raw, dict):
            msg = f"fallbacks[{key!r}] 必须为对象。"
            raise KbTplLoadError(msg)
        fallbacks[key] = FallbackTemplateEntry.model_validate(fb_raw)

    tone_profiles: dict[str, ToneProfile] = {}
    for profile_id, profile_raw in profiles_raw.items():
        if not isinstance(profile_raw, dict):
            msg = f"profiles[{profile_id!r}] 必须为对象。"
            raise KbTplLoadError(msg)
        tone_profiles[profile_id] = ToneProfile.model_validate(profile_raw)

    safety_snippets: dict[str, str] = {}
    for snippet_id, text in snippets_raw.items():
        if not isinstance(snippet_id, str) or not isinstance(text, str):
            msg = "safety snippets 键值必须均为字符串。"
            raise KbTplLoadError(msg)
        safety_snippets[snippet_id] = text

    safety_rules: list[SafetyNoticeRule] = []
    for index, rule_raw in enumerate(rules_raw):
        if not isinstance(rule_raw, dict):
            msg = f"resolveRules[{index}] 必须为对象。"
            raise KbTplLoadError(msg)
        safety_rules.append(SafetyNoticeRule.model_validate(rule_raw))

    meta = templates_payload.get("meta", {})
    bundle_version = "unknown"
    if isinstance(meta, dict):
        raw_version = meta.get("bundleVersion")
        if isinstance(raw_version, str):
            bundle_version = raw_version

    return KbTplBundle(
        bundle_version=bundle_version,
        templates=templates,
        slots=slots,
        fallbacks=fallbacks,
        tone_profiles=tone_profiles,
        safety_snippets=safety_snippets,
        safety_resolve_rules=tuple(safety_rules),
    )


def _read_json_file(path: Path) -> dict[str, Any]:
    """读取单个 JSON 文件为字典。

    :param path: JSON 文件路径。
    :type path: pathlib.Path
    :returns: 解析后的根对象（必须为 dict）。
    :rtype: dict[str, Any]
    :raises KbTplLoadError: 文件不存在、读取失败或根非对象时抛出。
    """
    if not path.is_file():
        msg = f"KB-TPL 文件不存在：{path}"
        raise KbTplLoadError(msg)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"读取 KB-TPL 文件失败：{path}（{exc}）"
        raise KbTplLoadError(msg) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"KB-TPL JSON 解析失败：{path}（{exc.msg}）"
        raise KbTplLoadError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"KB-TPL 根节点必须为对象：{path}"
        raise KbTplLoadError(msg)
    return payload


def load_kb_tpl_bundle(
    config_dir: Path | str | None = None,
) -> KbTplBundle:
    """从目录加载完整 KB-TPL 制品集。

    :param config_dir: 配置目录；``None`` 时使用 ``default_kb_tpl_config_dir()``。
    :type config_dir: pathlib.Path | str | None
    :returns: KB-TPL 聚合包。
    :rtype: KbTplBundle
    :raises KbTplLoadError: 任一必需文件缺失或解析失败时抛出。
    """
    resolved_dir = (
        Path(config_dir) if config_dir is not None else default_kb_tpl_config_dir()
    )
    return load_kb_tpl_bundle_from_json(
        templates_payload=_read_json_file(resolved_dir / "templates.v1.json"),
        slots_payload=_read_json_file(resolved_dir / "slots.v1.json"),
        fallback_payload=_read_json_file(resolved_dir / "fallback-by-risk.v1.json"),
        tone_payload=_read_json_file(resolved_dir / "tone-by-risk.v1.json"),
        safety_payload=_read_json_file(resolved_dir / "safety-notices.v1.json"),
    )
