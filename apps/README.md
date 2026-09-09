# apps

四个应用目录，各自 README 说明目录所有权与协作边界。

| 目录 | 应用 | Owner Agent | 协作 Agent |
| --- | --- | --- | --- |
| `core/` | Marketplace Core（业务模型与规则） | dev | architect（契约）、config（配置） |
| `woo/` | WordPress + WooCommerce storefront | dev | config（环境与 Woo 配置）、ops（运行） |
| `odoo/` | Odoo ERP（Sales / Inventory / Delivery） | dev | config（环境与 Odoo 配置）、ops（运行） |
| `integration/` | Integration Layer（外部 API 适配与同步） | dev | architect（契约）、config（配置） |

本目录由 `config` Agent 建立骨架；代码实现归 `dev`，环境与平台配置归 `config`。
任何跨目录修改必须在对应 issue 中声明。
