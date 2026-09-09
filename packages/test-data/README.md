# packages/test-data — 固定测试数据

Owner: **config**（ISSUE-0008）。QA / Ops 依据本目录与 `docs/测试数据说明.md` 初始化与校验数据。

## 目录

| 路径 | 内容 | 说明 |
| --- | --- | --- |
| `retailers/retailers.json` | 测试买家（retailer） | `retailer_pending` / `retailer_approved`，`.test` 邮箱 |
| `brands/brands.json` | 测试品牌 | Demo Brand A（Woo 商品分类：`demo-brand-a`） |
| `products/products.json` | 测试商品 / SKU | `DEMO-SKU-001` / `DEMO-SKU-002`，含 Woo/Odoo 两侧信息 |
| `orders/orders.json` | 订单 | 阶段 0 为空占位，阶段一填充 |

## 设计约束

- 固定命名空间：SKU `DEMO-SKU-###`、品牌 slug `demo-brand-*`、邮箱 `*.example.test`。
- **不包含任何密码/密钥**。账号密码一律来自本地 `.env`（模板见 `infra/env/*.env.example`）。
- 重复导入不产生不可控重复数据：所有导入均以唯一键（SKU / username / ref）幂等 upsert。

## 与运行系统的关系

本目录是**唯一事实源**，各系统以“配置即代码”方式实现对应 seed（幂等）：

- Woo 商品 → `apps/woo/config/seed-products.php`（ISSUE-0003 扩展）
- Woo 买家账号 + 品牌 → `apps/woo/config/seed-test-data.php`（ISSUE-0008）
- Odoo 客户/库存/SKU → `apps/odoo/config/provision/provision_odoo.py`（ISSUE-0004 + ISSUE-0008 扩展）

初始化 / 重置方法与 QA 使用说明见 `docs/测试数据说明.md`。
