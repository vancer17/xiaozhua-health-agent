"""KB-INPUT-LEX enrich 编排服务（L1 接入层）。

串联 :class:`~xiaozhua_health_agent.input_lex.LexiconLoader`、
:class:`~xiaozhua_health_agent.input_lex.CorpusBuilder`、
:class:`~xiaozhua_health_agent.input_lex.RuleMatcher`、
:class:`~xiaozhua_health_agent.input_lex.PatchMerger` 与
:class:`~xiaozhua_health_agent.input_lex.EnrichAudit`，在 ``parse_input`` 之前将
口语化入参补全为结构化 ``input_schema`` 字段。本模块 **不** 执行医学分诊裁决。
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from xiaozhua_health_agent.input_lex.corpus_builder import (
    CorpusBuilder,
    InputLexCorpusBuildError,
)
from xiaozhua_health_agent.input_lex.enrich_audit import (
    EnrichAuditError,
    build_enrich_audit_record_async,
    persist_enrich_audit_record_async,
)
from xiaozhua_health_agent.input_lex.input_lex_types import (
    DEFAULT_INPUT_LEX_ENRICH_OPTIONS,
    InputLexBundle,
    InputLexEnrichAuditPersistResult,
    InputLexEnrichAuditRecord,
    InputLexEnrichOptions,
    InputLexEnrichResult,
    InputLexMatchCorpus,
    InputLexMergeResult,
    InputLexRuleMatchResult,
)
from xiaozhua_health_agent.input_lex.lexicon_loader import (
    InputLexLoadError,
    load_input_lex_bundle_async,
)
from xiaozhua_health_agent.input_lex.patch_merger import PatchMerger
from xiaozhua_health_agent.input_lex.rule_matcher import RuleMatcher
from xiaozhua_health_agent.schemas import SpeciesLiteral

__all__ = [
    "InputLexEnrichError",
    "InputLexEnricher",
    "enrich_agent_input_payload_async",
    "resolve_input_lex_bundle_async",
]


class InputLexEnrichError(Exception):
    """KB-INPUT-LEX enrich 编排失败（词表加载、语料构建或审计持久化等）。"""


async def resolve_input_lex_bundle_async(
    *,
    bundle: InputLexBundle | None = None,
    load_default: bool = True,
) -> InputLexBundle:
    """解析本次 enrich 应使用的 KB-INPUT-LEX 词表快照。

    优先使用调用方显式传入的 ``bundle``；否则在 ``load_default=True`` 时通过
    默认路径异步加载制品。

    :param bundle: 可选预加载词表快照。
    :type bundle: InputLexBundle | None
    :param load_default: 当 ``bundle`` 为 ``None`` 时是否加载默认制品。
    :type load_default: bool
    :returns: 不可变词表快照。
    :rtype: InputLexBundle
    :raises InputLexEnrichError: 未提供 bundle 且禁止默认加载时抛出。
    :raises InputLexLoadError: 默认制品加载或校验失败时抛出。
    """
    if bundle is not None:
        return bundle
    if not load_default:
        msg = "未提供 input_lex bundle 且 load_default=False，无法执行 enrich。"
        raise InputLexEnrichError(msg)
    return await load_input_lex_bundle_async()


class InputLexEnricher:
    """KB-INPUT-LEX 单次 enrich 编排器。

    绑定不可变词表快照，按固定顺序执行语料构建 → 规则匹配 → 补丁合并 →
    可选审计构建与持久化。CPU 密集步骤委托各子模块的 ``*_async`` 方法（线程池
    隔离）；词表加载在 :func:`resolve_input_lex_bundle_async` 中完成。
    """

    def __init__(self, bundle: InputLexBundle) -> None:
        """绑定词表快照并构造子组件。

        :param bundle: 已加载的 KB-INPUT-LEX 制品。
        :type bundle: InputLexBundle
        """
        self._bundle: InputLexBundle = bundle
        self._corpus_builder: CorpusBuilder = CorpusBuilder(bundle)
        self._rule_matcher: RuleMatcher = RuleMatcher(bundle)
        self._patch_merger: PatchMerger = PatchMerger(bundle)

    @property
    def bundle(self) -> InputLexBundle:
        """返回构造时绑定的词表快照。

        :returns: 不可变词表制品。
        :rtype: InputLexBundle
        """
        return self._bundle

    async def enrich_async(
        self,
        payload: Mapping[str, Any],
        *,
        options: InputLexEnrichOptions | None = None,
    ) -> InputLexEnrichResult:
        """对单份 input JSON 执行完整 enrich 编排（异步）。

        :param payload: camelCase 分诊入参根对象（``input_schema`` 风格）。
        :type payload: collections.abc.Mapping[str, Any]
        :param options: 编排选项；省略时使用
            :data:`~xiaozhua_health_agent.input_lex.DEFAULT_INPUT_LEX_ENRICH_OPTIONS`。
        :type options: InputLexEnrichOptions | None
        :returns: 含 enriched payload 与阶段性产物的编排结果。
        :rtype: InputLexEnrichResult
        :raises InputLexCorpusBuildError: 入参无法校验为 ``AgentInput`` 时抛出。
        :raises InputLexEnrichError: 审计持久化配置不合法或持久化失败时抛出。
        """
        resolved_options = (
            options if options is not None else DEFAULT_INPUT_LEX_ENRICH_OPTIONS
        )
        original_payload = copy.deepcopy(dict(payload))

        corpus = await self._corpus_builder.build_from_mapping_async(payload)
        species = _extract_species_from_payload(payload)
        match_result = await self._rule_matcher.match_async(
            corpus,
            species=species,
        )
        merge_result = await self._patch_merger.merge_async(payload, match_result)

        audit = await self._build_audit_if_requested(
            resolved_options=resolved_options,
            match_result=match_result,
            merge_result=merge_result,
            corpus=corpus,
            original_payload=original_payload,
        )
        audit_persist_result = await self._persist_audit_if_requested(
            resolved_options=resolved_options,
            audit=audit,
        )

        return InputLexEnrichResult(
            enriched_payload=merge_result.enriched_payload,
            merge_result=merge_result,
            match_result=match_result,
            corpus=corpus,
            audit=audit,
            audit_persist_result=audit_persist_result,
            skipped=False,
        )

    async def _build_audit_if_requested(
        self,
        *,
        resolved_options: InputLexEnrichOptions,
        match_result: InputLexRuleMatchResult,
        merge_result: InputLexMergeResult,
        corpus: InputLexMatchCorpus,
        original_payload: dict[str, Any],
    ) -> InputLexEnrichAuditRecord | None:
        """按选项构建 enrich 审计记录（内部辅助）。

        :param resolved_options: 已解析的编排选项。
        :type resolved_options: InputLexEnrichOptions
        :param match_result: 规则匹配结果。
        :type match_result: InputLexRuleMatchResult
        :param merge_result: 补丁合并结果。
        :type merge_result: InputLexMergeResult
        :param corpus: 匹配语料快照。
        :type corpus: InputLexMatchCorpus
        :param original_payload: 原始入参深拷贝。
        :type original_payload: dict[str, Any]
        :returns: 审计记录；未启用构建时为 ``None``。
        :rtype: InputLexEnrichAuditRecord | None
        """
        if not resolved_options.build_audit:
            return None
        return await build_enrich_audit_record_async(
            match_result=match_result,
            merge_result=merge_result,
            corpus=corpus,
            original_payload=original_payload,
            bundle=self._bundle,
            options=resolved_options.audit_build_options,
        )

    async def _persist_audit_if_requested(
        self,
        *,
        resolved_options: InputLexEnrichOptions,
        audit: InputLexEnrichAuditRecord | None,
    ) -> InputLexEnrichAuditPersistResult | None:
        """按选项持久化 enrich 审计记录（内部辅助）。

        :param resolved_options: 已解析的编排选项。
        :type resolved_options: InputLexEnrichOptions
        :param audit: 待持久化的审计记录。
        :type audit: InputLexEnrichAuditRecord | None
        :returns: 持久化结果；未启用时为 ``None``。
        :rtype: InputLexEnrichAuditPersistResult | None
        :raises InputLexEnrichError: ``persist_audit=True`` 但缺少审计或持久化选项时抛出。
        :raises EnrichAuditError: 磁盘写入失败时抛出（包装为 :class:`InputLexEnrichError`）。
        """
        if not resolved_options.persist_audit:
            return None
        if audit is None:
            msg = "persist_audit=True 要求 build_audit=True 以产出审计记录。"
            raise InputLexEnrichError(msg)
        persist_options = resolved_options.audit_persist_options
        if persist_options is None:
            msg = "persist_audit=True 时必须提供 audit_persist_options。"
            raise InputLexEnrichError(msg)
        try:
            return await persist_enrich_audit_record_async(
                audit,
                options=persist_options,
            )
        except EnrichAuditError as exc:
            msg = f"enrich 审计持久化失败：{exc}"
            raise InputLexEnrichError(msg) from exc


async def enrich_agent_input_payload_async(
    payload: Mapping[str, Any],
    *,
    bundle: InputLexBundle | None = None,
    load_default_bundle: bool = True,
    options: InputLexEnrichOptions | None = None,
) -> InputLexEnrichResult:
    """便捷函数：异步解析词表并执行单次 enrich 编排。

    :param payload: camelCase 分诊入参根对象。
    :type payload: collections.abc.Mapping[str, Any]
    :param bundle: 可选预加载词表；省略时由 ``load_default_bundle`` 控制是否加载默认制品。
    :type bundle: InputLexBundle | None
    :param load_default_bundle: 当 ``bundle`` 为 ``None`` 时是否加载默认词表。
    :type load_default_bundle: bool
    :param options: enrich 编排选项。
    :type options: InputLexEnrichOptions | None
    :returns: enrich 编排完整结果。
    :rtype: InputLexEnrichResult
    :raises InputLexEnrichError: 词表无法解析时抛出。
    :raises InputLexLoadError: 默认词表加载失败时抛出。
    :raises InputLexCorpusBuildError: 入参语料构建失败时抛出。
    """
    resolved_bundle = await resolve_input_lex_bundle_async(
        bundle=bundle,
        load_default=load_default_bundle,
    )
    return await InputLexEnricher(resolved_bundle).enrich_async(
        payload,
        options=options,
    )


def _extract_species_from_payload(
    payload: Mapping[str, Any],
) -> SpeciesLiteral | None:
    """从入参 JSON 提取 ``pet.species``（内部辅助）。

    :param payload: camelCase 分诊入参根对象。
    :type payload: collections.abc.Mapping[str, Any]
    :returns: 物种字面量；缺失或非法时为 ``None``（RuleMatcher 将跳过物种过滤规则）。
    :rtype: SpeciesLiteral | None
    """
    pet_raw = payload.get("pet")
    if not isinstance(pet_raw, Mapping):
        return None
    species_raw = pet_raw.get("species")
    if species_raw in ("dog", "cat", "unknown"):
        return species_raw  # type: ignore[return-value]
    return None
