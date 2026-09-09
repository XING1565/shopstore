# packages/test-data/scripts — 测试数据初始化 / 重置脚本

Owner: **config**（ISSUE-0008）。负责把 `packages/test-data/` 的 canonical 测试数据
导入到已启动的 Woo / Odoo（幂等），以及把测试数据重置回初始状态。

> 说明：这是“测试数据层”脚本，只调各应用**已存在的幂等 provision/seed 入口**
> （`apps/woo/config/seed-test-data.php`、`apps/odoo/config/provision/provision_odoo.py`）。
> 项目级一键启动/停止/编排由 ops（ISSUE-0010）在 `infra/scripts`、`infra/docker` 固化。

## 前置条件

- Docker + Docker Compose v2 可用，且对应服务已按各自 README 初始化（`.env` 已就绪）。
- 未设置真实密码前脚本可运行，但只会写入 `change_me_in_env_file` 占位密码。

## init-test-data（幂等导入）

重复执行不会产生重复数据：全部按唯一键（SKU / username / ref）upsert。

```bash
bash packages/test-data/scripts/init-test-data.sh
```

```powershell
powershell -ExecutionPolicy Bypass -File packages/test-data/scripts/init-test-data.ps1
```

## reset-test-data（重置测试数据）

回到“无测试数据”的干净基线后重新 init。**会删除对应服务的全部数据卷**
（`docker compose down -v`），仅用于本地/一次性环境，不可用于共享环境。

```bash
bash packages/test-data/scripts/reset-test-data.sh
```

```powershell
powershell -ExecutionPolicy Bypass -File packages/test-data/scripts/reset-test-data.ps1
```
