# tests/smoke — 基础健康检查与冒烟测试（ISSUE-0009）

Owner：`qa`。协作：`dev`（Core / Integration 被测对象）、`config`（Woo / Odoo 环境与测试数据）。

本目录是阶段 0 的完整 QA 冒烟套件：跨 WooCommerce / Marketplace Core / Odoo /
Integration Layer 的可访问性、健康检查、模块与 SKU 存在性、Mock 链路、以及重启后的
数据持久化。区别于 `infra/scripts/shopstore.ps1 test-smoke`（ops 的轻量 HTTP + Mock
冒烟），本套件是 QA 的权威验收入口。

## 运行方式

前置：被测四环境已按 `infra/scripts/README.md` 完成 `init`（或 `start` + `seed`）。
套件从宿主机访问各服务端口（默认 `localhost`）。

```powershell
# Windows（仓库根目录）
python -m pytest tests/smoke -c tests/smoke/pytest.ini -v
```

```bash
# Linux / macOS
python3 -m pytest tests/smoke -c tests/smoke/pytest.ini -v
```

只跑只读子集（默认 Profile R）：

```powershell
python -m pytest tests/smoke -c tests/smoke/pytest.ini -v -m r
```

跑写路径子集（Profile W，**仅 staging**，见下）：

```powershell
$env:SMOKE_PROFILE = "all"      # 或 "w"
$env:SMOKE_TARGET = "staging"
python -m pytest tests/smoke -c tests/smoke/pytest.ini -v -m w
```

## 三种状态：PASS / FAIL / NOT_TESTED

| 状态 | 含义 | pytest 表现 |
| --- | --- | --- |
| PASS | 断言成立 | `passed` |
| FAIL | 断言不成立，且能指明具体服务 | `failed`（信息以 `service:` 开头） |
| NOT_TESTED | 无法判定（机制缺失/凭据缺失/依赖服务未起） | `skipped`（原因以 `NOT_TESTED:` 开头） |

- **NOT_TESTED 永远不是通过。** 运行结束时打印 `PASS / FAIL / NOT_TESTED` 汇总；
  只要出现 NOT_TESTED，该次运行不得视为“绿色”。
- 设 `SMOKE_STRICT=1` 时，含 NOT_TESTED 的运行以非零退出码结束，供 CI 直接拦截。
- **FAIL 必须说明具体服务**：所有失败信息以 `service: <服务名> ...` 前缀标明是
  Woo / Core / Odoo / Integration 哪一个。

## 两条测试纪律

1. **deny-probe 必须配 must-succeed 正向对照。** 一条“探测缺失/被拒”的用例必须与
   一条必然成功的对照用例成对出现，否则“探针坏掉了”和“真的缺失”得分相同。例如：
   - Odoo 模块存在（deny：模块未安装）←→ 对照：`base` 模块必然 `installed`。
   - 未知命令被拒（deny）←→ 对照：两条 Mock 链路必然成功。
   - 重启后数据保留（deny：记录消失）←→ 对照：重启前记录必然已存在。
2. **属性探针与机制探针分离。** 属性探针（如“模块是否安装”“SKU 是否存在”）在其
   *机制*（凭据、docker、XML-RPC、容器）不可用时上报 NOT_TESTED，而不是误报 FAIL；
   机制本身由独立的 must-succeed 对照用例守护（如 Woo 前台可达、Odoo XML-RPC 可达）。
   这样一条失败不会因为“路径写错/缺 fixture”而被误读为正确性结果。

## 两个 Profile：R（只读）/ W（写路径）

| Profile | 覆盖用例 | 允许目标 | 说明 |
| --- | --- | --- | --- |
| `r`（默认） | Woo/Core/Odoo 可达、Core `/ready`、Odoo 模块、SKU 存在、Integration Mock 链路 | live / staging / local | 不产生任何写操作，可与旧线上站点做 parity |
| `w` | 重启后数据持久化（写探针 + 重启 + 校验 + 清理） | **仅 staging / local** | 会写一条 `QA-PERSIST-*` 记录并重启 Odoo，**禁止对生产执行** |

- `SMOKE_PROFILE`：`r`（默认）/ `w` / `all`。
- `SMOKE_TARGET`：`local`（默认）/ `staging` / `live` / `prod`。
- Profile W 测试在 `SMOKE_TARGET` 为 live/prod 时**直接 FAIL**（拒绝执行），而不是
  静默跳过——写路径永不触碰生产。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `WOO_BASE_URL` | `http://localhost:8080` | WooCommerce 前台地址 |
| `CORE_BASE_URL` | `http://localhost:8000` | Core API 地址 |
| `ODOO_BASE_URL` | `http://localhost:8069` | Odoo Web / XML-RPC 地址 |
| `ODOO_DB_NAME` | `shopstore_odoo` | Odoo 数据库名 |
| `ODOO_SMOKE_USER` | `admin` | XML-RPC 查询用户 |
| `ODOO_SMOKE_PASSWORD` | 取 `ODOO_TEST_USER_PASSWORD` | 上述用户密码（缺失时模块/SKU 用例记 NOT_TESTED） |
| `WOO_CONSUMER_KEY` / `WOO_CONSUMER_SECRET` | 空 | 可选 Woo REST 凭据；缺省时 Woo SKU 走 `wp` CLI |
| `SMOKE_PROFILE` | `r` | `r` / `w` / `all` |
| `SMOKE_TARGET` | `local` | `local` / `staging` / `live` / `prod` |
| `SMOKE_STRICT` | 空 | 设为 `1` 时 NOT_TESTED 使退出码非零 |

## 用例清单

| 用例 | Profile | 检查点 |
| --- | --- | --- |
| `test_woo_front_reachable` | r | Woo 前台 `GET /` 可达（Woo 组正向对照） |
| `test_core_health_ok` | r | Core `GET /health` = 200 `ok`（存活） |
| `test_core_ready_db_ok` | r | Core `GET /ready` 数据库依赖 = `ok` |
| `test_odoo_web_login_reachable` | r | Odoo `GET /web/login` 可达（Odoo 组正向对照） |
| `test_odoo_xmlrpc_reachable` | r | Odoo XML-RPC `common.version` 可达（正向对照） |
| `test_odoo_modules_installed` | r | `sale` / `stock` 已安装（对照 `base`） |
| `test_odoo_sku_exist_unique` | r | `DEMO-SKU-001/002` 在 Odoo 唯一存在 |
| `test_woo_sku_exist` | r | `DEMO-SKU-001/002` 在 Woo 存在 |
| `test_publish_product_mock_chain` | r | Core 命令 → 发布商品 → Mock 成功 |
| `test_export_order_mock_chain` | r | Core 命令 → 导出订单 → Mock 成功 |
| `test_unknown_command_rejected` | r | 未知命令被拒（deny，对照两条成功链路） |
| `test_odoo_data_persists_across_restart` | w | 写探针 → `down/up` 重启 → 记录仍在 → 清理 |

## 测试数据

只用固定命名空间（`DEMO-SKU-###`、`DEMO-RTL-###`、`QA-PERSIST-*`）与 `example.test`
域名，不含任何真实客户资料。初始化/重置见 `packages/test-data/scripts/` 与
`docs/测试数据说明.md`。
