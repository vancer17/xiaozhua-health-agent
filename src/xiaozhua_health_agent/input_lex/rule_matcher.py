"""KB-INPUT-LEX 规则短语匹配器（RuleMatcher）。

对已构建的 :class:`~xiaozhua_health_agent.input_lex.InputLexMatchCorpus` 执行
词表 ``rules[]`` 子串匹配，产出按 ``priority`` 排序的命中列表，供后续
``PatchMerger`` 合并 ``patches`` / ``append``。本模块 **不** 写入
``AgentInput`` 或执行医学裁决。
"""

from __future__ import annotations

import asyncio

from xiaozhua_health_agent.input_lex.corpus_builder import normalize_match_text
from xiaozhua_health_agent.input_lex.input_lex_types import (
    InputLexBundle,
    InputLexMatchCorpus,
    InputLexMatchDefaults,
    InputLexPhraseMatchDetail,
    InputLexRule,
    InputLexRuleHit,
    InputLexRuleMatchResult,
)
from xiaozhua_health_agent.schemas import SpeciesLiteral

__all__ = [
    "RuleMatcher",
    "collect_matched_phrases_for_rule",
    "match_input_lex_rules",
    "match_input_lex_rules_async",
    "match_single_input_lex_rule",
    "phrase_is_eligible_for_matching",
    "phrase_matches_corpus",
    "rule_passes_species_filter",
]


class RuleMatcher:
    """KB-INPUT-LEX 规则短语匹配器。

    按词表 ``rules_by_priority`` 顺序，在合并语料上对每条规则的
    ``match.phrases`` 执行子串匹配；支持可选 ``species`` 过滤。纯 CPU
    逻辑；异步方法通过线程池执行，避免大批量规则评估阻塞事件循环。
    """

    def __init__(self, bundle: InputLexBundle) -> None:
        """绑定词表快照。

        :param bundle: 已加载的 KB-INPUT-LEX 制品。
        :type bundle: InputLexBundle
        """
        self._bundle: InputLexBundle = bundle

    @property
    def bundle(self) -> InputLexBundle:
        """返回构造时绑定的词表快照。

        :returns: 不可变词表制品。
        :rtype: InputLexBundle
        """
        return self._bundle

    def match(
        self,
        corpus: InputLexMatchCorpus,
        *,
        species: SpeciesLiteral | None = None,
    ) -> InputLexRuleMatchResult:
        """对语料同步执行全表规则匹配。

        :param corpus: 由 :class:`~xiaozhua_health_agent.input_lex.CorpusBuilder`
            构建的归一化语料。
        :type corpus: InputLexMatchCorpus
        :param species: 可选宠物物种（``dog`` / ``cat`` / ``unknown``），用于
            评估规则级 ``species`` 过滤；省略时跳过所有带物种限制的规则。
        :type species: SpeciesLiteral | None
        :returns: 命中规则与统计信息。
        :rtype: InputLexRuleMatchResult
        """
        return _match_rules_against_corpus(
            self._bundle,
            corpus,
            species=species,
        )

    async def match_async(
        self,
        corpus: InputLexMatchCorpus,
        *,
        species: SpeciesLiteral | None = None,
    ) -> InputLexRuleMatchResult:
        """对语料异步执行全表规则匹配。

        匹配逻辑在线程池中运行，适用于与 IO 密集的语料构建串联时避免
        阻塞事件循环。

        :param corpus: 归一化匹配语料。
        :type corpus: InputLexMatchCorpus
        :param species: 可选物种过滤上下文。
        :type species: SpeciesLiteral | None
        :returns: 命中规则与统计信息。
        :rtype: InputLexRuleMatchResult
        """

        def _match_sync() -> InputLexRuleMatchResult:
            """在线程池中执行同步匹配（闭包）。

            :returns: 规则匹配结果。
            :rtype: InputLexRuleMatchResult
            """
            return self.match(corpus, species=species)

        return await asyncio.to_thread(_match_sync)

    def match_single_rule(
        self,
        rule: InputLexRule,
        corpus: InputLexMatchCorpus,
        *,
        species: SpeciesLiteral | None = None,
    ) -> InputLexRuleHit | None:
        """对单条规则执行短语匹配（调试与单测用）。

        :param rule: 待评估的 LEX 规则。
        :type rule: InputLexRule
        :param corpus: 归一化匹配语料。
        :type corpus: InputLexMatchCorpus
        :param species: 可选物种过滤上下文。
        :type species: SpeciesLiteral | None
        :returns: 至少命中一个短语时返回命中记录；否则为 ``None``。
        :rtype: InputLexRuleHit | None
        """
        if not rule_passes_species_filter(rule, species):
            return None
        matched = collect_matched_phrases_for_rule(
            rule,
            corpus,
            match_defaults=corpus.match_defaults,
        )
        if not matched:
            return None
        return InputLexRuleHit(rule=rule, matched_phrases=matched)


def match_input_lex_rules(
    bundle: InputLexBundle,
    corpus: InputLexMatchCorpus,
    *,
    species: SpeciesLiteral | None = None,
) -> InputLexRuleMatchResult:
    """便捷函数：对语料执行全表规则匹配。

    :param bundle: KB-INPUT-LEX 词表快照。
    :type bundle: InputLexBundle
    :param corpus: 归一化匹配语料。
    :type corpus: InputLexMatchCorpus
    :param species: 可选物种过滤上下文。
    :type species: SpeciesLiteral | None
    :returns: 规则匹配结果。
    :rtype: InputLexRuleMatchResult
    """
    return RuleMatcher(bundle).match(corpus, species=species)


async def match_input_lex_rules_async(
    bundle: InputLexBundle,
    corpus: InputLexMatchCorpus,
    *,
    species: SpeciesLiteral | None = None,
) -> InputLexRuleMatchResult:
    """便捷函数：异步对语料执行全表规则匹配。

    :param bundle: KB-INPUT-LEX 词表快照。
    :type bundle: InputLexBundle
    :param corpus: 归一化匹配语料。
    :type corpus: InputLexMatchCorpus
    :param species: 可选物种过滤上下文。
    :type species: SpeciesLiteral | None
    :returns: 规则匹配结果。
    :rtype: InputLexRuleMatchResult
    """
    return await RuleMatcher(bundle).match_async(corpus, species=species)


def match_single_input_lex_rule(
    rule: InputLexRule,
    corpus: InputLexMatchCorpus,
    *,
    species: SpeciesLiteral | None = None,
) -> InputLexRuleHit | None:
    """便捷函数：对单条规则执行短语匹配。

    :param rule: 待评估的 LEX 规则。
    :type rule: InputLexRule
    :param corpus: 归一化匹配语料。
    :type corpus: InputLexMatchCorpus
    :param species: 可选物种过滤上下文。
    :type species: SpeciesLiteral | None
    :returns: 命中记录或 ``None``。
    :rtype: InputLexRuleHit | None
    """
    match_defaults = corpus.match_defaults
    if not rule_passes_species_filter(rule, species):
        return None
    matched = collect_matched_phrases_for_rule(
        rule,
        corpus,
        match_defaults=match_defaults,
    )
    if not matched:
        return None
    return InputLexRuleHit(rule=rule, matched_phrases=matched)


def rule_passes_species_filter(
    rule: InputLexRule,
    species: SpeciesLiteral | None,
) -> bool:
    """判断规则是否应参与当前物种上下文下的匹配。

    :param rule: LEX 规则。
    :type rule: InputLexRule
    :param species: 宠物物种；为 ``None`` 时仅允许无 ``species`` 限制的规则。
    :type species: SpeciesLiteral | None
    :returns: 应评估短语匹配时为 ``True``。
    :rtype: bool
    """
    if rule.species is None:
        return True
    if species is None:
        return False
    return species in rule.species


def phrase_is_eligible_for_matching(
    normalized_phrase: str,
    *,
    match_defaults: InputLexMatchDefaults,
) -> bool:
    """判断归一化短语是否满足 ``minPhraseLength`` 参与匹配。

    :param normalized_phrase: 已归一化的候选短语。
    :type normalized_phrase: str
    :param match_defaults: 全局匹配默认参数。
    :type match_defaults: InputLexMatchDefaults
    :returns: 长度达标且非空时为 ``True``。
    :rtype: bool
    """
    if not normalized_phrase:
        return False
    return len(normalized_phrase) >= match_defaults.min_phrase_length


def phrase_matches_corpus(
    normalized_phrase: str,
    corpus: InputLexMatchCorpus,
) -> bool:
    """判断归一化短语是否为合并语料的子串。

    :param normalized_phrase: 已按语料相同 ``match_defaults`` 归一化的短语。
    :type normalized_phrase: str
    :param corpus: 匹配语料包。
    :type corpus: InputLexMatchCorpus
    :returns: 子串命中时为 ``True``。
    :rtype: bool
    """
    return corpus.contains_normalized_phrase(normalized_phrase)


def collect_matched_phrases_for_rule(
    rule: InputLexRule,
    corpus: InputLexMatchCorpus,
    *,
    match_defaults: InputLexMatchDefaults,
) -> tuple[InputLexPhraseMatchDetail, ...]:
    """收集单条规则在语料中命中的所有短语明细。

    按 ``rule.match.phrases`` 声明顺序遍历；同一短语只记录一次。

    :param rule: LEX 规则。
    :type rule: InputLexRule
    :param corpus: 归一化匹配语料。
    :type corpus: InputLexMatchCorpus
    :param match_defaults: 短语归一化参数（应与构建语料时一致）。
    :type match_defaults: InputLexMatchDefaults
    :returns: 命中短语明细元组；无命中时为空元组。
    :rtype: tuple[InputLexPhraseMatchDetail, ...]
    """
    if match_defaults.mode != "substring":
        msg = f"暂不支持的 matchDefaults.mode：{match_defaults.mode!r}"
        raise ValueError(msg)

    matched: list[InputLexPhraseMatchDetail] = []
    seen_normalized: set[str] = set()

    for raw_phrase in rule.match.phrases:
        normalized = normalize_match_text(
            raw_phrase,
            match_defaults=match_defaults,
        )
        if not phrase_is_eligible_for_matching(
            normalized,
            match_defaults=match_defaults,
        ):
            continue
        if normalized in seen_normalized:
            continue
        if not phrase_matches_corpus(normalized, corpus):
            continue
        seen_normalized.add(normalized)
        matched.append(
            InputLexPhraseMatchDetail(
                raw_phrase=raw_phrase,
                normalized_phrase=normalized,
            )
        )

    return tuple(matched)


def _match_rules_against_corpus(
    bundle: InputLexBundle,
    corpus: InputLexMatchCorpus,
    *,
    species: SpeciesLiteral | None,
) -> InputLexRuleMatchResult:
    """对语料评估词表全部规则并汇总命中（内部辅助）。

    :param bundle: 词表快照。
    :type bundle: InputLexBundle
    :param corpus: 归一化匹配语料。
    :type corpus: InputLexMatchCorpus
    :param species: 可选物种过滤上下文。
    :type species: SpeciesLiteral | None
    :returns: 规则匹配结果。
    :rtype: InputLexRuleMatchResult
    """
    hits: list[InputLexRuleHit] = []
    evaluated_rule_count = 0
    skipped_species_filter_count = 0

    for rule in bundle.rules_by_priority():
        if not rule_passes_species_filter(rule, species):
            skipped_species_filter_count += 1
            continue
        evaluated_rule_count += 1
        matched_phrases = collect_matched_phrases_for_rule(
            rule,
            corpus,
            match_defaults=corpus.match_defaults,
        )
        if not matched_phrases:
            continue
        hits.append(
            InputLexRuleHit(
                rule=rule,
                matched_phrases=matched_phrases,
            )
        )

    return InputLexRuleMatchResult(
        hits=tuple(hits),
        bundle_version=bundle.meta.bundle_version,
        schema_version=bundle.meta.schema_version,
        evaluated_rule_count=evaluated_rule_count,
        skipped_species_filter_count=skipped_species_filter_count,
    )
