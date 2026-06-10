"""mustMention 同义词表（KB-SYN 简化加载器，WP0 语义评测）。

V1 支持可选 JSON 制品；未提供时仅做关键字面匹配（归一化后子串）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Final, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from xiaozhua_health_agent.eval.text_corpus import normalize_text

# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------


class SynonymMapError(Exception):
    """同义词表加载或解析失败。"""


# ---------------------------------------------------------------------------
# 模型
# ---------------------------------------------------------------------------


class SynonymMap(BaseModel):
    """mustMention 关键词同义词查找表。

    :param global_synonyms: 全局 keyword → 同义表述列表（不含 keyword 自身）。
    :param by_primary_flag: 可选；primaryFlag → (keyword → 同义表述列表)。
    """

    model_config = ConfigDict(extra="forbid")

    global_synonyms: dict[str, list[str]] = Field(
        default_factory=dict,
        description="全局 keyword → 同义表述列表。",
    )
    by_primary_flag: dict[str, dict[str, list[str]]] = Field(
        default_factory=dict,
        description="按 primaryFlag 细分的同义词覆盖表。",
    )

    @model_validator(mode="after")
    def _normalize_keys(self) -> Self:
        """校验同义词条目非空字符串列表。

        :returns: 校验通过后的同一实例。
        :rtype: SynonymMap
        :raises ValueError: 存在空 keyword 或空同义词项时抛出。
        """
        for table_name, table in (
            ("global_synonyms", self.global_synonyms),
            *(
                (f"by_primary_flag[{flag}]", mapping)
                for flag, mapping in self.by_primary_flag.items()
            ),
        ):
            for keyword, synonyms in table.items():
                if not keyword.strip():
                    msg = f"{table_name} 中存在空 keyword。"
                    raise ValueError(msg)
                for item in synonyms:
                    if not item.strip():
                        msg = f"{table_name}[{keyword!r}] 中存在空同义词项。"
                        raise ValueError(msg)
        return self

    def expand_keyword(
        self,
        keyword: str,
        *,
        primary_flag: str | None = None,
    ) -> frozenset[str]:
        """将单个 mustMention 关键词扩展为归一化后的匹配候选集合。

        候选始终包含 keyword 自身（归一化后）；同义词来自 ``by_primary_flag``
        与 ``global_synonyms`` 的并集。

        :param keyword: case ``mustMention`` 中的原始关键词。
        :type keyword: str
        :param primary_flag: 可选 Triage Core ``primaryFlag``，用于细粒度同义词。
        :type primary_flag: str | None
        :returns: 归一化后的不可变候选集合；空 keyword 返回空集。
        :rtype: frozenset[str]
        """
        if not keyword.strip():
            return frozenset()

        raw_candidates: set[str] = {keyword}
        if primary_flag is not None:
            flag_table = self.by_primary_flag.get(primary_flag, {})
            raw_candidates.update(flag_table.get(keyword, []))
        raw_candidates.update(self.global_synonyms.get(keyword, []))

        normalized: set[str] = set()
        for item in raw_candidates:
            text = normalize_text(item)
            if text:
                normalized.add(text)
        return frozenset(normalized)


EMPTY_SYNONYM_MAP: Final[SynonymMap] = SynonymMap()
"""空同义词表：仅匹配 keyword 字面（归一化后）。"""


# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------


def load_synonym_map_from_json(json_text: str) -> SynonymMap:
    """从 JSON 字符串加载同义词表。

    期望结构::

        {
          "globalSynonyms": { "休息": ["歇一歇", "静养"] },
          "byPrimaryFlag": { "POST_EXERCISE": { "补水": ["喝水"] } }
        }

    :param json_text: UTF-8 JSON 文本。
    :type json_text: str
    :returns: 校验后的 ``SynonymMap`` 实例。
    :rtype: SynonymMap
    :raises SynonymMapError: JSON 解析失败时抛出。
    :raises pydantic.ValidationError: 结构不符合模型时由 Pydantic 抛出。
    """
    try:
        payload: Any = json.loads(json_text)
    except json.JSONDecodeError as exc:
        msg = f"KB-SYN JSON 解析失败：{exc.msg}（位置 line={exc.lineno}, col={exc.colno}）"
        raise SynonymMapError(msg) from exc

    if not isinstance(payload, dict):
        msg = f"KB-SYN 根节点必须为对象，实际为 {type(payload).__name__}"
        raise SynonymMapError(msg)

    global_raw = payload.get("globalSynonyms", payload.get("global_synonyms", {}))
    flag_raw = payload.get("byPrimaryFlag", payload.get("by_primary_flag", {}))

    return SynonymMap(
        global_synonyms=_coerce_synonym_table(global_raw, field_name="globalSynonyms"),
        by_primary_flag=_coerce_flag_table(flag_raw),
    )


def load_synonym_map(path: Path | str | None = None) -> SynonymMap:
    """从文件加载同义词表；路径为 ``None`` 时返回空表。

    :param path: JSON 文件路径；``None`` 表示不使用 KB-SYN 制品。
    :type path: pathlib.Path | str | None
    :returns: 同义词表实例。
    :rtype: SynonymMap
    :raises SynonymMapError: 文件不存在或读取失败时抛出。
    """
    if path is None:
        return EMPTY_SYNONYM_MAP

    resolved = Path(path)
    if not resolved.is_file():
        msg = f"KB-SYN 文件不存在：{resolved}"
        raise SynonymMapError(msg)

    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"读取 KB-SYN 文件失败：{resolved}（{exc}）"
        raise SynonymMapError(msg) from exc

    return load_synonym_map_from_json(text)


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _coerce_synonym_table(raw: Any, *, field_name: str) -> dict[str, list[str]]:
    """将 JSON 子对象规范化为 keyword → 同义词列表字典。

    :param raw: JSON 解析得到的原始值。
    :type raw: Any
    :param field_name: 字段名（用于错误消息）。
    :type field_name: str
    :returns: 规范化后的同义词表。
    :rtype: dict[str, list[str]]
    :raises SynonymMapError: 类型不符合预期时抛出。
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        msg = f"{field_name} 必须为对象，实际为 {type(raw).__name__}"
        raise SynonymMapError(msg)

    table: dict[str, list[str]] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            msg = f"{field_name} 的键必须为字符串，实际为 {type(key).__name__}"
            raise SynonymMapError(msg)
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            msg = f"{field_name}[{key!r}] 的值必须为字符串数组。"
            raise SynonymMapError(msg)
        table[key] = list(value)
    return table


def _coerce_flag_table(raw: Any) -> dict[str, dict[str, list[str]]]:
    """将 ``byPrimaryFlag`` JSON 子对象规范化。

    :param raw: JSON 解析得到的原始值。
    :type raw: Any
    :returns: primaryFlag → 同义词表 的嵌套字典。
    :rtype: dict[str, dict[str, list[str]]]
    :raises SynonymMapError: 类型不符合预期时抛出。
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        msg = f"byPrimaryFlag 必须为对象，实际为 {type(raw).__name__}"
        raise SynonymMapError(msg)

    result: dict[str, dict[str, list[str]]] = {}
    for flag, mapping in raw.items():
        if not isinstance(flag, str):
            msg = f"byPrimaryFlag 的键必须为字符串，实际为 {type(flag).__name__}"
            raise SynonymMapError(msg)
        result[flag] = _coerce_synonym_table(
            mapping,
            field_name=f"byPrimaryFlag[{flag}]",
        )
    return result
