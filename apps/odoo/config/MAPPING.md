# Odoo 侧映射规则（ISSUE-0106）

本文件定义 Marketplace Core ↔ Odoo 的客户（partner）、SKU 与订单映射规则，以及
「销售单 → 确认 → 交货单 → 发货」基础流程，供 ISSUE-0107（Core 订单命令 → Odoo
销售单创建）直接使用。机器可读版本见 `apps/odoo/config/mapping/odoo_mapping.rules.json`。

规则由 `apps/odoo/config/provision/provision_odoo.py` 幂等落地（配置即代码），
验收由 `apps/odoo/config/provision/verify_fulfillment.py` 覆盖。全程不依赖手工 UI 点击。

## 1. 总原则

- **稳定业务键优先**：跨系统匹配一律用稳定键（partner `ref`、product `default_code`、
  sale order `client_order_ref`），不用名称、不猜字段。
- **Odoo 只承载 ERP 事实**：客户、SKU、销售单、交货单、库存、发货；批发价 / MOQ /
  订单主权在 Core，Odoo 不保存 marketplace 规则。
- **幂等**：所有查找均为「按唯一键先查再建」，重复触发不产生重复数据。

## 2. 客户（partner）映射

| 项 | 规则 |
| --- | --- |
| 目标模型 | `res.partner` |
| 匹配键 | `ref` == Core retailer 外部 ID（如 `DEMO-RTL-001`） |
| 必需字段 | `company_type = company`、`customer_rank >= 1` |
| 查找 | `[('ref', '=', '<retailer_external_id>')]`，必须唯一 |
| 缺失时 | 由 Integration（ISSUE-0107）按本规则创建，再用其 `id` 建销售单 |

`customer_rank >= 1` 保证该 partner 可作为销售单客户被 Odoo 接受。

canonical 测试客户：

```text
DEMO-RTL-001  retailer_approved@example.test  (Approved)
DEMO-RTL-002  retailer_pending@example.test   (Pending, 阶段 1 不下单)
```

## 3. SKU / 产品映射

| 项 | 规则 |
| --- | --- |
| 目标模型 | `product.product`（模板 `product.template`） |
| 匹配键 | `default_code` == SKU（如 `DEMO-SKU-001`），必须唯一 |
| 必需字段 | `sale_ok = true`、`is_storable = true`（可销售、可出库） |
| 查找 | `[('default_code', '=', '<sku>')]`，必须唯一 |

SKU 是 Core / Woo / Odoo 三系统稳定关联键；批发价、MOQ 不写入 Odoo。

## 4. 订单与外部 ID 映射

| 系统 | 记录 | 外部 ID |
| --- | --- | --- |
| Core | Marketplace Order | `marketplace_order_id`（业务主键） |
| Woo | Woo Order | `woo_order_id` |
| Odoo | `sale.order` | `odoo_sale_order_id` = Odoo 记录 `id` |
| Odoo | `stock.picking`（outgoing） | `odoo_delivery_id` = `picking.name` |

Odoo 侧幂等键：

| 项 | 规则 |
| --- | --- |
| 字段 | `sale.order.client_order_ref` |
| 取值 | Core 的 `marketplace_order_id` |
| 查找 | `[('client_order_ref', '=', '<marketplace_order_id>')]` |
| 作用 | 重复导出同一订单先命中该键，不重复创建销售单 |

## 5. 销售 → 交货 → 发货流程

```text
Integration 按 retailer.ref 解析/创建 partner
  -> 按 client_order_ref 查销售单；不存在才 create
  -> sale.order.action_confirm()          # 状态 draft -> sale
  -> 交货单自动生成：sale.order.picking_ids 中 picking_type_id.code == 'outgoing'
  -> 仓库在 Odoo 校验交货单 button_validate()  # 状态 -> done，即已发货
  -> 回传 Core：odoo_sale_order_id / odoo_delivery_id
```

仓库 `WH` 采用单步交货（`delivery_steps = ship_only`），确认销售单后直接生成
`WH/Stock -> Customers` 的出库单，阶段 1 允许仓库手动校验完成发货。

## 6. Canonical 测试夹具

| 名称 | 用途 |
| --- | --- |
| `DEMO-RTL-001/002` | 已审 / 待审测试客户 |
| `DEMO-SKU-001/002` | 测试 SKU（库存 120 / 80） |
| `SO-DEMO-001`（`client_order_ref=DEMO-MKT-ORDER-001`） | 确认销售单 + 生成交货单（ISSUE-0004） |
| `SO-DEMO-SHIP-001`（`client_order_ref=DEMO-MKT-ORDER-001-SHIP`） | 确认 + 交货 + 发货全链路（ISSUE-0106） |

## 7. 应用与验收

```powershell
# 幂等应用配置（公司/仓库/客户/SKU/库存 + 映射不变式）
powershell -ExecutionPolicy Bypass -File apps/odoo/config/provision/run.ps1 -Action provision
# 阶段一映射 + 履约验收（销售单 -> 确认 -> 交货 -> 发货）
powershell -ExecutionPolicy Bypass -File apps/odoo/config/provision/run.ps1 -Action fulfill
# 一次跑全量（init -> provision -> verify -> fulfill）
powershell -ExecutionPolicy Bypass -File apps/odoo/config/provision/run.ps1 -Action all
```

跨平台：`bash apps/odoo/config/provision/run.sh all`。

## 8. 不变量

- 仓库内不出现任何密码 / 密钥；密码只来自本地 `.env`。
- 测试数据只用 `example.test` 域名与本地演示账号。
- 配置重跑不改变已存在的目标状态（幂等）；重置 = 重建数据库，不做手工回退。
