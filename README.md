# shopstore

基于开源 WooCommerce + Odoo 生态构建的可稳定升级、可扩展的 B2B 电商 marketplace。

- WooCommerce：前台电商基座（storefront）
- Marketplace Core：marketplace 业务规则与订单主权
- Odoo：ERP、库存与履约基座
- Integration Layer：跨系统连接与可靠同步

## 目录结构

```
shopstore/
  docs/                  文档（架构 / PRD / 开发方案 / 规范）
  apps/
    core/                Marketplace Core（业务模型与规则）
    woo/                 WordPress + WooCommerce
    odoo/                Odoo ERP
    integration/         Integration Layer（Adapter / 同步）
  packages/
    contracts/           契约（openapi / events / schemas）
    test-data/           固定测试数据
  infra/
    docker/              Docker / Compose 编排
    scripts/             启动 / 备份 / 初始化脚本
    env/                 环境变量模板（*.env.example）
  tests/
    smoke/               冒烟测试
    integration/         集成测试
    e2e/                 端到端测试
```

## 快速开始（一键启动）

阶段 0 一键编排（ops / ISSUE-0010）已就绪，覆盖 WooCommerce、Odoo、Marketplace Core、
Integration Layer 四个环境：

```powershell
# Windows（PowerShell 5.1+）
.\infra\scripts\shopstore.ps1 init      # 首次：生成 .env、构建并启动全部栈、执行迁移
.\infra\scripts\shopstore.ps1 status    # 状态与健康检查
```

```bash
# Linux / macOS / Git Bash
bash infra/scripts/shopstore.sh init
bash infra/scripts/shopstore.sh status
```

完整命令（`start` / `stop` / `status` / `logs` / `init` / `seed` / `backup` / `restore` /
`test-smoke`）与备份/恢复、staging 启动说明见 `infra/scripts/README.md`、
`infra/RESTORE.md`、`infra/STAGING.md`。

## 最终目录映射说明

仓库在进入阶段 0 前已存在 `docs/`（`PRD.md`、`架构方案.md`、`阶段性开发方案.md`、
`issues/README.md`）与根 `README.md`。本骨架在保留原有内容的前提下建立阶段 0
目标目录；**未发生目录搬移**，映射与原目录一一对应：

| 原位置 | 目标位置 | 说明 |
| --- | --- | --- |
| `README.md` | `README.md` | 扩展为本文件 |
| `docs/PRD.md` 等 | `docs/` | 保持不变 |
| `docs/issues/README.md` | `docs/issues/` | 保持不变 |

新增目录均为阶段 0 目标结构中的空骨架（含 `.gitkeep` 占位），待对应 issue 填充。
若后续发现需要调整目录，须在对应 README 中更新映射并说明原因。

## 目录所有权（Agent 修改范围）

| 目录 | 主 Owner | 协作 Agent |
| --- | --- | --- |
| `docs/` 架构/契约文档、`packages/contracts/` | architect | pm、config、dev |
| `apps/core/`（代码）、`apps/integration/` | dev | architect、config |
| `apps/woo/plugins`、`apps/woo/theme`、`apps/odoo/addons` | dev | config、ops |
| `apps/woo`、`apps/odoo` 的站点/模块**配置**与 `packages/test-data/`、`infra/env/` | config | ops、qa、dev |
| `infra/docker/`、`infra/scripts/` | ops | config |
| `tests/`（smoke/integration/e2e） | qa | dev、config |
| `docs/` issue 记录、排期、验收 | pm | 全体 |

规则：

- 一个应用目录的代码归 dev，其配置归 config，运行归 ops；跨 Agent 边界修改必须在 issue 中声明。
- 更细的所有权见各应用 `README.md`。

## 文档入口

- 架构：`docs/架构方案.md`
- PRD：`docs/PRD.md`
- 开发方案：`docs/阶段性开发方案.md`
- 命名规范：`docs/命名规范.md`
- 测试数据说明：`docs/测试数据说明.md`
- 分支与提交规范：`docs/分支与提交规范.md`
- 本地开发说明：`docs/本地开发说明.md`
- 环境变量模板：`infra/env/`
- 版本清单：`docs/版本清单.md`（阶段 0 ISSUE-0002 产出）
