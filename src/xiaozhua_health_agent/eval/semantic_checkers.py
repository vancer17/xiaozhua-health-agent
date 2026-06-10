"""语义维度纯检查器（WP0 语义评测 · §四）。

消费 ``CorpusBundle`` 与 ``CaseExpected`` 约束，产出 ``SemanticDimensionResult``。
不含编排逻辑；违规通过 ``semantic_violation`` 工厂构造。
"""

from __future__ import annotations

from collections.abc import Sequence

from xiaozhua_health_agent.eval.case_dataset import CaseExpected
from xiaozhua_health_agent.eval.forbidden_patterns import merge_forbidden_patterns
from xiaozhua_health_agent.eval.semantic_eval_types import (
    SemanticDimensionResult,
    SemanticEvalDimension,
)
from xiaozhua_health_agent.eval.semantic_violation import (
    SemanticTextHit,
    make_forbidden_pattern_hits_violation,
    make_must_mention_missing_violation,
    make_must_not_mention_hits_violation,
    make_safety_notice_required_missing_violation,
)
from xiaozhua_health_agent.eval.synonym_map import SynonymMap
from xiaozhua_health_agent.eval.text_corpus import (
    CorpusBundle,
    TextSegment,
    normalize_text,
)
from xiaozhua_health_agent.schemas import AgentOutput


def check_must_mention(
    *,
    expected: CaseExpected,
    corpus: CorpusBundle,
    synonym_map: SynonymMap,
    primary_flag: str | None = None,
    case_id: str | None = None,
) -> SemanticDimensionResult:
    """检查 ``mustMention`` 关键词是否均在合并语料中出现。

    每个关键词经 ``SynonymMap`` 扩展后，在 ``corpus.merged`` 中做子串匹配。

    :param expected: case 验收约束（读取 ``must_mention``）。
    :type expected: CaseExpected
    :param corpus: 已构建的语料包。
    :type corpus: CorpusBundle
    :param synonym_map: 同义词扩展表。
    :type synonym_map: SynonymMap
    :param primary_flag: 可选 primaryFlag，用于细粒度同义词。
    :type primary_flag: str | None
    :param case_id: 可选 caseId，写入违规 message。
    :type case_id: str | None
    :returns: ``must_mention`` 维度比对结果。
    :rtype: SemanticDimensionResult
    """
    keywords = expected.must_mention
    if len(keywords) == 0:
        return SemanticDimensionResult(
            dimension=SemanticEvalDimension.MUST_MENTION.value,
            check_applied=False,
            passed=None,
            missing_keywords=[],
            violations=[],
        )

    missing: list[str] = []
    for keyword in keywords:
        candidates = synonym_map.expand_keyword(keyword, primary_flag=primary_flag)
        if not candidates:
            missing.append(keyword)
            continue
        if not any(candidate in corpus.merged for candidate in candidates):
            missing.append(keyword)

    if len(missing) == 0:
        return SemanticDimensionResult(
            dimension=SemanticEvalDimension.MUST_MENTION.value,
            check_applied=True,
            passed=True,
            missing_keywords=[],
            violations=[],
        )

    return SemanticDimensionResult(
        dimension=SemanticEvalDimension.MUST_MENTION.value,
        check_applied=True,
        passed=False,
        missing_keywords=list(missing),
        violations=[
            make_must_mention_missing_violation(
                missing_keywords=missing,
                case_id=case_id,
            )
        ],
    )


def check_must_not_mention(
    *,
    expected: CaseExpected,
    segments: Sequence[TextSegment],
    case_id: str | None = None,
) -> SemanticDimensionResult:
    """检查 ``mustNotMention`` 关键词是否未出现在任一分段语料中。

    :param expected: case 验收约束（读取 ``must_not_mention``）。
    :type expected: CaseExpected
    :param segments: 分段语料列表。
    :type segments: collections.abc.Sequence[TextSegment]
    :param case_id: 可选 caseId。
    :type case_id: str | None
    :returns: ``must_not_mention`` 维度比对结果。
    :rtype: SemanticDimensionResult
    """
    keywords = expected.must_not_mention
    if len(keywords) == 0:
        return SemanticDimensionResult(
            dimension=SemanticEvalDimension.MUST_NOT_MENTION.value,
            check_applied=False,
            passed=None,
            missing_keywords=[],
            violations=[],
        )

    hits: list[SemanticTextHit] = []
    for keyword in keywords:
        normalized_keyword = normalize_text(keyword)
        if not normalized_keyword:
            continue
        for segment in segments:
            index = segment.text.find(normalized_keyword)
            if index >= 0:
                hits.append(
                    SemanticTextHit(
                        keyword=keyword,
                        field_path=segment.path,
                        snippet=_extract_snippet(
                            segment.text, index, len(normalized_keyword)
                        ),
                    )
                )

    if len(hits) == 0:
        return SemanticDimensionResult(
            dimension=SemanticEvalDimension.MUST_NOT_MENTION.value,
            check_applied=True,
            passed=True,
            missing_keywords=[],
            violations=[],
        )

    return SemanticDimensionResult(
        dimension=SemanticEvalDimension.MUST_NOT_MENTION.value,
        check_applied=True,
        passed=False,
        missing_keywords=[],
        violations=[
            make_must_not_mention_hits_violation(
                hits=hits,
                case_id=case_id,
            )
        ],
    )


def check_forbidden_patterns(
    *,
    segments: Sequence[TextSegment],
    patterns: Sequence[str] | None = None,
    case_id: str | None = None,
) -> SemanticDimensionResult:
    """检查全局禁止 pattern 是否出现在任一分段语料中。

    :param segments: 分段语料列表。
    :type segments: collections.abc.Sequence[TextSegment]
    :param patterns: 可选 pattern 列表；省略时合并 schema 基线与默认扩展表。
    :type patterns: collections.abc.Sequence[str] | None
    :param case_id: 可选 caseId。
    :type case_id: str | None
    :returns: ``forbidden_pattern`` 维度比对结果。
    :rtype: SemanticDimensionResult
    """
    resolved_patterns = (
        merge_forbidden_patterns() if patterns is None else tuple(patterns)
    )

    hits: list[SemanticTextHit] = []
    for pattern in resolved_patterns:
        normalized_pattern = normalize_text(pattern)
        if not normalized_pattern:
            continue
        for segment in segments:
            index = segment.text.find(normalized_pattern)
            if index >= 0:
                hits.append(
                    SemanticTextHit(
                        keyword=pattern,
                        field_path=segment.path,
                        snippet=_extract_snippet(
                            segment.text,
                            index,
                            len(normalized_pattern),
                        ),
                    )
                )

    if len(hits) == 0:
        return SemanticDimensionResult(
            dimension=SemanticEvalDimension.FORBIDDEN_PATTERN.value,
            check_applied=True,
            passed=True,
            missing_keywords=[],
            violations=[],
        )

    return SemanticDimensionResult(
        dimension=SemanticEvalDimension.FORBIDDEN_PATTERN.value,
        check_applied=True,
        passed=False,
        missing_keywords=[],
        violations=[
            make_forbidden_pattern_hits_violation(
                hits=hits,
                case_id=case_id,
            )
        ],
    )


def check_safety_notice(
    *,
    expected: CaseExpected,
    output: AgentOutput,
    min_length: int,
    case_id: str | None = None,
) -> SemanticDimensionResult:
    """检查 ``safetyNoticeRequired`` 与 ``safetyNotice`` 字段是否满足 case 约束。

    当 ``expected.safety_notice_required`` 为 ``False`` 时，本维度记为
    ``check_applied=False`` 且 ``passed=None``（不叠加内容质量门禁）。

    :param expected: case 验收约束。
    :type expected: CaseExpected
    :param output: 完整 Agent 输出。
    :type output: AgentOutput
    :param min_length: ``required=true`` 时 ``safetyNotice`` 的最小有效长度。
    :type min_length: int
    :param case_id: 可选 caseId。
    :type case_id: str | None
    :returns: ``safety_notice`` 维度比对结果。
    :rtype: SemanticDimensionResult
    :raises ValueError: ``min_length`` 小于 1 时抛出。
    """
    if min_length < 1:
        msg = "min_length 必须 >= 1。"
        raise ValueError(msg)

    if not expected.safety_notice_required:
        return SemanticDimensionResult(
            dimension=SemanticEvalDimension.SAFETY_NOTICE.value,
            check_applied=False,
            passed=None,
            missing_keywords=[],
            violations=[],
        )

    normalized = normalize_text(output.safety_notice)
    actual_length = len(normalized)
    if actual_length >= min_length:
        return SemanticDimensionResult(
            dimension=SemanticEvalDimension.SAFETY_NOTICE.value,
            check_applied=True,
            passed=True,
            missing_keywords=[],
            violations=[],
        )

    return SemanticDimensionResult(
        dimension=SemanticEvalDimension.SAFETY_NOTICE.value,
        check_applied=True,
        passed=False,
        missing_keywords=[],
        violations=[
            make_safety_notice_required_missing_violation(
                min_length=min_length,
                actual_length=actual_length,
                case_id=case_id,
            )
        ],
    )


def _extract_snippet(
    text: str, index: int, match_length: int, *, radius: int = 12
) -> str:
    """提取命中处前后若干字符作为报告摘录。

    :param text: 归一化后的分段全文。
    :type text: str
    :param index: 命中起始下标。
    :type index: int
    :param match_length: 命中子串长度。
    :type match_length: int
    :param radius: 前后各保留字符数。
    :type radius: int
    :returns: 摘录字符串。
    :rtype: str
    """
    start = max(0, index - radius)
    end = min(len(text), index + match_length + radius)
    return text[start:end]
