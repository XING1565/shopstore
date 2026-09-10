"""业务枚举。

枚举值统一 snake_case，与 `packages/contracts/conventions.md` 第 8 节一一对应：
- 买家状态（PRD 第 6 节）：pending / approved / rejected / suspended
- 订单状态（PRD 第 6 节）：draft / submitted / sent_to_odoo / odoo_confirmed /
  inventory_reserved / picking_ready / shipped / completed / cancelled / sync_failed
"""

from __future__ import annotations

import enum


class RetailerStatus(enum.StrEnum):
    """买家（Retailer）认证状态。"""

    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    suspended = "suspended"


class BrandStatus(enum.StrEnum):
    """品牌（Brand）启用状态。"""

    active = "active"
    inactive = "inactive"


class ProductStatus(enum.StrEnum):
    """商品（Product）发布状态。"""

    draft = "draft"
    published = "published"
    archived = "archived"


class OrderStatus(enum.StrEnum):
    """Marketplace 订单（Order）状态。"""

    draft = "draft"
    submitted = "submitted"
    sent_to_odoo = "sent_to_odoo"
    odoo_confirmed = "odoo_confirmed"
    inventory_reserved = "inventory_reserved"
    picking_ready = "picking_ready"
    shipped = "shipped"
    completed = "completed"
    cancelled = "cancelled"
    sync_failed = "sync_failed"
