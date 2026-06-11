"""KB-INPUT-LEX enrich 审计构建与持久化（EnrichAudit）。

聚合 :class:`~xiaozhua_health_agent.input_lex.CorpusBuilder`、
:class:`~xiaozhua_health_agent.input_lex.RuleMatcher` 与
:class:`~xiaozhua_health_agent.input_lex.PatchMerger` 的阶段性产物，产出可序列化
:class:`~xiaozhua_health_agent.input_lex.InputLexEnrichAuditRecord`，并支持异步
磁盘持久化。本模块 **不** 执行口语匹配、补丁合并或医学裁决。
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from xiaozhua_health_agent.input_lex.input_lex_types import (
    DEFAULT_ENRICH_AUDIT_BUILD_OPTIONS,
    INPUT_LEX_ENRICH_AUDIT_SCHEMA_VERSION,
    InputLexAppendApplicationRecord,
    InputLexBundle,
    InputLexCorpusAuditSummary,
    InputLexEnrichAuditBuildOptions,
    InputLexEnrichAuditPersistOptions,
    InputLexEnrichAuditPersistResult,
    InputLexEnrichAuditRecord,
    InputLexFieldChangeAudit,
    InputLexMatchCorpus,
    InputLexMatchedPhraseAudit,
    InputLexMergeResult,
    InputLexPatchApplicationRecord,
    InputLexRuleHit,
    InputLexRuleHitAudit,
    InputLexRuleMatchResult,
    InputLexRuleMergeRecord,
)

__all__ = [
    "DEFAULT_ENRICH_AUDIT_BUILD_OPTIONS",
    "EnrichAudit",
    "EnrichAuditError",
    "build_enrich_audit_record",
    "build_enrich_audit_record_async",
    "persist_enrich_audit_record",
    "persist_enrich_audit_record_async",
    "serialize_enrich_audit_record_to_json",
    "serialize_enrich_audit_record_to_mapping",
]


class EnrichAuditError(Exception):
    """EnrichAudit 构建或持久化失败。"""


class EnrichAudit:
    """KB-INPUT-LEX enrich 全流程审计构建器。

    将 ``RuleMatcher`` 命中明细与 ``PatchMerger`` 合并记录聚合为
    :class:`InputLexEnrichAuditRecord`，并提供 JSON 序列化与异步磁盘写入。
    纯 CPU 构建逻辑；异步方法对构建与 IO 使用 ``asyncio.to_thread`` 隔离。
    """

    def build(
        self,
        *,
        match_result: InputLexRuleMatchResult,
        merge_result: InputLexMergeResult,
        corpus: InputLexMatchCorpus | None = None,
        original_payload: Mapping[str, Any] | None = None,
        bundle: InputLexBundle | None = None,
        options: InputLexEnrichAuditBuildOptions | None = None,
    ) -> InputLexEnrichAuditRecord:
        """从匹配与合并结果构建 enrich 审计记录（同步）。

        :param match_result: RuleMatcher 产出的命中列表与统计。
        :type match_result: InputLexRuleMatchResult
        :param merge_result: PatchMerger 产出的 enriched payload 与逐规则明细。
        :type merge_result: InputLexMergeResult
        :param corpus: 可选匹配语料快照，用于写入语料摘要。
        :type corpus: InputLexMatchCorpus | None
        :param original_payload: 可选原始 input JSON，用于提取 ``caseId`` /
            ``timestamp`` 及可选嵌入快照。
        :type original_payload: collections.abc.Mapping[str, Any] | None
        :param bundle: 可选词表快照，用于写入 ``agentBundlePin``。
        :type bundle: InputLexBundle | None
        :param options: 构建选项；省略时使用
            :data:`DEFAULT_ENRICH_AUDIT_BUILD_OPTIONS`。
        :type options: InputLexEnrichAuditBuildOptions | None
        :returns: 完整 enrich 审计记录。
        :rtype: InputLexEnrichAuditRecord
        """
        return build_enrich_audit_record(
            match_result=match_result,
            merge_result=merge_result,
            corpus=corpus,
            original_payload=original_payload,
            bundle=bundle,
            options=options,
        )

    async def build_async(
        self,
        *,
        match_result: InputLexRuleMatchResult,
        merge_result: InputLexMergeResult,
        corpus: InputLexMatchCorpus | None = None,
        original_payload: Mapping[str, Any] | None = None,
        bundle: InputLexBundle | None = None,
        options: InputLexEnrichAuditBuildOptions | None = None,
    ) -> InputLexEnrichAuditRecord:
        """从匹配与合并结果构建 enrich 审计记录（异步）。

        CPU 密集的聚合与快照嵌入在线程池中执行，避免阻塞事件循环。

        :param match_result: RuleMatcher 产出的命中列表与统计。
        :type match_result: InputLexRuleMatchResult
        :param merge_result: PatchMerger 产出的 enriched payload 与逐规则明细。
        :type merge_result: InputLexMergeResult
        :param corpus: 可选匹配语料快照。
        :type corpus: InputLexMatchCorpus | None
        :param original_payload: 可选原始 input JSON。
        :type original_payload: collections.abc.Mapping[str, Any] | None
        :param bundle: 可选词表快照。
        :type bundle: InputLexBundle | None
        :param options: 构建选项。
        :type options: InputLexEnrichAuditBuildOptions | None
        :returns: 完整 enrich 审计记录。
        :rtype: InputLexEnrichAuditRecord
        """

        def _build_sync() -> InputLexEnrichAuditRecord:
            return self.build(
                match_result=match_result,
                merge_result=merge_result,
                corpus=corpus,
                original_payload=original_payload,
                bundle=bundle,
                options=options,
            )

        return await asyncio.to_thread(_build_sync)

    @staticmethod
    def to_mapping(record: InputLexEnrichAuditRecord) -> dict[str, Any]:
        """将审计记录序列化为 JSON 可编码字典。

        :param record: enrich 审计记录。
        :type record: InputLexEnrichAuditRecord
        :returns: 与 JSON 往返兼容的映射。
        :rtype: dict[str, Any]
        """
        return serialize_enrich_audit_record_to_mapping(record)

    @staticmethod
    def to_json(
        record: InputLexEnrichAuditRecord,
        *,
        indent: int | None = None,
    ) -> str:
        """将审计记录序列化为 UTF-8 JSON 文本。

        :param record: enrich 审计记录。
        :type record: InputLexEnrichAuditRecord
        :param indent: 可选美化缩进；``None`` 为紧凑单行 JSON。
        :type indent: int | None
        :returns: JSON 字符串。
        :rtype: str
        """
        return serialize_enrich_audit_record_to_json(record, indent=indent)

    def persist(
        self,
        record: InputLexEnrichAuditRecord,
        options: InputLexEnrichAuditPersistOptions,
    ) -> InputLexEnrichAuditPersistResult:
        """将审计记录同步写入磁盘。

        :param record: 待持久化的 enrich 审计记录。
        :type record: InputLexEnrichAuditRecord
        :param options: 持久化路径与格式选项。
        :type options: InputLexEnrichAuditPersistOptions
        :returns: 写入结果摘要。
        :rtype: InputLexEnrichAuditPersistResult
        :raises EnrichAuditError: 目录创建或文件写入失败时抛出。
        """
        return persist_enrich_audit_record(record, options)

    async def persist_async(
        self,
        record: InputLexEnrichAuditRecord,
        options: InputLexEnrichAuditPersistOptions,
    ) -> InputLexEnrichAuditPersistResult:
        """将审计记录异步写入磁盘。

        文件 IO 在线程池中执行，避免阻塞事件循环。

        :param record: 待持久化的 enrich 审计记录。
        :type record: InputLexEnrichAuditRecord
        :param options: 持久化路径与格式选项。
        :type options: InputLexEnrichAuditPersistOptions
        :returns: 写入结果摘要。
        :rtype: InputLexEnrichAuditPersistResult
        :raises EnrichAuditError: 目录创建或文件写入失败时抛出。
        """

        def _persist_sync() -> InputLexEnrichAuditPersistResult:
            return self.persist(record, options)

        return await asyncio.to_thread(_persist_sync)


def build_enrich_audit_record(
    *,
    match_result: InputLexRuleMatchResult,
    merge_result: InputLexMergeResult,
    corpus: InputLexMatchCorpus | None = None,
    original_payload: Mapping[str, Any] | None = None,
    bundle: InputLexBundle | None = None,
    options: InputLexEnrichAuditBuildOptions | None = None,
) -> InputLexEnrichAuditRecord:
    """便捷函数：构建 enrich 审计记录（同步）。

    :param match_result: RuleMatcher 产出。
    :type match_result: InputLexRuleMatchResult
    :param merge_result: PatchMerger 产出。
    :type merge_result: InputLexMergeResult
    :param corpus: 可选语料快照。
    :type corpus: InputLexMatchCorpus | None
    :param original_payload: 可选原始 input JSON。
    :type original_payload: collections.abc.Mapping[str, Any] | None
    :param bundle: 可选词表快照（提供 ``meta.agentBundlePin``）。
    :type bundle: InputLexBundle | None
    :param options: 构建选项。
    :type options: InputLexEnrichAuditBuildOptions | None
    :returns: enrich 审计记录。
    :rtype: InputLexEnrichAuditRecord
    """
    effective_options = options or DEFAULT_ENRICH_AUDIT_BUILD_OPTIONS
    merge_by_rule_id = _index_merge_records_by_rule_id(merge_result.rule_records)
    rule_hits = _build_rule_hit_audits(
        match_result.hits,
        merge_by_rule_id=merge_by_rule_id,
    )
    field_changes = _build_field_change_audits(merge_result.rule_records)
    corpus_summary = _build_corpus_audit_summary(
        corpus,
        options=effective_options,
    )
    case_id, input_timestamp = _extract_input_identifiers(original_payload)

    original_snapshot: dict[str, Any] | None = None
    if effective_options.include_original_payload and original_payload is not None:
        original_snapshot = _snapshot_mapping(original_payload)

    enriched_snapshot: dict[str, Any] | None = None
    if effective_options.include_enriched_payload:
        enriched_snapshot = _snapshot_mapping(merge_result.enriched_payload)

    agent_bundle_pin = _resolve_agent_bundle_pin(bundle=bundle)

    return InputLexEnrichAuditRecord(
        audit_schema_version=INPUT_LEX_ENRICH_AUDIT_SCHEMA_VERSION,
        case_id=case_id,
        input_timestamp=input_timestamp,
        lex_bundle_version=merge_result.bundle_version,
        lex_schema_version=merge_result.schema_version,
        agent_bundle_pin=agent_bundle_pin,
        evaluated_rule_count=match_result.evaluated_rule_count,
        skipped_species_filter_count=match_result.skipped_species_filter_count,
        hit_count=merge_result.hit_count,
        applied_patch_count=merge_result.applied_patch_count,
        applied_append_count=merge_result.applied_append_count,
        rule_hits=rule_hits,
        field_changes=field_changes,
        corpus_summary=corpus_summary,
        original_payload=original_snapshot,
        enriched_payload=enriched_snapshot,
    )


async def build_enrich_audit_record_async(
    *,
    match_result: InputLexRuleMatchResult,
    merge_result: InputLexMergeResult,
    corpus: InputLexMatchCorpus | None = None,
    original_payload: Mapping[str, Any] | None = None,
    bundle: InputLexBundle | None = None,
    options: InputLexEnrichAuditBuildOptions | None = None,
) -> InputLexEnrichAuditRecord:
    """便捷函数：异步构建 enrich 审计记录。

    :param match_result: RuleMatcher 产出。
    :type match_result: InputLexRuleMatchResult
    :param merge_result: PatchMerger 产出。
    :type merge_result: InputLexMergeResult
    :param corpus: 可选语料快照。
    :type corpus: InputLexMatchCorpus | None
    :param original_payload: 可选原始 input JSON。
    :type original_payload: collections.abc.Mapping[str, Any] | None
    :param bundle: 可选词表快照。
    :type bundle: InputLexBundle | None
    :param options: 构建选项。
    :type options: InputLexEnrichAuditBuildOptions | None
    :returns: enrich 审计记录。
    :rtype: InputLexEnrichAuditRecord
    """

    def _build_sync() -> InputLexEnrichAuditRecord:
        return build_enrich_audit_record(
            match_result=match_result,
            merge_result=merge_result,
            corpus=corpus,
            original_payload=original_payload,
            bundle=bundle,
            options=options,
        )

    return await asyncio.to_thread(_build_sync)


def serialize_enrich_audit_record_to_mapping(
    record: InputLexEnrichAuditRecord,
) -> dict[str, Any]:
    """将 :class:`InputLexEnrichAuditRecord` 转为 JSON 可编码字典。

    :param record: enrich 审计记录。
    :type record: InputLexEnrichAuditRecord
    :returns: 用于 ``json.dumps`` 的映射。
    :rtype: dict[str, Any]
    """
    return _dump_pydantic_model(record)


def serialize_enrich_audit_record_to_json(
    record: InputLexEnrichAuditRecord,
    *,
    indent: int | None = None,
) -> str:
    """将 enrich 审计记录序列化为 UTF-8 JSON 字符串。

    :param record: enrich 审计记录。
    :type record: InputLexEnrichAuditRecord
    :param indent: 可选美化缩进。
    :type indent: int | None
    :returns: JSON 文本。
    :rtype: str
    """
    payload = serialize_enrich_audit_record_to_mapping(record)
    return json.dumps(payload, ensure_ascii=False, indent=indent)


def persist_enrich_audit_record(
    record: InputLexEnrichAuditRecord,
    options: InputLexEnrichAuditPersistOptions,
) -> InputLexEnrichAuditPersistResult:
    """将 enrich 审计记录同步写入磁盘。

    :param record: 待持久化记录。
    :type record: InputLexEnrichAuditRecord
    :param options: 持久化选项。
    :type options: InputLexEnrichAuditPersistOptions
    :returns: 写入结果。
    :rtype: InputLexEnrichAuditPersistResult
    :raises EnrichAuditError: IO 失败时抛出。
    """
    target_path = Path(options.path).expanduser().resolve()
    if options.ensure_parent_dirs:
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            msg = f"创建审计目录失败：{target_path.parent}（{exc}）"
            raise EnrichAuditError(msg) from exc

    text, appended = _format_persist_payload(record, options)
    encoding = "utf-8"
    try:
        if options.format == "jsonl":
            mode = "a" if options.append_when_jsonl else "w"
            with target_path.open(mode, encoding=encoding) as handle:
                handle.write(text)
        else:
            with target_path.open("w", encoding=encoding) as handle:
                handle.write(text)
    except OSError as exc:
        msg = f"写入 enrich 审计记录失败：{target_path}（{exc}）"
        raise EnrichAuditError(msg) from exc

    return InputLexEnrichAuditPersistResult(
        path=str(target_path),
        bytes_written=len(text.encode(encoding)),
        format=options.format,
        appended=appended,
    )


async def persist_enrich_audit_record_async(
    record: InputLexEnrichAuditRecord,
    options: InputLexEnrichAuditPersistOptions,
) -> InputLexEnrichAuditPersistResult:
    """将 enrich 审计记录异步写入磁盘。

    :param record: 待持久化记录。
    :type record: InputLexEnrichAuditRecord
    :param options: 持久化选项。
    :type options: InputLexEnrichAuditPersistOptions
    :returns: 写入结果。
    :rtype: InputLexEnrichAuditPersistResult
    :raises EnrichAuditError: IO 失败时抛出。
    """

    def _persist_sync() -> InputLexEnrichAuditPersistResult:
        return persist_enrich_audit_record(record, options)

    return await asyncio.to_thread(_persist_sync)


def _build_rule_hit_audits(
    hits: tuple[InputLexRuleHit, ...],
    *,
    merge_by_rule_id: dict[str, InputLexRuleMergeRecord],
) -> tuple[InputLexRuleHitAudit, ...]:
    """将 RuleMatcher 命中与 PatchMerger 逐规则记录对齐为审计摘要。

    :param hits: 按 priority 升序的命中列表。
    :type hits: tuple[InputLexRuleHit, ...]
    :param merge_by_rule_id: 规则 ID → 合并明细索引。
    :type merge_by_rule_id: dict[str, InputLexRuleMergeRecord]
    :returns: 逐规则审计摘要元组。
    :rtype: tuple[InputLexRuleHitAudit, ...]
    """
    audits: list[InputLexRuleHitAudit] = []
    for hit in hits:
        rule = hit.rule
        merge_record = merge_by_rule_id.get(rule.id)
        patch_apps = (
            merge_record.patch_applications
            if merge_record is not None
            else ()
        )
        append_apps = (
            merge_record.append_applications
            if merge_record is not None
            else ()
        )
        matched_phrases = tuple(
            InputLexMatchedPhraseAudit(
                raw_phrase=item.raw_phrase,
                normalized_phrase=item.normalized_phrase,
            )
            for item in hit.matched_phrases
        )
        audits.append(
            InputLexRuleHitAudit(
                rule_id=rule.id,
                intent=rule.intent,
                priority=rule.priority,
                rule_mode=rule.mode,
                maps_to_agent_rules=rule.maps_to_agent_rules,
                matched_phrases=matched_phrases,
                patch_applications=patch_apps,
                append_applications=append_apps,
                has_effective_change=_rule_has_effective_change(
                    patch_apps,
                    append_apps,
                ),
            ),
        )
    return tuple(audits)


def _build_field_change_audits(
    rule_records: tuple[InputLexRuleMergeRecord, ...],
) -> tuple[InputLexFieldChangeAudit, ...]:
    """从逐规则合并记录扁平化字段级变更审计。

    :param rule_records: PatchMerger 逐规则合并明细。
    :type rule_records: tuple[InputLexRuleMergeRecord, ...]
    :returns: 按规则处理顺序排列的字段变更列表。
    :rtype: tuple[InputLexFieldChangeAudit, ...]
    """
    changes: list[InputLexFieldChangeAudit] = []
    for merge_record in rule_records:
        for patch_app in merge_record.patch_applications:
            if patch_app.action != "applied":
                continue
            changes.append(
                InputLexFieldChangeAudit(
                    field_path=patch_app.field_path,
                    change_kind="patch",
                    source_rule_id=merge_record.rule_id,
                    previous_value=patch_app.previous_value,
                    new_value=patch_app.new_value,
                ),
            )
        for append_app in merge_record.append_applications:
            if len(append_app.appended_values) == 0:
                continue
            changes.append(
                InputLexFieldChangeAudit(
                    field_path=append_app.field_path,
                    change_kind="append",
                    source_rule_id=merge_record.rule_id,
                    previous_value=list(append_app.previous_values),
                    new_value=list(append_app.new_values),
                ),
            )
    return tuple(changes)


def _build_corpus_audit_summary(
    corpus: InputLexMatchCorpus | None,
    *,
    options: InputLexEnrichAuditBuildOptions,
) -> InputLexCorpusAuditSummary | None:
    """构建可选语料审计摘要。

    :param corpus: 匹配语料；为 ``None`` 或未启用摘要时返回 ``None``。
    :type corpus: InputLexMatchCorpus | None
    :param options: 构建选项。
    :type options: InputLexEnrichAuditBuildOptions
    :returns: 语料摘要或 ``None``。
    :rtype: InputLexCorpusAuditSummary | None
    """
    if corpus is None or not options.include_corpus_summary:
        return None

    preview = _truncate_text_preview(
        corpus.merged,
        max_chars=options.corpus_merged_preview_max_chars,
    )
    return InputLexCorpusAuditSummary(
        segment_count=len(corpus.segments),
        merged_text_length=len(corpus.merged),
        merged_text_preview=preview,
        match_sources=corpus.match_sources,
    )


def _index_merge_records_by_rule_id(
    rule_records: tuple[InputLexRuleMergeRecord, ...],
) -> dict[str, InputLexRuleMergeRecord]:
    """将逐规则合并记录索引为 rule_id → 记录映射。

    :param rule_records: PatchMerger 逐规则明细。
    :type rule_records: tuple[InputLexRuleMergeRecord, ...]
    :returns: 规则 ID 索引；重复 ID 时保留首次出现。
    :rtype: dict[str, InputLexRuleMergeRecord]
    """
    indexed: dict[str, InputLexRuleMergeRecord] = {}
    for record in rule_records:
        if record.rule_id not in indexed:
            indexed[record.rule_id] = record
    return indexed


def _rule_has_effective_change(
    patch_applications: tuple[InputLexPatchApplicationRecord, ...],
    append_applications: tuple[InputLexAppendApplicationRecord, ...],
) -> bool:
    """判断单条规则是否产生有效字段变更。

    :param patch_applications: 标量补丁应用记录。
    :type patch_applications: tuple[InputLexPatchApplicationRecord, ...]
    :param append_applications: 数组追加应用记录。
    :type append_applications: tuple[InputLexAppendApplicationRecord, ...]
    :returns: 存在已应用补丁或非空追加时为 ``True``。
    :rtype: bool
    """
    if any(item.action == "applied" for item in patch_applications):
        return True
    return any(len(item.appended_values) > 0 for item in append_applications)


def _extract_input_identifiers(
    original_payload: Mapping[str, Any] | None,
) -> tuple[str | None, str | None]:
    """从原始 input JSON 提取 ``caseId`` 与 ``timestamp`` 字符串。

    :param original_payload: 原始入参映射。
    :type original_payload: collections.abc.Mapping[str, Any] | None
    :returns: ``(case_id, input_timestamp_iso)`` 元组。
    :rtype: tuple[str | None, str | None]
    """
    if original_payload is None:
        return None, None

    case_id_raw = original_payload.get("caseId")
    case_id = case_id_raw if isinstance(case_id_raw, str) and case_id_raw.strip() else None

    timestamp_raw = original_payload.get("timestamp")
    input_timestamp = _coerce_timestamp_to_iso_string(timestamp_raw)
    return case_id, input_timestamp


def _coerce_timestamp_to_iso_string(value: object) -> str | None:
    """将入参 ``timestamp`` 规范化为 ISO-8601 字符串。

    :param value: JSON 中的 timestamp 字段（字符串或 datetime）。
    :type value: object
    :returns: ISO 字符串；无法解析时为 ``None``。
    :rtype: str | None
    """
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def _resolve_agent_bundle_pin(
    *,
    bundle: InputLexBundle | None,
) -> str:
    """从词表快照解析 ``agentBundlePin``。

    :param bundle: 可选 KB-INPUT-LEX 制品；省略时返回 ``unknown``。
    :type bundle: InputLexBundle | None
    :returns: ``meta.agentBundlePin`` 或占位 ``unknown``。
    :rtype: str
    """
    if bundle is None:
        return "unknown"
    pin = bundle.meta.agent_bundle_pin.strip()
    return pin if pin else "unknown"


def _snapshot_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    """深拷贝式快照 JSON 映射（仅一层 dict 复制，嵌套结构共享引用）。

    审计嵌入用途；若需完全隔离应在上游传入 ``copy.deepcopy`` 后的对象。

    :param payload: 待快照映射。
    :type payload: collections.abc.Mapping[str, Any]
    :returns: 可变字典快照。
    :rtype: dict[str, Any]
    """
    return dict(payload)


def _truncate_text_preview(text: str, *, max_chars: int) -> str:
    """截断语料预览文本。

    :param text: 原始合并语料。
    :type text: str
    :param max_chars: 最大保留字符数；``0`` 返回空串。
    :type max_chars: int
    :returns: 预览文本（超长时追加 ``…``）。
    :rtype: str
    """
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars == 1:
        return "…"
    return f"{text[: max_chars - 1]}…"


def _format_persist_payload(
    record: InputLexEnrichAuditRecord,
    options: InputLexEnrichAuditPersistOptions,
) -> tuple[str, bool]:
    """按持久化选项格式化审计记录文本。

    :param record: enrich 审计记录。
    :type record: InputLexEnrichAuditRecord
    :param options: 持久化选项。
    :type options: InputLexEnrichAuditPersistOptions
    :returns: ``(text, appended)`` 元组；``appended`` 仅对 jsonl 有意义。
    :rtype: tuple[str, bool]
    """
    if options.format == "jsonl":
        line = serialize_enrich_audit_record_to_json(record, indent=None)
        appended = options.append_when_jsonl
        suffix = "\n" if not line.endswith("\n") else ""
        return f"{line}{suffix}", appended

    body = serialize_enrich_audit_record_to_json(
        record,
        indent=options.json_indent,
    )
    return body, False


def _dump_pydantic_model(model: BaseModel) -> dict[str, Any]:
    """将 Pydantic 模型导出为 JSON 兼容字典。

    :param model: 任意严格 Pydantic 模型实例。
    :type model: pydantic.BaseModel
    :returns: JSON 可编码映射。
    :rtype: dict[str, Any]
    """
    return model.model_dump(by_alias=True, mode="json")
