"""Adapter 接口与实现。

- :class:`WooAdapter` / :class:`OdooAdapter` 为接口（Protocol）；
- :class:`MockAdapter` 为实现两个接口的测试替身（阶段 0 Mock 链路）；
- :class:`BaseAdapter` 为未来真实 Adapter 提供共享 HTTP 管道。
"""

from __future__ import annotations

from .base import BaseAdapter
from .core import CoreAdapter, HttpCoreAdapter
from .mock import MockAdapter, MockCoreAdapter
from .odoo import OdooAdapter
from .woo import WooAdapter

__all__ = [
    "BaseAdapter",
    "WooAdapter",
    "OdooAdapter",
    "CoreAdapter",
    "HttpCoreAdapter",
    "MockAdapter",
    "MockCoreAdapter",
]
