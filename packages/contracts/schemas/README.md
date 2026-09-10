# Schemas（基础 JSON Schema）

本目录存放跨系统共享的基础 JSON Schema（draft 2020-12），是 Core、Integration、Woo 插件、Odoo 模块和 QA 共同遵守的数据形状契约。

## 文件清单

| 文件 | 用途 |
| --- | --- |
| `money.schema.json` | 统一金额格式（`amount_minor` + ISO 4217 `currency`） |
| `timestamp.schema.json` | 统一时间格式（RFC 3339，UTC，`Z` 结尾） |
| `error.schema.json` | 统一错误响应格式（`error.code/message/details/request_id`） |
| `external-ids.schema.json` | 外部系统 ID 映射结构与 SKU 规则（`$defs`：`Sku`、`ProductExternalIds`、`OrderExternalIds`） |
| `brand.schema.json` | Core Brand 品牌档案（商品归属，name 唯一，status 启用状态） |
| `product.schema.json` | Core Product 业务主实体（批发价 / MOQ 真相 + `external_ids`） |
| `product-projections.schema.json` | 三系统投影边界（`$defs`：`WooProductProjection`、`OdooProductProjection`） |
| `order.schema.json` | Marketplace Order 骨架（含 `external_ids` 与状态枚举） |

## 使用约定

- 所有 schema 采用 JSON Schema draft 2020-12，`$id` 以 `https://shopstore.local/contracts/schemas/` 为命名空间。
- 跨文件引用使用相对 `$ref`，例如 `external-ids.schema.json#/$defs/ProductExternalIds`。
- 字段命名统一 `snake_case`；时间字段统一 `*_at` 后缀。
- 枚举值统一 `snake_case`（与 PRD 的 PascalCase 业务状态对应关系见 `conventions.md`）。
- 金额禁止使用浮点数；时间禁止使用本地时区。

## 与 OpenAPI 的关系

`schemas/` 是领域数据形状的权威来源。`openapi/openapi.yaml` 承载 HTTP 层契约：阶段 0 已有健康检查与通用组件，阶段 1 已纳入 Product 资源（创建 / 查询 / 更新 / 发布 / 下架）与 Brand 资源（创建 / 查询 / 更新 / 删除），并以 `$ref` 引用本目录的 `product.schema.json`、`brand.schema.json`、`money.schema.json`、`external-ids.schema.json`。Order 资源待 ISSUE-0103 相关接口冻结时以 path 形式纳入。
