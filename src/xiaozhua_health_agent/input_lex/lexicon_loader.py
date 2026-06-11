"""KB-INPUT-LEX 制品加载器（LexiconLoader）。"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from xiaozhua_health_agent.input_lex.input_lex_types import (
    INPUT_LEX_SCHEMA_VERSION,
    InputLexBundle,
    InputLexMatchDefaults,
    InputLexRule,
)
from xiaozhua_health_agent.paths import default_input_lex_path

__all__ = [
    "InputLexLoadError",
    "LexiconLoader",
    "clear_default_lexicon_loader_cache",
    "get_default_lexicon_loader",
    "load_input_lex_bundle",
    "load_input_lex_bundle_async",
    "load_input_lex_bundle_from_json",
    "load_input_lex_bundle_from_json_text",
]


class InputLexLoadError(Exception):
    """KB-INPUT-LEX 制品加载或校验失败。"""


class LexiconLoader:
    """KB-INPUT-LEX 词表加载器（路径解析 + 同步/异步磁盘 IO）。

    负责从 JSON 制品构建不可变 :class:`InputLexBundle`，供后续接入层
    ``RuleMatcher`` / ``PatchMerger`` 消费。本类 **不** 执行口语匹配或
    ``AgentInput`` 补丁写入。
    """

    def __init__(self, path: Path | str | None = None) -> None:
        """构造加载器并记录制品路径。

        :param path: JSON 文件路径；``None`` 时使用
            :func:`xiaozhua_health_agent.paths.default_input_lex_path`。
        :type path: pathlib.Path | str | None
        """
        self._path: Path | None = Path(path) if path is not None else None

    def resolved_path(self) -> Path:
        """解析生效的制品绝对路径。

        :returns: 词表 JSON 文件路径。
        :rtype: pathlib.Path
        """
        if self._path is not None:
            return self._path.expanduser().resolve()
        return default_input_lex_path()

    def load(self) -> InputLexBundle:
        """从磁盘同步加载并校验词表制品。

        :returns: 不可变词表快照。
        :rtype: InputLexBundle
        :raises InputLexLoadError: 文件不存在、读取失败或校验失败时抛出。
        """
        return load_input_lex_bundle(self.resolved_path())

    async def load_async(self) -> InputLexBundle:
        """从磁盘异步加载并校验词表制品。

        文件读取在线程池中执行，避免阻塞事件循环。

        :returns: 不可变词表快照。
        :rtype: InputLexBundle
        :raises InputLexLoadError: 文件不存在、读取失败或校验失败时抛出。
        """
        return await load_input_lex_bundle_async(self.resolved_path())

    @staticmethod
    def from_json_text(text: str) -> InputLexBundle:
        """从 UTF-8 JSON 文本解析词表（无磁盘 IO）。

        :param text: 完整 ``input-lex.v1.json`` 文本。
        :type text: str
        :returns: 不可变词表快照。
        :rtype: InputLexBundle
        :raises InputLexLoadError: JSON 解析或校验失败时抛出。
        """
        return load_input_lex_bundle_from_json_text(text)

    @staticmethod
    def from_json_mapping(payload: Mapping[str, Any]) -> InputLexBundle:
        """从已解析 JSON 根对象构建词表（无磁盘 IO）。

        :param payload: ``input-lex.v1.json`` 根对象。
        :type payload: collections.abc.Mapping[str, Any]
        :returns: 不可变词表快照。
        :rtype: InputLexBundle
        :raises InputLexLoadError: 校验失败时抛出。
        """
        return load_input_lex_bundle_from_json(payload)


def load_input_lex_bundle_from_json_text(text: str) -> InputLexBundle:
    """从 JSON 字符串加载词表制品。

    :param text: UTF-8 JSON 文本。
    :type text: str
    :returns: 校验后的词表快照。
    :rtype: InputLexBundle
    :raises InputLexLoadError: 解析或校验失败时抛出。
    """
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = (
            f"KB-INPUT-LEX JSON 解析失败：{exc.msg}"
            f"（位置 line={exc.lineno}, col={exc.colno}）"
        )
        raise InputLexLoadError(msg) from exc
    if not isinstance(payload, dict):
        msg = f"KB-INPUT-LEX 根节点必须为对象，实际为 {type(payload).__name__}"
        raise InputLexLoadError(msg)
    return load_input_lex_bundle_from_json(payload)


def load_input_lex_bundle_from_json(payload: Mapping[str, Any]) -> InputLexBundle:
    """从 JSON 根对象加载并校验词表制品。

    :param payload: ``input-lex.v1.json`` 根对象。
    :type payload: collections.abc.Mapping[str, Any]
    :returns: 校验后的词表快照。
    :rtype: InputLexBundle
    :raises InputLexLoadError: 结构或语义校验失败时抛出。
    """
    try:
        bundle = InputLexBundle.model_validate(dict(payload))
    except ValidationError as exc:
        msg = f"KB-INPUT-LEX 结构校验失败：{exc}"
        raise InputLexLoadError(msg) from exc

    _validate_schema_version(bundle)
    _validate_phrase_lengths(bundle)
    _validate_patch_enumerations(bundle)
    _validate_enum_escalation_alignment(bundle)
    return bundle


def load_input_lex_bundle(path: Path | str | None = None) -> InputLexBundle:
    """从文件同步加载词表制品。

    :param path: JSON 文件路径；``None`` 时使用默认制品路径。
    :type path: pathlib.Path | str | None
    :returns: 校验后的词表快照。
    :rtype: InputLexBundle
    :raises InputLexLoadError: 文件不存在、读取失败或校验失败时抛出。
    """
    resolved = _resolve_lexicon_path(path)
    if not resolved.is_file():
        msg = f"KB-INPUT-LEX 文件不存在：{resolved}"
        raise InputLexLoadError(msg)
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"读取 KB-INPUT-LEX 文件失败：{resolved}（{exc}）"
        raise InputLexLoadError(msg) from exc
    return load_input_lex_bundle_from_json_text(text)


async def load_input_lex_bundle_async(
    path: Path | str | None = None,
) -> InputLexBundle:
    """从文件异步加载词表制品。

    文件读取在线程池中执行，避免阻塞事件循环。

    :param path: JSON 文件路径；``None`` 时使用默认制品路径。
    :type path: pathlib.Path | str | None
    :returns: 校验后的词表快照。
    :rtype: InputLexBundle
    :raises InputLexLoadError: 文件不存在、读取失败或校验失败时抛出。
    """

    def _load_sync() -> InputLexBundle:
        """在线程池中执行同步加载（闭包）。

        :returns: 词表快照。
        :rtype: InputLexBundle
        """
        return load_input_lex_bundle(path)

    return await asyncio.to_thread(_load_sync)


@lru_cache(maxsize=1)
def get_default_lexicon_loader() -> LexiconLoader:
    """返回使用默认制品路径的进程内单例加载器。

    :returns: 默认路径的 :class:`LexiconLoader` 实例。
    :rtype: LexiconLoader
    """
    return LexiconLoader()


def clear_default_lexicon_loader_cache() -> None:
    """清空默认加载器 LRU 缓存（单测用）。

    :rtype: None
    """
    get_default_lexicon_loader.cache_clear()


def _resolve_lexicon_path(path: Path | str | None) -> Path:
    """解析词表 JSON 文件路径。

    :param path: 调用方路径；``None`` 时使用项目默认路径。
    :type path: pathlib.Path | str | None
    :returns: 绝对路径。
    :rtype: pathlib.Path
    """
    if path is None:
        return default_input_lex_path()
    return Path(path).expanduser().resolve()


def _validate_schema_version(bundle: InputLexBundle) -> None:
    """校验 ``meta.schemaVersion`` 与加载器支持的版本一致。

    :param bundle: 已解析的词表快照。
    :type bundle: InputLexBundle
    :rtype: None
    :raises InputLexLoadError: 版本不匹配时抛出。
    """
    if bundle.meta.schema_version != INPUT_LEX_SCHEMA_VERSION:
        msg = (
            "KB-INPUT-LEX schemaVersion 不受支持："
            f"期望 {INPUT_LEX_SCHEMA_VERSION!r}，"
            f"实际 {bundle.meta.schema_version!r}"
        )
        raise InputLexLoadError(msg)


def _validate_phrase_lengths(bundle: InputLexBundle) -> None:
    """校验各规则短语长度满足 ``matchDefaults.minPhraseLength``。

    :param bundle: 已解析的词表快照。
    :type bundle: InputLexBundle
    :rtype: None
    :raises InputLexLoadError: 存在过短短语时抛出。
    """
    min_length = bundle.match_defaults.min_phrase_length
    violations = _collect_rules_with_short_phrases(
        bundle.rules,
        min_length=min_length,
        match_defaults=bundle.match_defaults,
    )
    if violations:
        preview = ", ".join(violations[:5])
        suffix = "..." if len(violations) > 5 else ""
        msg = (
            f"KB-INPUT-LEX 存在短于 minPhraseLength={min_length} 的短语："
            f"{preview}{suffix}"
        )
        raise InputLexLoadError(msg)


def _validate_patch_enumerations(bundle: InputLexBundle) -> None:
    """校验 ``patches`` 中字符串枚举值落在 ``enumerations`` 定义内。

    :param bundle: 已解析的词表快照。
    :type bundle: InputLexBundle
    :rtype: None
    :raises InputLexLoadError: 枚举值非法时抛出。
    """
    violations: list[str] = []
    for rule in bundle.rules:
        for field_path, value in rule.patches.items():
            if not isinstance(value, str):
                continue
            allowed = bundle.enumeration_for_path(field_path)
            if allowed is None:
                continue
            if value not in allowed:
                violations.append(f"{rule.id} patches[{field_path!r}]={value!r}")
    if violations:
        preview = "; ".join(violations[:5])
        suffix = "..." if len(violations) > 5 else ""
        msg = f"KB-INPUT-LEX patches 含非法枚举值：{preview}{suffix}"
        raise InputLexLoadError(msg)


def _validate_enum_escalation_alignment(bundle: InputLexBundle) -> None:
    """校验 ``mergePolicy.enumEscalation`` 与 ``enumerations`` 档位一致。

    :param bundle: 已解析的词表快照。
    :type bundle: InputLexBundle
    :rtype: None
    :raises InputLexLoadError: 档位表与 enumerations 不一致时抛出。
    """
    for field_path, levels in bundle.merge_policy.enum_escalation.items():
        allowed = bundle.enumeration_for_path(field_path)
        if allowed is None:
            msg = f"enumEscalation 含未知字段路径：{field_path!r}"
            raise InputLexLoadError(msg)
        if tuple(levels) != allowed:
            msg = (
                f"enumEscalation[{field_path!r}] 与 enumerations 不一致："
                f"escalation={list(levels)!r}, enumerations={list(allowed)!r}"
            )
            raise InputLexLoadError(msg)


def _normalized_phrase_length(
    phrase: str,
    *,
    match_defaults: InputLexMatchDefaults,
) -> int:
    """计算短语在匹配默认策略下的有效长度。

    :param phrase: 原始短语。
    :type phrase: str
    :param match_defaults: 全局匹配默认参数。
    :type match_defaults: InputLexMatchDefaults
    :returns: 有效字符数。
    :rtype: int
    """
    text = phrase.strip()
    if match_defaults.normalize_whitespace:
        text = re.sub(r"\s+", "", text)
    return len(text)


def _collect_rules_with_short_phrases(
    rules: tuple[InputLexRule, ...],
    *,
    min_length: int,
    match_defaults: InputLexMatchDefaults,
) -> list[str]:
    """收集短语长度不足规则 ID 列表（内部辅助）。

    :param rules: 规则元组。
    :type rules: tuple[InputLexRule, ...]
    :param min_length: 最小短语长度。
    :type min_length: int
    :param match_defaults: 匹配默认参数。
    :type match_defaults: InputLexMatchDefaults
    :returns: ``ruleId: phrase`` 描述列表。
    :rtype: list[str]
    """
    violations: list[str] = []
    for rule in rules:
        for phrase in rule.match.phrases:
            effective_len = _normalized_phrase_length(
                phrase,
                match_defaults=match_defaults,
            )
            if effective_len < min_length:
                violations.append(f"{rule.id}: {phrase!r}")
    return violations
