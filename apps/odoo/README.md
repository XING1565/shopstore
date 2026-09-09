# apps/odoo — Odoo ERP

ERP / 库存 / 履约基座（Sales / Inventory / Warehouse / Delivery）。

## 目录所有权

| 路径 | 内容 | Owner |
| --- | --- | --- |
| `addons/marketplace_connector/` | marketplace 连接模块代码 | dev |
| `config/` | Odoo 运行时配置（compose、`odoo.conf` 模板、幂等配置/验收脚本），ISSUE-0004 + ISSUE-0008 | config |
| `README.md` | 本文件 | config |

> Odoo 本体属于运行时安装产物，不随本仓库提交；版本锁定见 `docs/版本清单.md`（ISSUE-0002）。
> 环境变量模板见 `infra/env/odoo.env.example`。

## 运行时配置（ISSUE-0004 输出，ISSUE-0008 扩展测试数据）

- Docker compose（Odoo CE 19.0 + PostgreSQL 16，镜像 digest 锁定）：`config/docker/compose.yaml`
- 幂等配置 / 验收 / 登录脚本：`config/provision/`（`run.ps1` / `run.sh` 一键执行）
- 使用说明：见 `config/README.md`
- ISSUE-0008 追加：待审买家 customer（`DEMO-RTL-002` = retailer_pending@example.test），
  与 Woo 侧 canonical 测试买家对齐（见 `packages/test-data/` 与 `docs/测试数据说明.md`）。

## 协作边界

- 自定义 addon **代码**归 dev。
- Odoo 环境安装与**业务配置**（公司、仓库、产品、SKU、模块安装）归 config（ISSUE-0004）。
- 运行/编排/备份归 ops。
- Odoo 数据库（含测试数据）不提交进 git。
