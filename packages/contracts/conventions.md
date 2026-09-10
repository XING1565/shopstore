# 契约与约定（Contracts & Conventions）

> 本文档是 ShopVidi 跨系统契约的权威约定，供 Developer 与 QA 使用。
> 状态：阶段 0 草案，待 pm / dev / qa 评审后冻结。所有「尚未在代码中验证」的条目均标记为 `NOT_TESTED`。

## 1. 适用范围与对象

- 本文档约束 Core、Integration、Woo 插件、Odoo 模块之间的一切数据交换。
- 字段命名统一 `snake_case`；时间字段统一 `*_at` 后缀；枚举值统一 `snake_case`。
- Core 自生成 ID 使用 UUID v4（不透明字符串）；Woo 与 Odoo 使用其原生整数 ID。

## 2. 外部系统 ID 映射

Core 保存所有跨系统关联 ID，映射结构以 `schemas/external-ids.schema.json` 为准。

### 2.1 Core Product -> Woo / Odoo

```text
Core Product (product_id, UUID v4)
  -> woo_product_id   （WooCommerce 商品投影，整数）
  -> odoo_product_id  （Odoo 产品投影，整数）
  -> sku              （三系统共享的稳定业务关联键，见第 3 节）
```

JSON 形态：

```json
{
  "product_id": "9f0e2a1c-7b3d-4c5e-8f6a-2d1e0b3a4c5d",
  "sku": "DEMO-SKU-001",
  "external_ids": {
    "woo_product_id": 1234,
    "odoo_product_id": 567
  }
}
```

### 2.2 Marketplace Order -> Woo / Odoo

```text
Marketplace Order (marketplace_order_id, UUID v4)
  -> woo_order_id         （WooCommerce 订单投影，整数）
  -> odoo_sale_order_id   （Odoo 销售单，整数）
  -> odoo_delivery_id     （Odoo 交货单，整数）
```

JSON 形态：

```json
{
  "marketplace_order_id": "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
  "external_ids": {
    "woo_order_id": 789,
    "odoo_sale_order_id": 1011,
    "odoo_delivery_id": 1213
  }
}
```

### 2.3 规则

- 外部 ID 字段**缺失**表示该投影尚未创建（不使用 `null`）。
- 一次 Odoo 交货单可包含多条销售单（多单合发）时，`odoo_delivery_id` 允许多值；阶段一先按 1:1 处理，多值结构待 ISSUE-0107 细化（`NOT_TESTED`）。
- 外部 ID 映射由 Integration 写回 Core，Core 领域模块不直接调用 Woo / Odoo API。

### 2.4 Product 三系统投影边界

批发价与 MOQ 的真相只在 Core；Woo 只做展示投影，Odoo 只拥有 SKU 与库存。投影形状见 `schemas/product-projections.schema.json`：

| 系统 | 持有字段 | 明确不持有 |
| --- | --- | --- |
| Core（`product.schema.json`） | 批发价 `wholesale_price`、MOQ、SKU、`external_ids` 等全部业务字段 | —（业务主实体） |
| Woo（`WooProductProjection`） | `sku`、`name`、`description`、`images`、`brand`、展示状态 | 批发价、MOQ（由桥接插件渲染时从 Core 读取） |
| Odoo（`OdooProductProjection`） | `sku`（→ `default_code`）、`name` | 批发价、MOQ；库存为 Odoo 主权，不回写 Core |

约束：

- Woo 后台不得手改批发价 / MOQ 并覆盖 Core 数据；下单与展示钩子必须回 Core 校验。
- Odoo 库存数量（qty_available / on-hand）由 Odoo 维护，阶段一不回传、不复制到 Core。

## 3. SKU 规则

- 格式：大写字母、数字、连字符；首尾必须为字母或数字；长度 3-64。
- 正则：`^[A-Z0-9][A-Z0-9-]{1,62}[A-Z0-9]$`，示例 `DEMO-SKU-001`。
- 唯一性：SKU 在 Core 全局唯一；在 Woo 中映射到 `sku`，在 Odoo 中映射到产品 `default_code`，三处必须一致。
- 不可变：SKU 一经发布不得修改；改 SKU 视为新产品（需迁移并重新映射外部 ID）。
- 测试数据使用固定命名空间 `DEMO-SKU-*`（见 ISSUE-0008）。

## 4. 请求追踪 ID

- 统一使用 HTTP 头 `X-Request-Id`，值为 UUID v4。
- 由调用方（Woo 桥接插件 / API 网关 / 其他服务）生成；缺失时由服务端生成并在响应头回显。
- 服务端必须在日志、错误响应 `error.request_id` 中记录该值。
- 领域事件另携带 `trace_id`（端到端业务流转关联，跨多次请求保持不变）与 `request_id`（触发本次事件的单次请求）。

```text
X-Request-Id  = 单次 HTTP 请求
trace_id      = 一次跨系统业务流转（例如一次下单到发货的完整链路）
```

## 5. 幂等键命名规则

- 统一使用 HTTP 头 `Idempotency-Key`（事件 / 任务内为 `idempotency_key` 字段）。
- 命名格式：`{scope}.{entity}.{action}.{source_id}`，四段点分隔。

| 段 | 取值 |
| --- | --- |
| `scope` | `core`、`woo`、`odoo`、`integration`（发起侧） |
| `entity` | `product`、`order`、`sale-order`、`delivery`、`customer`、`retailer`、`brand` |
| `action` | `create`、`update`、`upsert`、`publish`、`confirm`、`reserve`、`ship`、`import`、`export` |
| `source_id` | 发起系统的稳定 ID（如 `marketplace_order_id`、`sku`、`woo_order_id`），保留原值 |

示例：

```text
core.order.export.1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d   # 导出 Core 订单到 Odoo
core.product.publish.DEMO-SKU-001                        # 发布商品到 Woo / Odoo
odoo.delivery.import.1213                                # 导入 Odoo 交货单状态
```

- 约束：总长 ≤ 255；`scope`/`entity`/`action` 小写，`source_id` 保留原值；大小写敏感。
- 语义：**同一键 + 同一负载** = 可安全重试（副作用至多执行一次）；**同一键 + 不同负载** = 拒绝并返回 `409 Conflict`。

## 6. 统一时间格式

- 格式：RFC 3339 / ISO 8601，一律 UTC，以 `Z` 结尾，禁止本地时区偏移。
- 模式：`YYYY-MM-DDTHH:MM:SS[.fraction]Z`，推荐毫秒精度。
- 示例：`2026-09-09T03:36:27.050Z`。
- 纯日期（无时间）使用 `YYYY-MM-DD`，字段命名用 `*_date`。
- 时间戳字段命名统一 `*_at`（`created_at`、`updated_at`、`occurred_at`）。

## 7. 统一金额格式

- 结构：`{ "amount_minor": <integer>, "currency": "<ISO 4217>" }`。
- `amount_minor` 为带符号整数，以货币最小单位计（美元为分、日元为元）。
- `currency` 为 ISO 4217 三位大写字母（`USD`、`EUR`、`CNY`）。
- **禁止**在 JSON 中使用浮点数表示金额。
- 换算：十进制值 = `amount_minor / 10^exponent`，`exponent` 由 ISO 4217 最小单位表决定（默认 2；JPY=0、KWD=3）。
- 示例：`{ "amount_minor": 129900, "currency": "USD" }` 表示 1299.00 美元。
- 阶段 0 基础货币为 USD（由 ISSUE-0002 版本清单冻结）。多币种换算与舍入策略待阶段一引入（`NOT_TESTED`）。

## 8. 状态命名

- 机器可读枚举统一 `snake_case`，与 PRD 的 PascalCase 业务状态一一对应。

### 8.1 买家状态（PRD 第 6 节）

| PRD | 枚举值 |
| --- | --- |
| Pending | `pending` |
| Approved | `approved` |
| Rejected | `rejected` |
| Suspended | `suspended` |

### 8.2 订单状态（PRD 第 6 节）

| PRD | 枚举值 |
| --- | --- |
| Draft | `draft` |
| Submitted | `submitted` |
| SentToOdoo | `sent_to_odoo` |
| OdooConfirmed | `odoo_confirmed` |
| InventoryReserved | `inventory_reserved` |
| PickingReady | `picking_ready` |
| Shipped | `shipped` |
| Completed | `completed` |
| Cancelled | `cancelled` |
| SyncFailed | `sync_failed` |

### 8.3 商品状态（架构方案 / 数据模型）

| 含义 | 枚举值 |
| --- | --- |
| 草稿（未投影） | `draft` |
| 已发布（已投影 Woo / Odoo） | `published` |
| 已下架 | `archived` |

## 9. API 变更版本策略

- **版本化方式**：URL 路径主版本 `/api/v1/...`，这是唯一权威的版本信号。
- **主版本（major）**：破坏性变更时递增，并新增 `/api/v2/...` 路径，旧版本并行保留一个冻结期。
- **破坏性变更**包含：删除 / 重命名字段或端点、改变字段类型或含义、收紧校验导致既有合法请求被拒、删除枚举值。
- **非破坏性变更**（不升主版本）：新增可选字段、新增端点、放宽校验、新增枚举值。
- **弃用（deprecation）**：字段 / 端点被弃用时，在 OpenAPI 标记 `deprecated: true` 并在响应头 `Sunset` 给出下线日期；仅在下一个主版本中实际删除。
- 阶段 0 只发布 `v1` 骨架；接口冻结由 ISSUE-0005 / ISSUE-0006 依赖本策略完成。

## 10. 假设与未验证项

- 假设 Woo 与 Odoo 均使用整数自增 ID（两者默认行为一致）。
- 假设阶段 0 基础货币为 USD、`exponent = 2`（待 ISSUE-0002 冻结）。
- 一单多交货单 / 多单合并交货的映射结构、多币种舍入策略均为 `NOT_TESTED`，留待阶段一 issue 细化。
