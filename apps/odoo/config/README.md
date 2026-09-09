# apps/odoo/config — Odoo 运行时配置（ISSUE-0004 + ISSUE-0008）

config 负责的 Odoo 环境安装与业务配置全部放在本目录，遵循“原生配置优先、幂等可重跑”。

## 目录

| 路径 | 内容 |
| --- | --- |
| `docker/compose.yaml` | Odoo CE 19.0 + PostgreSQL 16（镜像 tag+digest 锁定，无 `latest`） |
| `odoo.conf.example` | Odoo Server 配置模板（compose 环境通常用镜像内置 conf + 环境变量） |
| `provision/provision_odoo.py` | 幂等配置：公司 / 仓库 / 基础库存地点 / 出库流程 / 客户 / 供应商 / 产品 SKU / 初始库存 / 用户 |
| `provision/verify_odoo.py` | 验收校验：模块 / 仓库 / SKU / 库存 / 演示销售单 / 交货单生成 |
| `provision/login_check.py` | XML-RPC 可达性 + admin / warehouse 登录校验 |
| `provision/run.ps1` / `run.sh` | 本地生命周期便利脚本（Windows PowerShell / Linux-macOS） |
| `README.md` | 本文件（config 维护） |

## 快速开始

1. 准备环境变量（真实值只进本地 `.env`，不入库）：

   ```powershell
   Copy-Item infra/env/odoo.env.example apps/odoo/config/docker/.env
   # 编辑 .env，至少填写 ODOO_DB_PASSWORD、ODOO_ADMIN_PASSWD、ODOO_TEST_USER_PASSWORD
   ```

2. 首次搭建（init：建库并安装 sale/stock → provision：幂等配置 → verify：验收）：

   ```powershell
   powershell -ExecutionPolicy Bypass -File apps/odoo/config/provision/run.ps1 -Action all
   # 跨平台等价命令：bash apps/odoo/config/provision/run.sh all
   ```

3. 之后日常操作：

   ```powershell
   ... run.ps1 -Action up        # 启动
   ... run.ps1 -Action provision # 幂等配置（重跑无副作用）
   ... run.ps1 -Action verify    # 验收
   ... run.ps1 -Action status|logs|down
   ```

## 目标配置状态

| 项 | 值 |
| --- | --- |
| 公司 | ShopStore Demo Co |
| 默认仓库 | WH（出库流程 = 单步交货 ship_only） |
| 基础库存地点 | WH/Stock、WH/Input、WH/Output（随仓库自动创建） |
| 测试客户 | Demo Retailer (Approved)，ref `DEMO-RTL-001`（retailer_approved@example.test） |
| 待审测试客户 | Demo Retailer (Pending)，ref `DEMO-RTL-002`（retailer_pending@example.test，ISSUE-0008） |
| 测试供应商 | Demo Supplier，ref `DEMO-SUP-001` |
| 测试产品 / SKU | `DEMO-SKU-001`（初始库存 120）、`DEMO-SKU-002`（初始库存 80），可库存、唯一 SKU |
| 模块 | sales（sale）、inventory（stock）已安装 |
| 用户 | admin（系统管理员）；warehouse（仓库 / Inventory User），密码取自 `ODOO_TEST_USER_PASSWORD` |
| 演示销售单 | `SO-DEMO-001`（确认后生成交货单，幂等创建） |

## 幂等与重置约定

- `provision_odoo.py` 与 `verify_odoo.py` 均可安全重跑：按唯一键（ref / login / default_code / 单号）查找，存在即跳过。
- 幂等只保证“不重复产生数据”；如需完整重置，**重建数据库**（不是手工删数据）：

  ```powershell
  docker compose -f apps/odoo/config/docker/compose.yaml --project-directory apps/odoo/config/docker down -v
  # 再次执行 run.ps1 -Action all
  ```

- 测试数据只用 `example.test` 域名与本地演示账号，不使用真实客户资料。

## 版本冻结

- odoo `19.0`（镜像 digest `sha256:d5a78a8c...e6b9`，Odoo CE 19.0-20260908）
- postgres `16`（镜像 digest `sha256:f1c3376c...f6f94`，PostgreSQL 16.15）
- 详见 `docs/版本清单.md`（ISSUE-0002）与 `docker/compose.yaml` 内注释。

## 协作边界

- 本目录归 config（ISSUE-0004 + ISSUE-0008）维护；自定义 addon 代码在 `apps/odoo/addons/`（dev）。
- 项目级一键启动 / 停止 / 备份 / 日志脚本由 ops（ISSUE-0010）在 `infra/scripts`、`infra/docker` 提供并整合。
- Odoo 数据库与 filestore 是本地运行时数据（命名卷），不提交进 git。
