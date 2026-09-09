# staging 启动说明

> 归属：ops（ISSUE-0010）。说明如何把阶段 0 四环境以 staging 形态拉起。
> ops 只负责到 staging；**生产部署始终由人类执行，ops 永不部署生产**。

## 1. 与 local 的差异

| 维度 | local | staging |
| --- | --- | --- |
| `APP_ENV` | `local` | `staging` |
| 站点 URL | `http://localhost:*` | staging 主机名（见下） |
| 密码/密钥 | `change_me_in_env_file` 占位 | 真实但仅存于 `.env`（不提交） |
| 数据库端口 | 默认不暴露或本机 | 按 staging 网络策略 |
| 重启策略 | `unless-stopped` | 同（容器编排层保证） |

## 2. 准备 staging `.env`

在 staging 主机上，从模板生成并填写真实值（**绝不提交进 git**）：

```bash
cp infra/env/woo.env.example         apps/woo/.env
cp infra/env/odoo.env.example        apps/odoo/config/docker/.env
cp infra/env/core.env.example        apps/core/.env
cp infra/env/integration.env.example apps/integration/.env
```

关键项：

- `apps/core/.env`：`APP_ENV=staging`、`APP_DEBUG=false`、`LOG_LEVEL=INFO`、真实 `DB_PASSWORD`。
- `apps/woo/.env`：`WOO_BASE_URL=https://<staging-host>`、`WP_ENVIRONMENT_TYPE=staging`、真实密码。
- `apps/odoo/config/docker/.env`：真实 `ODOO_DB_PASSWORD`、`ODOO_ADMIN_PASSWD`。
- `apps/integration/.env`：`APP_ENV=staging`、`CORE_BASE_URL` / `WOO_BASE_URL` / `ODOO_BASE_URL`
  指向 staging 地址。

## 3. 启动顺序

```bash
# 1) 启动三栈
bash infra/scripts/shopstore.sh init        # 或 start（若环境已初始化过）

# 2) 迁移是显式的、有门槛的部署步骤（见第 4 节）
# 3) 幂等导入测试数据（仅验收环境需要；生产/staging 业务数据禁用 seed）
bash infra/scripts/shopstore.sh seed
# 4) 冒烟
bash infra/scripts/shopstore.sh test-smoke
```

> `init` 会为 local 默认执行 Core 迁移；在 staging，迁移必须走第 4 节的显式门槛流程，
> 不要依赖 `init` 里的自动迁移路径。

## 4. 迁移（显式、有门槛）

`apps/core` 的数据库变更通过 Alembic 迁移推进。staging 上迁移是**一次单独、可审批的操作**：

```bash
# 1) 迁移前备份（必须）
bash infra/scripts/shopstore.sh backup

# 2) 应用迁移（显式执行，不做自动迁移）
docker compose -f infra/docker/compose.yaml --env-file apps/core/.env \
  run --rm core alembic -c migrations/alembic.ini upgrade head

# 3) 校验
docker compose -f infra/docker/compose.yaml --env-file apps/core/.env \
  run --rm core alembic -c migrations/alembic.ini current
```

迁移不得被打包进 `start` / `up` 的隐式流程；回滚方式 = 用第 1 步备份 `restore` 或
`alembic downgrade <rev>`（见 `apps/core/README.md`）。

## 5. 回滚

```bash
# 用最近一次备份整体回滚（覆盖式，需 CONFIRM=yes）
CONFIRM=yes bash infra/scripts/shopstore.sh restore --backup-dir backups/<时间戳>

# 或仅 Core 迁移回滚
docker compose -f infra/docker/compose.yaml --env-file apps/core/.env \
  run --rm core alembic -c migrations/alembic.ini downgrade <上一版本>
```

## 6. 每次 staging 发布的记录

每次 staging 变更必须留记录（what / verify / rollback）：

```markdown
## staging 发布 <日期> <变更摘要>
- 变更内容：
- 验证方式：
- 回滚方式：
```

## 7. 已知边界

- 阶段 0 的 Integration Layer 无常驻服务，`test-smoke` 以测试套件验证。
- `apps/core/.env` 同时被容器（`infra/docker/compose.yaml` 的 `--env-file`）与本机进程
  读取；容器内 `DB_HOST` 由 compose 固定为服务名 `core-db`，无需在 `.env` 中改成容器名。
