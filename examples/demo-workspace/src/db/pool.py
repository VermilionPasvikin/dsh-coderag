"""Connection pool for the demo workspace."""

from __future__ import annotations


def init_pool(size: int) -> list[object]:
    """初始化连接池。"""
    return [object() for _ in range(size)]
