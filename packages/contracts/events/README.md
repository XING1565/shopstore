# Events（领域事件）

本目录定义跨系统的领域事件契约。事件是 Core、Integration、Woo、Odoo 之间的解耦通道：

```text
Core 产生领域命令 / 事件
  -> Integration 转换为目标系统 API 调用
  -> 外部系统状态回传
  -> Core 消费并更新业务状态
```

## 事件信封

所有事件使用统一信封 `envelope.schema.json`：

```json
{
  "event_id": "UUID v4",
  "event_type": "catalog.product.published",
  "event_version": "1",
  "source": "core",
  "occurred_at": "2026-09-09T03:36:27Z",
  "trace_id": "UUID v4",
  "request_id": "UUID v4",
  "data": { }
}
```

## 命名规则

`event_type = {domain}.{entity}.{past_tense_verb}`，三段小写、点分隔：

| domain | 含义 |
| --- | --- |
| `identity` | 买家 / 认证 |
| `catalog` | 品牌 / 商品 |
| `commerce` | 订单 / 履约状态 |

## 商品领域事件（已冻结，负载见 product-events.schema.json）

商品创建链路与投影由以下事件驱动，`event_type` 的 `domain=catalog`：

| event_type | 触发时机 | 负载（`$defs`） | 消费者动作 |
| --- | --- | --- | --- |
| `catalog.product.created` | Core 创建商品草稿 | `ProductEventData` | 记录 / 追踪，不投影 |
| `catalog.product.published` | Core 发布商品（draft → published） | `ProductEventData` | Integration 创建 Woo 投影 + Odoo 投影，写回 `woo_product_id` / `odoo_product_id` |
| `catalog.product.updated` | Core 更新商品（价格 / MOQ / 名称等） | `ProductEventData` | Integration 更新 Woo / Odoo 投影 |
| `catalog.product.archived` | Core 下架商品（published → archived） | `ProductArchivedData` | Integration 在 Woo 隐藏、在 Odoo 停用 |

关键约束：

- `catalog.product.published` 携带完整商品快照（含批发价与 MOQ 真相），但 Integration **只按各系统投影取字段**（见 `schemas/product-projections.schema.json`）：Woo 投影不含批发价 / MOQ，Odoo 投影只含 SKU 与名称。
- 投影成功后，`woo_product_id` / `odoo_product_id` 由 Integration 写回 Core 的 `external_ids`，事件负载本身不含这两个写回值。

## 其它领域计划事件（占位，待对应 issue 冻结）

```text
commerce.order.created
commerce.order.status_changed
commerce.order.sync_failed
odoo.delivery.shipped          # Odoo -> Core 状态回传
woo.order.submitted            # Woo -> Core 下单投影
```

## 示例：商品发布事件

```json
{
  "event_id": "3f2a1c4e-8b7d-4a9f-9c2e-1d0f3a5b6c7d",
  "event_type": "catalog.product.published",
  "event_version": "1",
  "source": "core",
  "occurred_at": "2026-09-09T03:36:27Z",
  "trace_id": "5a6b7c8d-9e0f-4a1b-8c2d-3e4f5a6b7c8d",
  "request_id": "7c8d9e0f-1a2b-4c3d-8e4f-5a6b7c8d9e0f",
  "data": {
    "product_id": "9f0e2a1c-7b3d-4c5e-8f6a-2d1e0b3a4c5d",
    "sku": "DEMO-SKU-001",
    "name": "Demo Product",
    "brand_id": "1b2c3d4e-5f6a-7b8c-9d0e-1f2a3b4c5d6e",
    "wholesale_price": {
      "amount_minor": 129900,
      "currency": "USD"
    },
    "moq": 10,
    "status": "published"
  }
}
```

## 关键约束

- 事件必须携带 `trace_id` 和 `event_type`，用于端到端追踪和消费者路由。
- 事件不直接修改消费方的业务状态；消费方根据事件生成命令，Integration 负责可靠传输（幂等、重试）。
- 同一幂等键的重复事件必须可被安全去重（见 `conventions.md` 幂等键规则）。
