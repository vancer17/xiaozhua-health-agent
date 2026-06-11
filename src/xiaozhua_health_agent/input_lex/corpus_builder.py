"""KB-INPUT-LEX 匹配语料构建器（CorpusBuilder）。

从 ``AgentInput`` 的 ``meta.matchSources`` 字段抽取文本，按词表
``matchDefaults`` 归一化后产出 :class:`InputLexMatchCorpus`，供后续
``RuleMatcher`` 消费。本模块 **不** 执行规则匹配或字段补丁。
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping, Sequence
from typing import Any, Final

from pydantic import ValidationError

from xiaozhua_health_agent.input_lex.input_lex_types import (
    InputLexBundle,
    InputLexCorpusSegment,
    InputLexMatchCorpus,
    InputLexMatchDefaults,
    InputLexMatchSourceLiteral,
)
from xiaozhua_health_agent.schemas import AgentInput

__all__ = [
    "CorpusBuilder",
    "InputLexCorpusBuildError",
    "build_match_corpus",
    "build_match_corpus_async",
    "build_match_corpus_from_mapping",
    "build_match_corpus_from_mapping_async",
    "merge_normalized_segments",
    "normalize_match_text",
]


class InputLexCorpusBuildError(Exception):
    """匹配语料构建失败（入参校验或来源字段提取错误）。"""


_WHITESPACE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\s+")


class CorpusBuilder:
    """从 ``AgentInput`` 构建 KB-INPUT-LEX 短语匹配语料。

    读取词表 ``meta.matchSources`` 与 ``matchDefaults``，将
    ``userReport.text``、``userReport.symptoms[]``、``context.notes[]``
    规范化为不可变 :class:`InputLexMatchCorpus`。纯 CPU 逻辑；异步方法
    通过线程池隔离 Pydantic 校验与归一化，避免阻塞事件循环。
    """

    def __init__(self, bundle: InputLexBundle) -> None:
        """绑定词表快照并缓存匹配配置。

        :param bundle: 已加载的 KB-INPUT-LEX 制品。
        :type bundle: InputLexBundle
        """
        self._bundle: InputLexBundle = bundle
        self._match_sources: tuple[InputLexMatchSourceLiteral, ...] = (
            bundle.meta.match_sources
        )
        self._match_defaults: InputLexMatchDefaults = bundle.match_defaults

    @property
    def bundle(self) -> InputLexBundle:
        """返回构造时绑定的词表快照。

        :returns: 不可变词表制品。
        :rtype: InputLexBundle
        """
        return self._bundle

    @property
    def match_sources(self) -> tuple[InputLexMatchSourceLiteral, ...]:
        """返回生效的语料来源路径列表。

        :returns: ``meta.matchSources`` 快照。
        :rtype: tuple[InputLexMatchSourceLiteral, ...]
        """
        return self._match_sources

    @property
    def match_defaults(self) -> InputLexMatchDefaults:
        """返回生效的匹配默认参数。

        :returns: ``matchDefaults`` 快照。
        :rtype: InputLexMatchDefaults
        """
        return self._match_defaults

    def build(self, agent_input: AgentInput) -> InputLexMatchCorpus:
        """从强类型入参同步构建匹配语料。

        :param agent_input: 符合 input_schema 的分诊入参。
        :type agent_input: AgentInput
        :returns: 归一化后的匹配语料包。
        :rtype: InputLexMatchCorpus
        """
        segments = self._collect_segments(agent_input)
        return self._assemble_corpus(segments)

    async def build_async(self, agent_input: AgentInput) -> InputLexMatchCorpus:
        """从强类型入参异步构建匹配语料。

        归一化与分段展开在线程池中执行，避免大文本阻塞事件循环。

        :param agent_input: 符合 input_schema 的分诊入参。
        :type agent_input: AgentInput
        :returns: 归一化后的匹配语料包。
        :rtype: InputLexMatchCorpus
        """

        def _build_sync() -> InputLexMatchCorpus:
            """在线程池中执行同步构建（闭包）。

            :returns: 匹配语料包。
            :rtype: InputLexMatchCorpus
            """
            return self.build(agent_input)

        return await asyncio.to_thread(_build_sync)

    def build_from_mapping(
        self,
        payload: Mapping[str, Any],
    ) -> InputLexMatchCorpus:
        """从 JSON 风格根对象校验入参并构建匹配语料。

        :param payload: App / mock adapter 提交的 input 对象。
        :type payload: collections.abc.Mapping[str, Any]
        :returns: 归一化后的匹配语料包。
        :rtype: InputLexMatchCorpus
        :raises InputLexCorpusBuildError: ``AgentInput`` 校验失败时抛出。
        """
        agent_input = _validate_agent_input_mapping(payload)
        return self.build(agent_input)

    async def build_from_mapping_async(
        self,
        payload: Mapping[str, Any],
    ) -> InputLexMatchCorpus:
        """从 JSON 风格根对象异步校验入参并构建匹配语料。

        Pydantic 校验与语料构建均在线程池中执行。

        :param payload: App / mock adapter 提交的 input 对象。
        :type payload: collections.abc.Mapping[str, Any]
        :returns: 归一化后的匹配语料包。
        :rtype: InputLexMatchCorpus
        :raises InputLexCorpusBuildError: ``AgentInput`` 校验失败时抛出。
        """

        def _build_sync() -> InputLexMatchCorpus:
            """在线程池中执行校验与构建（闭包）。

            :returns: 匹配语料包。
            :rtype: InputLexMatchCorpus
            """
            return self.build_from_mapping(payload)

        return await asyncio.to_thread(_build_sync)

    def _collect_segments(
        self,
        agent_input: AgentInput,
    ) -> tuple[InputLexCorpusSegment, ...]:
        """按 ``match_sources`` 顺序收集并归一化语料分段。

        :param agent_input: 分诊入参。
        :type agent_input: AgentInput
        :returns: 有序分段元组。
        :rtype: tuple[InputLexCorpusSegment, ...]
        """
        collected: list[InputLexCorpusSegment] = []
        for source in self._match_sources:
            raw_texts = _extract_raw_texts_for_source(agent_input, source)
            for index, raw_text in enumerate(raw_texts):
                normalized = normalize_match_text(
                    raw_text,
                    match_defaults=self._match_defaults,
                )
                collected.append(
                    InputLexCorpusSegment(
                        source=source,
                        index=index,
                        raw_text=raw_text,
                        normalized_text=normalized,
                    )
                )
        return tuple(collected)

    def _assemble_corpus(
        self,
        segments: tuple[InputLexCorpusSegment, ...],
    ) -> InputLexMatchCorpus:
        """将分段列表封装为不可变语料包。

        :param segments: 有序分段。
        :type segments: tuple[InputLexCorpusSegment, ...]
        :returns: 含合并语料的快照。
        :rtype: InputLexMatchCorpus
        """
        merged = merge_normalized_segments(segments)
        return InputLexMatchCorpus(
            merged=merged,
            segments=segments,
            match_sources=self._match_sources,
            match_defaults=self._match_defaults,
        )


def build_match_corpus(
    agent_input: AgentInput,
    bundle: InputLexBundle,
) -> InputLexMatchCorpus:
    """使用词表快照从 ``AgentInput`` 同步构建匹配语料。

    :param agent_input: 分诊入参。
    :type agent_input: AgentInput
    :param bundle: KB-INPUT-LEX 制品。
    :type bundle: InputLexBundle
    :returns: 匹配语料包。
    :rtype: InputLexMatchCorpus
    """
    return CorpusBuilder(bundle).build(agent_input)


async def build_match_corpus_async(
    agent_input: AgentInput,
    bundle: InputLexBundle,
) -> InputLexMatchCorpus:
    """使用词表快照从 ``AgentInput`` 异步构建匹配语料。

    :param agent_input: 分诊入参。
    :type agent_input: AgentInput
    :param bundle: KB-INPUT-LEX 制品。
    :type bundle: InputLexBundle
    :returns: 匹配语料包。
    :rtype: InputLexMatchCorpus
    """
    return await CorpusBuilder(bundle).build_async(agent_input)


def build_match_corpus_from_mapping(
    payload: Mapping[str, Any],
    bundle: InputLexBundle,
) -> InputLexMatchCorpus:
    """从 JSON 根对象校验入参并同步构建匹配语料。

    :param payload: input_schema 风格对象。
    :type payload: collections.abc.Mapping[str, Any]
    :param bundle: KB-INPUT-LEX 制品。
    :type bundle: InputLexBundle
    :returns: 匹配语料包。
    :rtype: InputLexMatchCorpus
    :raises InputLexCorpusBuildError: 入参校验失败时抛出。
    """
    return CorpusBuilder(bundle).build_from_mapping(payload)


async def build_match_corpus_from_mapping_async(
    payload: Mapping[str, Any],
    bundle: InputLexBundle,
) -> InputLexMatchCorpus:
    """从 JSON 根对象异步校验入参并构建匹配语料。

    :param payload: input_schema 风格对象。
    :type payload: collections.abc.Mapping[str, Any]
    :param bundle: KB-INPUT-LEX 制品。
    :type bundle: InputLexBundle
    :returns: 匹配语料包。
    :rtype: InputLexMatchCorpus
    :raises InputLexCorpusBuildError: 入参校验失败时抛出。
    """
    return await CorpusBuilder(bundle).build_from_mapping_async(payload)


def normalize_match_text(
    text: str,
    *,
    match_defaults: InputLexMatchDefaults,
) -> str:
    """按词表 ``matchDefaults`` 归一化单段文本。

    步骤：

    1. 去除首尾空白；
    2. 若 ``normalizeWhitespace`` 为真，折叠并移除所有空白字符；
    3. 若 ``caseInsensitive`` 为真，执行 ``casefold``。

    :param text: 原始文本。
    :type text: str
    :param match_defaults: 全局匹配默认参数。
    :type match_defaults: InputLexMatchDefaults
    :returns: 用于子串匹配的归一化文本。
    :rtype: str
    """
    normalized = text.strip()
    if match_defaults.normalize_whitespace:
        normalized = _WHITESPACE_PATTERN.sub("", normalized)
    if match_defaults.case_insensitive:
        normalized = normalized.casefold()
    return normalized


def merge_normalized_segments(
    segments: Sequence[InputLexCorpusSegment],
) -> str:
    """将分段归一化文本拼接为合并语料。

    仅拼接 ``normalized_text`` 非空的分段，不插入分隔符（空白已在
    分段级归一化中处理）。

    :param segments: 语料分段序列。
    :type segments: collections.abc.Sequence[InputLexCorpusSegment]
    :returns: 合并后的归一化语料。
    :rtype: str
    """
    parts: list[str] = []
    for segment in segments:
        if segment.normalized_text:
            parts.append(segment.normalized_text)
    return "".join(parts)


def _extract_raw_texts_for_source(
    agent_input: AgentInput,
    source: InputLexMatchSourceLiteral,
) -> tuple[str, ...]:
    """从 ``AgentInput`` 提取指定来源的原始文本列表。

    :param agent_input: 分诊入参。
    :type agent_input: AgentInput
    :param source: ``meta.matchSources`` 中的路径。
    :type source: InputLexMatchSourceLiteral
    :returns: 原始文本元组（列表来源按数组顺序展开）。
    :rtype: tuple[str, ...]
    :raises InputLexCorpusBuildError: 遇到未知来源路径时抛出。
    """
    if source == "userReport.text":
        return (agent_input.user_report.text,)
    if source == "userReport.symptoms":
        return tuple(agent_input.user_report.symptoms)
    if source == "context.notes":
        return tuple(agent_input.context.notes)
    msg = f"不支持的 matchSources 路径：{source!r}"
    raise InputLexCorpusBuildError(msg)


def _validate_agent_input_mapping(payload: Mapping[str, Any]) -> AgentInput:
    """将 JSON 根对象校验为 ``AgentInput``。

    :param payload: input_schema 风格对象。
    :type payload: collections.abc.Mapping[str, Any]
    :returns: 强类型入参。
    :rtype: AgentInput
    :raises InputLexCorpusBuildError: Pydantic 校验失败时抛出。
    """
    try:
        return AgentInput.model_validate(dict(payload))
    except ValidationError as exc:
        msg = f"AgentInput 校验失败，无法构建匹配语料：{exc}"
        raise InputLexCorpusBuildError(msg) from exc
