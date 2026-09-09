# apps/odoo — Odoo ERP

ERP / 库存 / 履约基座（Sales / Inventory / Warehouse / Delivery）。

## 目录所有权

| 路径 | 内容 | Owner |
| --- | --- | --- |
| `addons/marketplace_connector/` | marketplace 连接模块代码 | dev |
| `config/` | Odoo 配置（`odoo.conf` 模板、模块加载顺序等） | config |
| `README.md` | 本文件 | config |

> Odoo 本体属于运行时安装产物，不随本仓库提交；版本锁定见 `docs/版本清单.md`（ISSUE-0002）。
> 环境变量模板见 `infra/env/odoo.env.example`。

## 协作边界

- 自定义 addon **代码**归 dev。
- Odoo 环境安装与**业务配置**（公司、仓库、产品、SKU、模块安装）归 config（ISSUE-0004）。
- 运行/编排/备份归 ops。
- Odoo 数据库（含测试数据）不提交进 git。
