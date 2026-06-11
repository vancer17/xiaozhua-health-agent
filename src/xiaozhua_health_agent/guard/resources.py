"""ValidateContent 异步资源加载（KB-SYN 等 IO 密集路径）。"""

from __future__ import annotations

import asyncio
from pathlib import Path

from xiaozhua_health_agent.eval import (
    EMPTY_SYNONYM_MAP,
    SynonymMap,
    load_synonym_map,
)
from xiaozhua_health_agent.guard.guard_types import ContentGuardOptions
from xiaozhua_health_agent.paths import default_synonym_map_path

__all__ = [
    "load_synonym_map_async",
    "resolve_synonym_map_for_guard",
    "resolve_synonym_map_for_guard_async",
]


async def load_synonym_map_async(
    path: Path | str | None = None,
) -> SynonymMap:
    """异步从磁盘加载 KB-SYN 同义词表。

    文件读取在线程池中执行，避免阻塞事件循环。

    :param path: JSON 文件路径；``None`` 时返回 ``EMPTY_SYNONYM_MAP``。
    :type path: pathlib.Path | str | None
    :returns: 同义词表实例。
    :rtype: SynonymMap
    :raises SynonymMapError: 文件不存在或解析失败时由底层 loader 抛出。
    """

    def _load() -> SynonymMap:
        """在线程池中执行同步加载（闭包）。

        :returns: 同义词表。
        :rtype: SynonymMap
        """
        return load_synonym_map(path)

    return await asyncio.to_thread(_load)


async def resolve_synonym_map_for_guard_async(
    *,
    synonym_map: SynonymMap | None,
    options: ContentGuardOptions,
    synonym_map_path: Path | str | None = None,
) -> SynonymMap:
    """解析 ValidateContent 应使用的同义词表（异步）。

    :param synonym_map: 调用方已注入的同义词表；非 ``None`` 时直接返回。
    :type synonym_map: SynonymMap | None
    :param options: 守卫配置（读取 ``load_default_synonym_map``）。
    :type options: ContentGuardOptions
    :param synonym_map_path: 可选 KB-SYN 路径；省略时使用项目默认路径。
    :type synonym_map_path: pathlib.Path | str | None
    :returns: 解析后的同义词表。
    :rtype: SynonymMap
    """
    if synonym_map is not None:
        return synonym_map
    if not options.load_default_synonym_map:
        return EMPTY_SYNONYM_MAP
    resolved_path = (
        Path(synonym_map_path)
        if synonym_map_path is not None
        else default_synonym_map_path()
    )
    return await load_synonym_map_async(resolved_path)


def resolve_synonym_map_for_guard(
    *,
    synonym_map: SynonymMap | None,
    options: ContentGuardOptions,
    synonym_map_path: Path | str | None = None,
) -> SynonymMap:
    """解析 ValidateContent 应使用的同义词表（同步）。

    :param synonym_map: 调用方已注入的同义词表；非 ``None`` 时直接返回。
    :type synonym_map: SynonymMap | None
    :param options: 守卫配置。
    :type options: ContentGuardOptions
    :param synonym_map_path: 可选 KB-SYN 路径。
    :type synonym_map_path: pathlib.Path | str | None
    :returns: 解析后的同义词表。
    :rtype: SynonymMap
    """
    if synonym_map is not None:
        return synonym_map
    if not options.load_default_synonym_map:
        return EMPTY_SYNONYM_MAP
    resolved_path = (
        synonym_map_path if synonym_map_path is not None else default_synonym_map_path()
    )
    return load_synonym_map(resolved_path)
