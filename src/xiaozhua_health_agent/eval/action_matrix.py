"""Action 矩阵期望 fixture 加载与推导（WP5 集成验收）。

制品：``assets/eval/action_matrix.v1.json``。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Self, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from xiaozhua_health_agent.eval.case_dataset import (
    EXPECTED_CASE_COUNT,
    CaseRecord,
    HealthTriageDataset,
    load_health_triage_dataset,
)
from xiaozhua_health_agent.paths import (
    default_action_matrix_path,
    default_kb_action_path,
)
from xiaozhua_health_agent.schemas import ActionItem

ACTION_MATRIX_SCHEMA_VERSION: str = "xiaozhua.eval.action_matrix.v1"
"""action 矩阵 fixture 顶层 schemaVersion。"""

DEFAULT_PIPELINE_PROFILE: str = "mechanical_merge_v1"
"""V1 期望矩阵对应的管道 profile。"""


class ActionMatrixLoadError(Exception):
    """action 矩阵 fixture 加载或校验失败。"""


class ActionMatrixEntry(BaseModel):
    """单条 case 的行动路由期望。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    case_id: str = Field(alias="caseId")
    case_name: str = Field(alias="caseName")
    primary_flag: str = Field(alias="primaryFlag")
    primary_action_hint: str = Field(alias="primaryActionHint")
    primary_action: ActionItem = Field(alias="primaryAction")
    secondary_action: ActionItem | None = Field(default=None, alias="secondaryAction")
    notes: str | None = None


class ActionMatrixMeta(BaseModel):
    """fixture 元数据。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_version: str = Field(alias="schemaVersion")
    matrix_version: str = Field(alias="matrixVersion")
    description: str
    cases_dataset: str = Field(alias="casesDataset")
    expected_case_count: int = Field(alias="expectedCaseCount")
    pipeline_profile: str = Field(alias="pipelineProfile")


class ActionMatrixSources(BaseModel):
    """上游制品版本 pin。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    cases_path: str = Field(alias="casesPath")
    triage_bundle_version: str = Field(alias="triageBundleVersion")
    kb_action_path: str = Field(alias="kbActionPath")
    kb_action_bundle_version: str = Field(alias="kbActionBundleVersion")


class ActionMatrixSummary(BaseModel):
    """批级 sanity 统计（加载时可选校验）。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    hint_counts: dict[str, int] = Field(alias="hintCounts")
    primary_route_counts: dict[str, int] = Field(alias="primaryRouteCounts")
    with_secondary_action: int = Field(alias="withSecondaryAction")


class ActionMatrixFixture(BaseModel):
    """完整 action 矩阵期望制品。"""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    meta: ActionMatrixMeta
    sources: ActionMatrixSources
    summary: ActionMatrixSummary
    entries: list[ActionMatrixEntry]

    @model_validator(mode="after")
    def _validate_entry_shape(self) -> Self:
        """校验条目数量与 caseId 唯一性。

        :returns: 校验通过后的同一实例。
        :rtype: ActionMatrixFixture
        :raises ValueError: 条目数量或 caseId 不符合要求时抛出。
        """
        expected = self.meta.expected_case_count
        if len(self.entries) != expected:
            msg = f"entries 长度应为 {expected}，实际为 {len(self.entries)}。"
            raise ValueError(msg)

        seen: set[str] = set()
        for entry in self.entries:
            if entry.case_id in seen:
                msg = f"重复的 caseId：{entry.case_id!r}。"
                raise ValueError(msg)
            seen.add(entry.case_id)
        return self

    def entry_by_case_id(self) -> dict[str, ActionMatrixEntry]:
        """构建 caseId → 期望条目索引。

        :returns: caseId 到期望条目的映射。
        :rtype: dict[str, ActionMatrixEntry]
        """
        return {entry.case_id: entry for entry in self.entries}

    def case_ids(self) -> tuple[str, ...]:
        """按 fixture 顺序返回全部 caseId。

        :returns: caseId 元组。
        :rtype: tuple[str, ...]
        """
        return tuple(entry.case_id for entry in self.entries)


def load_action_matrix_from_json(payload: Mapping[str, Any]) -> ActionMatrixFixture:
    """从 JSON 根对象加载 action 矩阵 fixture。

    :param payload: ``action_matrix.v1.json`` 根对象。
    :type payload: collections.abc.Mapping[str, Any]
    :returns: 校验后的 fixture。
    :rtype: ActionMatrixFixture
    :raises ActionMatrixLoadError: schemaVersion 不匹配或结构非法时抛出。
    :raises pydantic.ValidationError: 字段类型不符合模型时由 Pydantic 抛出。
    """
    if payload.get("meta", {}).get("schemaVersion") != ACTION_MATRIX_SCHEMA_VERSION:
        msg = (
            f"不支持的 action 矩阵 schemaVersion："
            f"{payload.get('meta', {}).get('schemaVersion')!r}。"
        )
        raise ActionMatrixLoadError(msg)
    return ActionMatrixFixture.model_validate(payload)


def load_action_matrix(path: Path | str | None = None) -> ActionMatrixFixture:
    """从文件加载 action 矩阵 fixture。

    :param path: JSON 路径；``None`` 时使用 ``default_action_matrix_path()``。
    :type path: pathlib.Path | str | None
    :returns: 校验后的 fixture。
    :rtype: ActionMatrixFixture
    :raises ActionMatrixLoadError: 文件不存在或解析失败时抛出。
    """
    resolved = Path(path) if path is not None else default_action_matrix_path()
    if not resolved.is_file():
        msg = f"action 矩阵文件不存在：{resolved}"
        raise ActionMatrixLoadError(msg)
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"读取 action 矩阵文件失败：{resolved}（{exc}）"
        raise ActionMatrixLoadError(msg) from exc
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        msg = f"action 矩阵 JSON 解析失败：{exc.msg}"
        raise ActionMatrixLoadError(msg) from exc
    if not isinstance(payload, dict):
        msg = "action 矩阵根节点必须为对象。"
        raise ActionMatrixLoadError(msg)
    return load_action_matrix_from_json(payload)


def validate_action_matrix_against_kb_action(
    fixture: ActionMatrixFixture,
    *,
    kb_action_path: Path | str | None = None,
) -> None:
    """校验 fixture 每行 action 与 KB-ACTION 对 hint 的映射一致。

    :param fixture: 已加载的 action 矩阵。
    :type fixture: ActionMatrixFixture
    :param kb_action_path: 可选 KB-ACTION 路径。
    :type kb_action_path: pathlib.Path | str | None
    :raises ActionMatrixLoadError: 映射不一致时抛出。
    """
    from xiaozhua_health_agent.copy.kb_action_loader import load_kb_action_bundle

    kb = load_kb_action_bundle(kb_action_path)
    mismatches: list[str] = []
    for entry in fixture.entries:
        hint = entry.primary_action_hint
        mapping = kb.actions.get(hint)
        if mapping is None:
            mismatches.append(f"{entry.case_id}: 未注册的 hint {hint!r}")
            continue
        if mapping.label != entry.primary_action.label:
            mismatches.append(
                f"{entry.case_id}: primaryAction.label 期望 {mapping.label!r}，"
                f"fixture 为 {entry.primary_action.label!r}",
            )
        if mapping.route != entry.primary_action.route:
            mismatches.append(
                f"{entry.case_id}: primaryAction.route 期望 {mapping.route!r}，"
                f"fixture 为 {entry.primary_action.route!r}",
            )
        action_id = kb.secondary_by_primary_flag.get(entry.primary_flag)
        if action_id is None:
            if entry.secondary_action is not None:
                mismatches.append(
                    f"{entry.case_id}: fixture 有次行动但 KB-ACTION 无 secondary 映射",
                )
            continue
        secondary = kb.secondary_actions.get(action_id)
        if secondary is None:
            mismatches.append(
                f"{entry.case_id}: secondaryByPrimaryFlag 指向未注册 id {action_id!r}",
            )
            continue
        if entry.secondary_action is None:
            mismatches.append(f"{entry.case_id}: 缺少期望 secondaryAction")
            continue
        if entry.secondary_action.label != secondary.label:
            mismatches.append(
                f"{entry.case_id}: secondaryAction.label 不一致",
            )
        if entry.secondary_action.route != secondary.route:
            mismatches.append(
                f"{entry.case_id}: secondaryAction.route 不一致",
            )

    if mismatches:
        detail = "\n".join(f"  - {line}" for line in mismatches)
        msg = f"action 矩阵与 KB-ACTION 不一致：\n{detail}"
        raise ActionMatrixLoadError(msg)


def validate_action_matrix_against_policy_tables(
    fixture: ActionMatrixFixture,
) -> None:
    """校验 fixture 每行 hint 与 ``ACTION_BY_FLAG[primaryFlag]`` 一致。

    :param fixture: 已加载的 action 矩阵。
    :type fixture: ActionMatrixFixture
    :raises ActionMatrixLoadError: hint 与 policy 表不一致时抛出。
    """
    from xiaozhua_health_agent.triage.policy_data import ACTION_BY_FLAG
    from xiaozhua_health_agent.triage.triage_types import PrimaryFlagLiteral

    mismatches: list[str] = []
    for entry in fixture.entries:
        flag = cast(PrimaryFlagLiteral, entry.primary_flag)
        expected_hint = ACTION_BY_FLAG.get(flag)
        if expected_hint is None:
            mismatches.append(f"{entry.case_id}: 未知 primaryFlag {flag!r}")
            continue
        if entry.primary_action_hint != expected_hint:
            mismatches.append(
                f"{entry.case_id}: hint 期望 {expected_hint!r}，"
                f"fixture 为 {entry.primary_action_hint!r}",
            )
    if mismatches:
        detail = "\n".join(f"  - {line}" for line in mismatches)
        msg = f"action 矩阵与 ACTION_BY_FLAG 不一致：\n{detail}"
        raise ActionMatrixLoadError(msg)


def validate_action_matrix_summary(fixture: ActionMatrixFixture) -> None:
    """校验 ``summary`` 统计与 ``entries`` 一致。

    :param fixture: 已加载的 action 矩阵。
    :type fixture: ActionMatrixFixture
    :raises ActionMatrixLoadError: 统计不一致时抛出。
    """
    from collections import Counter

    hint_counts = Counter(entry.primary_action_hint for entry in fixture.entries)
    route_counts = Counter(entry.primary_action.route for entry in fixture.entries)
    with_secondary = sum(
        1 for entry in fixture.entries if entry.secondary_action is not None
    )

    errors: list[str] = []
    if dict(hint_counts) != fixture.summary.hint_counts:
        errors.append(
            f"hintCounts 不一致：fixture={fixture.summary.hint_counts} "
            f"computed={dict(hint_counts)}",
        )
    if dict(route_counts) != fixture.summary.primary_route_counts:
        errors.append(
            f"primaryRouteCounts 不一致：fixture={fixture.summary.primary_route_counts} "
            f"computed={dict(route_counts)}",
        )
    if with_secondary != fixture.summary.with_secondary_action:
        errors.append(
            f"withSecondaryAction 不一致：fixture={fixture.summary.with_secondary_action} "
            f"computed={with_secondary}",
        )
    if errors:
        msg = "action 矩阵 summary 与 entries 不一致：\n" + "\n".join(
            f"  - {e}" for e in errors
        )
        raise ActionMatrixLoadError(msg)


def validate_action_matrix_against_dataset(
    fixture: ActionMatrixFixture,
    dataset: HealthTriageDataset,
) -> None:
    """校验 fixture caseId 集合与 mock case 数据集一致。

    :param fixture: 已加载的 action 矩阵。
    :type fixture: ActionMatrixFixture
    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :raises ActionMatrixLoadError: caseId 集合不匹配时抛出。
    """
    fixture_ids = set(fixture.entry_by_case_id())
    dataset_ids = {case.case_id for case in dataset.cases}
    if fixture_ids != dataset_ids:
        missing = sorted(dataset_ids - fixture_ids)
        extra = sorted(fixture_ids - dataset_ids)
        msg = f"action 矩阵 caseId 与数据集不一致：missing={missing!r} extra={extra!r}"
        raise ActionMatrixLoadError(msg)


def validate_action_matrix_fixture(
    fixture: ActionMatrixFixture,
    *,
    dataset: HealthTriageDataset | None = None,
    kb_action_path: Path | str | None = None,
    check_source_pins: bool = True,
) -> None:
    """对 fixture 执行完整静态校验。

    :param fixture: 已加载的 action 矩阵。
    :type fixture: ActionMatrixFixture
    :param dataset: 可选 mock case 数据集。
    :type dataset: HealthTriageDataset | None
    :param kb_action_path: 可选 KB-ACTION 路径。
    :type kb_action_path: pathlib.Path | str | None
    :param check_source_pins: 是否校验 ``sources`` 与当前 bundle 版本 pin 一致。
    :type check_source_pins: bool
    :raises ActionMatrixLoadError: 任一校验失败时抛出。
    """
    if fixture.meta.schema_version != ACTION_MATRIX_SCHEMA_VERSION:
        msg = f"schemaVersion 应为 {ACTION_MATRIX_SCHEMA_VERSION!r}。"
        raise ActionMatrixLoadError(msg)
    if fixture.meta.expected_case_count != EXPECTED_CASE_COUNT:
        msg = f"expectedCaseCount 应为 {EXPECTED_CASE_COUNT}。"
        raise ActionMatrixLoadError(msg)

    validate_action_matrix_summary(fixture)
    validate_action_matrix_against_policy_tables(fixture)
    validate_action_matrix_against_kb_action(fixture, kb_action_path=kb_action_path)

    if dataset is not None:
        validate_action_matrix_against_dataset(fixture, dataset)

    if check_source_pins:
        from xiaozhua_health_agent.copy.kb_action_loader import load_kb_action_bundle
        from xiaozhua_health_agent.triage.policy_data import BUNDLE_VERSION

        kb = load_kb_action_bundle(kb_action_path)
        if fixture.sources.triage_bundle_version != BUNDLE_VERSION:
            msg = (
                f"sources.triageBundleVersion pin 过期："
                f"fixture={fixture.sources.triage_bundle_version!r} "
                f"runtime={BUNDLE_VERSION!r}"
            )
            raise ActionMatrixLoadError(msg)
        if fixture.sources.kb_action_bundle_version != kb.bundle_version:
            msg = (
                f"sources.kbActionBundleVersion pin 过期："
                f"fixture={fixture.sources.kb_action_bundle_version!r} "
                f"runtime={kb.bundle_version!r}"
            )
            raise ActionMatrixLoadError(msg)
        if fixture.sources.kb_action_path != "assets/kb-action/actions.v1.json":
            msg = "sources.kbActionPath 与默认制品路径不一致。"
            raise ActionMatrixLoadError(msg)


def derive_action_matrix_entry(case: CaseRecord) -> ActionMatrixEntry:
    """从单条 case 推导期望行动条目（用于 regenerate / 漂移检测）。

    :param case: mock case 记录。
    :type case: CaseRecord
    :returns: 推导的期望条目。
    :rtype: ActionMatrixEntry
    :raises ValueError: 输入解析失败时抛出。
    """
    from xiaozhua_health_agent.copy.action_mapper import (
        map_primary_action,
        map_secondary_action,
    )
    from xiaozhua_health_agent.copy.kb_action_loader import load_kb_action_bundle
    from xiaozhua_health_agent.parse import parse_input
    from xiaozhua_health_agent.triage import run_triage_core

    parsed = parse_input(case.input)
    if not parsed.passed or parsed.fact_sheet is None:
        msg = f"case {case.case_id!r} 输入解析失败。"
        raise ValueError(msg)

    triage = run_triage_core(parsed.fact_sheet)
    kb = load_kb_action_bundle()
    primary = map_primary_action(kb_action=kb, triage=triage)
    secondary = map_secondary_action(kb_action=kb, triage=triage)

    return ActionMatrixEntry(
        caseId=case.case_id,
        caseName=case.name,
        primaryFlag=triage.primary_flag,
        primaryActionHint=triage.primary_action_hint,
        primaryAction=primary,
        secondaryAction=secondary,
    )


def derive_action_matrix_entries(
    dataset: HealthTriageDataset,
) -> list[ActionMatrixEntry]:
    """从 mock case 数据集推导全部期望条目。

    :param dataset: mock case 数据集。
    :type dataset: HealthTriageDataset
    :returns: 与数据集顺序一致的期望条目列表。
    :rtype: list[ActionMatrixEntry]
    """
    return [derive_action_matrix_entry(case) for case in dataset.cases]


def load_validated_action_matrix(
    path: Path | str | None = None,
    *,
    dataset: HealthTriageDataset | None = None,
    check_source_pins: bool = True,
) -> ActionMatrixFixture:
    """加载 fixture 并执行完整静态校验。

    :param path: JSON 路径；省略时使用默认路径。
    :type path: pathlib.Path | str | None
    :param dataset: 可选 mock case 数据集。
    :type dataset: HealthTriageDataset | None
    :param check_source_pins: 是否校验 bundle 版本 pin。
    :type check_source_pins: bool
    :returns: 校验后的 fixture。
    :rtype: ActionMatrixFixture
    """
    resolved_dataset = dataset
    if resolved_dataset is None:
        resolved_dataset = load_health_triage_dataset()
    fixture = load_action_matrix(path)
    validate_action_matrix_fixture(
        fixture,
        dataset=resolved_dataset,
        kb_action_path=default_kb_action_path(),
        check_source_pins=check_source_pins,
    )
    return fixture


def entries_match_derived(
    fixture_entries: Sequence[ActionMatrixEntry],
    derived_entries: Sequence[ActionMatrixEntry],
) -> list[str]:
    """比较 fixture 条目与推导条目，返回差异描述列表。

    :param fixture_entries: fixture 中的期望条目。
    :type fixture_entries: collections.abc.Sequence[ActionMatrixEntry]
    :param derived_entries: 运行时推导条目。
    :type derived_entries: collections.abc.Sequence[ActionMatrixEntry]
    :returns: 差异说明；空列表表示完全一致。
    :rtype: list[str]
    """
    diffs: list[str] = []
    fixture_by_id = {entry.case_id: entry for entry in fixture_entries}
    derived_by_id = {entry.case_id: entry for entry in derived_entries}

    for case_id in sorted(set(fixture_by_id) | set(derived_by_id)):
        expected = fixture_by_id.get(case_id)
        actual = derived_by_id.get(case_id)
        if expected is None:
            diffs.append(f"{case_id}: fixture 缺少条目")
            continue
        if actual is None:
            diffs.append(f"{case_id}: 推导缺少条目")
            continue
        if expected.primary_flag != actual.primary_flag:
            diffs.append(
                f"{case_id}: primaryFlag {expected.primary_flag!r} != {actual.primary_flag!r}",
            )
        if expected.primary_action_hint != actual.primary_action_hint:
            diffs.append(
                f"{case_id}: hint {expected.primary_action_hint!r} != "
                f"{actual.primary_action_hint!r}",
            )
        if expected.primary_action.label != actual.primary_action.label:
            diffs.append(f"{case_id}: primaryAction.label 不一致")
        if expected.primary_action.route != actual.primary_action.route:
            diffs.append(
                f"{case_id}: primaryAction.route {expected.primary_action.route!r} != "
                f"{actual.primary_action.route!r}",
            )
        exp_sec = expected.secondary_action
        act_sec = actual.secondary_action
        if exp_sec is None and act_sec is None:
            continue
        if exp_sec is None or act_sec is None:
            diffs.append(f"{case_id}: secondaryAction 一方为 null")
            continue
        if exp_sec.label != act_sec.label or exp_sec.route != act_sec.route:
            diffs.append(f"{case_id}: secondaryAction 不一致")
    return diffs
