"""③-1 知识资产聚合加载与默认单例缓存。"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from xiaozhua_health_agent.copy.copy_types import CopyKnowledgeBundle
from xiaozhua_health_agent.copy.kb_action_loader import load_kb_action_bundle
from xiaozhua_health_agent.copy.kb_forbid_loader import load_kb_forbid_bundle
from xiaozhua_health_agent.copy.kb_tpl_loader import load_kb_tpl_bundle


def load_copy_knowledge_bundle(
    *,
    kb_tpl_config_dir: Path | str | None = None,
    kb_action_path: Path | str | None = None,
    kb_forbid_path: Path | str | None = None,
) -> CopyKnowledgeBundle:
    """加载 ③-1 所需的全部知识资产。

    :param kb_tpl_config_dir: KB-TPL 配置目录；``None`` 使用项目默认路径。
    :type kb_tpl_config_dir: pathlib.Path | str | None
    :param kb_action_path: KB-ACTION JSON 路径；``None`` 使用项目默认路径。
    :type kb_action_path: pathlib.Path | str | None
    :param kb_forbid_path: KB-FORBID JSON 路径；``None`` 使用项目默认路径。
    :type kb_forbid_path: pathlib.Path | str | None
    :returns: 聚合知识包。
    :rtype: CopyKnowledgeBundle
    """
    return CopyKnowledgeBundle(
        kb_tpl=load_kb_tpl_bundle(kb_tpl_config_dir),
        kb_action=load_kb_action_bundle(kb_action_path),
        kb_forbid=load_kb_forbid_bundle(kb_forbid_path),
    )


@lru_cache(maxsize=1)
def load_default_copy_knowledge_bundle() -> CopyKnowledgeBundle:
    """加载并缓存默认路径下的知识资产聚合包。

    进程内首次调用后结果不可变；测试需调用 ``clear_default_copy_knowledge_cache`` 刷新。

    :returns: 默认 ``CopyKnowledgeBundle`` 单例。
    :rtype: CopyKnowledgeBundle
    """
    return load_copy_knowledge_bundle()


def clear_default_copy_knowledge_cache() -> None:
    """清空 ``load_default_copy_knowledge_bundle`` 的 LRU 缓存。

    :rtype: None
    """
    load_default_copy_knowledge_bundle.cache_clear()
