"""KB-INPUT-LEX LexiconLoader 单测。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xiaozhua_health_agent.input_lex import (
    INPUT_LEX_SCHEMA_VERSION,
    InputLexLoadError,
    LexiconLoader,
    load_input_lex_bundle,
    load_input_lex_bundle_from_json_text,
)
from xiaozhua_health_agent.paths import default_input_lex_path, project_root


@pytest.fixture
def default_lex_path() -> Path:
    """默认制品路径 fixture。

    :returns: input-lex.v1.json 绝对路径。
    :rtype: pathlib.Path
    """
    return default_input_lex_path()


def test_load_default_input_lex_bundle(default_lex_path: Path) -> None:
    """默认制品应成功加载且规则 ID 唯一、已按 priority 排序。"""
    bundle = load_input_lex_bundle(default_lex_path)
    assert bundle.meta.schema_version == INPUT_LEX_SCHEMA_VERSION
    assert bundle.meta.bundle_version == "1.2.0"
    assert len(bundle.rules) >= 40

    rule_ids = [rule.id for rule in bundle.rules]
    assert len(rule_ids) == len(set(rule_ids))

    priorities = [rule.priority for rule in bundle.rules]
    assert priorities == sorted(priorities)


def test_lexicon_loader_sync_and_static_helpers(default_lex_path: Path) -> None:
    """LexiconLoader 同步与无 IO 静态方法应一致。"""
    loader = LexiconLoader(default_lex_path)
    assert loader.resolved_path() == default_lex_path.resolve()

    text = default_lex_path.read_text(encoding="utf-8")
    from_loader = loader.load()
    from_text = LexiconLoader.from_json_text(text)
    from_mapping = LexiconLoader.from_json_mapping(json.loads(text))

    assert from_loader.meta.bundle_version == from_text.meta.bundle_version
    assert from_loader.rules[0].id == from_mapping.rules[0].id


@pytest.mark.asyncio
async def test_load_input_lex_bundle_async(default_lex_path: Path) -> None:
    """异步加载应与同步结果一致。"""
    loader = LexiconLoader(default_lex_path)
    sync_bundle = loader.load()
    async_bundle = await loader.load_async()
    assert sync_bundle.meta.bundle_version == async_bundle.meta.bundle_version
    assert len(sync_bundle.rules) == len(async_bundle.rules)


def test_load_missing_file_raises(tmp_path: Path) -> None:
    """缺失文件应抛出 InputLexLoadError。"""
    missing = tmp_path / "missing.json"
    with pytest.raises(InputLexLoadError, match="文件不存在"):
        load_input_lex_bundle(missing)


def test_invalid_schema_version_raises(default_lex_path: Path) -> None:
    """错误 schemaVersion 应被拒绝。"""
    payload = json.loads(default_lex_path.read_text(encoding="utf-8"))
    payload["meta"]["schemaVersion"] = "xiaozhua.kb_input_lex.v0"
    with pytest.raises(InputLexLoadError, match="schemaVersion"):
        load_input_lex_bundle_from_json_text(json.dumps(payload, ensure_ascii=False))


def test_duplicate_rule_id_raises(default_lex_path: Path) -> None:
    """重复 rules.id 应在 Pydantic 层失败。"""
    payload = json.loads(default_lex_path.read_text(encoding="utf-8"))
    payload["rules"].append(payload["rules"][0])
    with pytest.raises(InputLexLoadError, match="结构校验失败"):
        load_input_lex_bundle_from_json_text(json.dumps(payload, ensure_ascii=False))


def test_default_path_under_project_root() -> None:
    """未配置环境变量时默认路径应落在项目根 assets 下。"""
    path = default_input_lex_path()
    assert path == project_root() / "assets/kb-input-lex/input-lex.v1.json"
    assert path.is_file()
