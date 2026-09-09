# 数据恢复说明（backup / restore）

> 归属：ops（ISSUE-0010）。配合 `infra/scripts/shopstore.ps1` / `shopstore.sh` 的
> `backup` / `restore` 命令使用。

## 1. 备份了什么

`backup` 在 `backups/<时间戳>/` 下生成：

| 文件 | 内容 | 恢复方式 |
| --- | --- | --- |
| `woo-mysql.sql` | WooCommerce 的 MySQL 全量（`mysqldump`） | `mysql` 导入 |
| `woo-uploads.tar.gz` | Woo 上传目录 `wp-content/uploads` | 解包回卷 |
| `odoo-postgres.pgdump` | Odoo 的 PostgreSQL 全量（`pg_dump -Fc`） | `pg_restore` |
| `odoo-filestore.tar.gz` | Odoo filestore（附件等，`/var/lib/odoo/filestore`） | 解包回卷 |
| `core-postgres.pgdump` | Core 的 PostgreSQL 全量（`pg_dump -Fc`） | `pg_restore` |
| `manifest.txt` | 时间戳 + 备份时的 git commit + 文件清单 | 审计 |

**不在备份范围**（可由 compose / 镜像重建，非业务状态）：WordPress 核心与插件、
Odoo 核心与模块、Core 应用镜像本身。

## 2. 一键恢复

```powershell
# Windows：确认后恢复（会覆盖现有数据）
$env:CONFIRM = 'yes'
.\infra\scripts\shopstore.ps1 restore -BackupDir .\backups\<时间戳>
```

```bash
# Linux / macOS / Git Bash
CONFIRM=yes bash infra/scripts/shopstore.sh restore --backup-dir backups/<时间戳>
```

脚本会：停止目标应用容器（保留数据库容器）→ 删库重建 → 导入 dump → 解包有状态文件 →
重启应用。Core 恢复后建议再跑一次 `alembic upgrade head`（若 dump 版本落后于代码，见下）。

安全护栏：

- 必须显式 `CONFIRM=yes`。
- 仅允许 `APP_ENV` 为 `local` / `staging`（拒绝向 prod 类环境恢复）。
- 恢复是**覆盖式**的：现有同名库会被 drop 重建。

## 3. 手工恢复（等价步骤，用于排障或理解）

### 3.1 WooCommerce（MySQL + 上传）

```bash
docker compose -f apps/woo/compose.yaml stop woo
# 把 dump 与上传归档拷进容器，再导入（见 infra/scripts 内实现）
# 等价 SQL：
#   DROP DATABASE IF EXISTS shopstore_woo;
#   CREATE DATABASE shopstore_woo CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
#   source /tmp/woo.sql;   (或 mysql shopstore_woo < woo-mysql.sql)
# 上传：tar -C /var/www/html -xzf /tmp/woo-uploads.tar.gz
docker compose -f apps/woo/compose.yaml start woo
```

### 3.2 Odoo（PostgreSQL + filestore）

```bash
docker compose -f apps/odoo/config/docker/compose.yaml --project-directory apps/odoo/config/docker stop odoo
#   dropdb -U odoo --if-exists shopstore_odoo
#   createdb -U odoo shopstore_odoo
#   pg_restore -U odoo -d shopstore_odoo --no-owner --role=odoo /tmp/odoo.pgdump
#   rm -rf /var/lib/odoo/filestore && tar -C /var/lib/odoo -xzf /tmp/odoo-filestore.tar.gz
docker compose -f apps/odoo/config/docker/compose.yaml --project-directory apps/odoo/config/docker start odoo
```

### 3.3 Core（PostgreSQL）

```bash
docker compose -f infra/docker/compose.yaml --env-file apps/core/.env stop core
#   dropdb -U core --if-exists shopstore_core
#   createdb -U core shopstore_core
#   pg_restore -U core -d shopstore_core --no-owner --role=core /tmp/core.pgdump
docker compose -f infra/docker/compose.yaml --env-file apps/core/.env start core
```

## 4. 恢复后的验证

```powershell
.\infra\scripts\shopstore.ps1 test-smoke   # HTTP 健康 + Integration Mock 链路
```

对 Odoo 还可运行 `bash apps/odoo/config/provision/run.sh verify`（或 `run.ps1 -Action verify`）
复核公司/仓库/产品/SKU/库存/演示销售单。

## 5. 恢复演练（验收依据）

按 `docs/测试数据说明.md` 在干净环境：

```text
1. init   -> 全新启动
2. seed   -> 导入测试数据
3. backup -> 生成备份（确认 backups/<ts>/ 六个文件齐全）
4. 破坏性改动（如 seed 重复、删除部分数据）
5. restore（CONFIRM=yes，指向第 3 步备份目录）
6. test-smoke / odoo verify 通过 -> 数据回到第 3 步时的状态
```

## 6. 注意事项

- 恢复会覆盖当前数据；共享/生产类环境禁用（护栏见第 2 节）。
- 备份与恢复都在容器内读写，规避了 PowerShell 5.1 重定向导致 UTF-16 破坏二进制/文本
  dump 的问题。
- 若从旧备份恢复后代码已前进，Core 需 `alembic upgrade head`；Odoo/Woo 由各自
  provisioning 幂等收敛。
