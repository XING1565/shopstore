"""Core 领域模型包。

导入所有模型以填充 ``Base.metadata``（供 Alembic autogenerate 与测试建表使用）。
"""

from __future__ import annotations

from app.db import Base

from .brand import Brand
from .order import Order, OrderLine, OrderStatusEvent
from .product import Product
from .retailer import Retailer

__all__ = [
    "Base",
    "Brand",
    "Order",
    "OrderLine",
    "OrderStatusEvent",
    "Product",
    "Retailer",
]
