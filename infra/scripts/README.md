# infra/scripts — 一键编排脚本

阶段 0（ISSUE-0010，ops）的一键启动/停止/日志/初始化/测试数据/备份/恢复/状态/冒烟脚本。
统一编排四个环境：WooCommerce、Odoo、Marketplace Core、Integration Layer。

> 目录所有权：`infra/docker/`、`infra/scripts/` 归 ops；`apps/woo/compose.yaml`、
> `apps/odoo/config/docker/`、`packages/test-data/scripts/` 归 config（本层脚本复用，
> 不重复实现）。

## 前置要求

- Docker Engine + Docker Compose V2（`docker compose` 子命令）。
- Windows：PowerShell 5.1+；Linux / macOS / Git Bash：bash + `curl`。

## 命令总览

| 命令 | 说明 | PowerShell | 跨平台 (bash) |
| --- | --- | --- | --- |
| `init` | 首次初始化：生成 `.env`、构建并启动全部栈、执行迁移 | `.\infra\scripts\shopstore.ps1 init` | `bash infra/scripts/shopstore.sh init` |
| `start` | 启动全部栈（保留数据卷） | `... start` | `... start` |
| `stop` | 停止全部栈（保留数据卷） | `... stop` | `... stop` |
| `status` | 各服务容器状态 + HTTP 健康检查 | `... status` | `... status` |
| `logs` | 查看日志（可指定服务 / 跟随 / tail） | `... logs -Service woo -Follow` | `... logs --service woo --follow` |
| `seed` | 幂等导入测试数据（复用 `packages/test-data/scripts/`） | `... seed` | `... seed` |
| `backup` | 备份三套数据库 + 有状态文件 | `... backup` | `... backup` |
| `restore` | 从备份目录恢复（见 `infra/RESTORE.md`） | `... restore -BackupDir <路径>` | `... restore --backup-dir <路径>` |
| `test-smoke` | ops 级冒烟（HTTP 端点 + Integration Mock 链路） | `... test-smoke` | `... test-smoke` |

`logs` 额外参数：`-Service woo|odoo|core|all`（默认 all）、`-Follow`、`-Tail N`（默认 100）。

## 快速开始（全新环境）

```powershell
# Windows
.\infra\scripts\shopstore.ps1 init
.\infra\scripts\shopstore.ps1 status
```

```bash
# Linux / macOS / Git Bash
bash infra/scripts/shopstore.sh init
bash infra/scripts/shopstore.sh status
```

`init` 会自动从 `infra/env/*.env.example` 生成本地 `.env`（已存在则不覆盖）：

| 应用 | 运行时 .env |
| --- | --- |
| WooCommerce | `apps/woo/.env` |
| Odoo | `apps/odoo/config/docker/.env` |
| Core | `apps/core/.env` |
| Integration | `apps/integration/.env` |

生成后请把 `change_me_in_env_file` 占位密码改为本机值（本地演示可用默认值，共享前必须改）。

## 服务地址（默认端口）

| 服务 | 地址 | 健康检查 |
| --- | --- | --- |
| WooCommerce 前台 | `http://localhost:8080` | `GET /` |
| Odoo | `http://localhost:8069` | `GET /web/login` |
| Marketplace Core | `http://localhost:8000` | `GET /health`、`GET /ready` |

端口可在对应 `.env` 中调整（`WOO_PORT` / `ODOO_HTTP_PORT` / `APP_PORT`）。

## 各命令做了什么

- **init**：生成 `.env` → Woo `up -d --build`（首次自动装 WP/WooCommerce + 测试数据）→
  Odoo `run.sh all`（初始化库 + 安装 sale/stock + 幂等配置 + 验收）→ Core `up -d --build`
  → 等 core-db 就绪 → `alembic upgrade head`。
- **start / stop**：`docker compose up -d` / `down`（不删数据卷），跨 Woo / Odoo / Core 三栈。
- **status**：三栈 `compose ps` + Woo/Core/Odoo 的 HTTP 可达性检查（PASS/FAIL）。
- **logs**：透传 `docker compose logs`（可 `-Service` / `-Follow` / `-Tail`）。
- **seed**：调用 `packages/test-data/scripts/init-test-data.*`，幂等重放 Woo + Odoo 测试数据。
- **backup**：见下。
- **restore**：见 `infra/RESTORE.md`。
- **test-smoke**：HTTP 检查 Woo/Core(/health、/ready)/Odoo + Integration 的 Mock 链路测试
  （`pytest`，即 Core Command → Task → Adapter → Mock Result）。QA 的完整冒烟套件
  （`tests/smoke`，ISSUE-0009）在其之上独立维护。

## 备份与恢复

- 备份输出：`backups/<时间戳>/`（目录已在 `.gitignore` 忽略，绝不提交）。
- 备份内容：`woo-mysql.sql`、`woo-uploads.tar.gz`、`odoo-postgres.pgdump`、
  `odoo-filestore.tar.gz`、`core-postgres.pgdump`，外加 `manifest.txt`。
- 恢复步骤与安全须知见 `infra/RESTORE.md`。

## staging 启动说明

见 `infra/STAGING.md`。
