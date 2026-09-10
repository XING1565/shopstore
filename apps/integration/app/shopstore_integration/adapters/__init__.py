"""Adapter 接口与实现。

- :class:`WooAdapter` / :class:`OdooAdapter` 为接口（Protocol）；
- :class:`MockAdapter` 为实现两个接口的测试替身（阶段 0 Mock 链路）；
- :class:`BaseAdapter` 为真实 Adapter 提供共享 HTTP 管道；
- :class:`HttpOdooAdapter` 为真实 Odoo Adapter（JSON-RPC，ISSUE-0107）；
- :class:`CoreAdapter` / :class:`HttpCoreAdapter` 为 Integration -> Core 反向调用
  （履约状态回传，ISSUE-0108）。
"""

from __future__ import annotations

from .base import BaseAdapter
from .core import CoreAdapter, HttpCoreAdapter
from .mock import MockAdapter, MockCoreAdapter
from .odoo import OdooAdapter
from .odoo_http import HttpOdooAdapter
from .woo import WooAdapter

__all__ = [
    "BaseAdapter",
    "WooAdapter",
    "OdooAdapter",
    "CoreAdapter",
    "HttpCoreAdapter",
    "MockAdapter",
    "MockCoreAdapter",
    "HttpOdooAdapter",
]
