# apps/integration — Integration Layer

跨系统连接层：Woo / Odoo Adapter、同步任务、幂等、统一 HTTP 客户端、错误分类与日志。

## 目录所有权

| 路径 | 内容 | Owner |
| --- | --- | --- |
| `app/shopstore_integration/` | Adapter / 同步任务 / 客户端代码 | dev |
| `tests/` | 单元 / Mock Adapter 测试 | dev（qa 协作验收） |
| `README.md` | 本文件 | config |

> 环境变量模板见 `infra/env/integration.env.example`。

## 阶段 0 已交付（ISSUE-0006）

验证链路：

```text
Core Command -> Integration Task -> Adapter -> Mock Result
```

| 模块 | 职责 |
| --- | --- |
| `config.py` | 环境配置与超时配置（`TimeoutConfig` / `RetryConfig` / `IntegrationSettings`） |
| `logging.py` | 日志接口 `IntegrationLogger` 与默认实现（携带 `request_id` / `trace_id`） |
| `errors.py` | 错误分类（超时 / 连接 / 鉴权 / 未找到 / 冲突 / 校验 / 上游） |
| `http_client.py` | 统一请求客户端 `UnifiedHttpClient`（httpx 封装，注入 `X-Request-Id`，统一超时与错误分类） |
| `idempotency.py` | 幂等键 `IdempotencyKey` 与存储接口 `IdempotencyStore`（进程内 `InMemoryIdempotencyStore`） |
| `commands.py` | Core 命令封装（`Command`，Core 不依赖 Odoo API 细节） |
| `tasks/base.py` | 同步任务抽象 `SyncTask`（封装幂等、错误捕获、日志）与 `TaskResult` |
| `tasks/dispatch.py` | 按 `command_type` 分派命令的 `TaskDispatcher` |
| `tasks/publish_product.py` | 示例任务：发布商品到 Woo / Odoo |
| `tasks/export_order.py` | 订单导出任务：Core 订单 → Odoo 销售单 |
| `adapters/woo.py` | `WooAdapter` 接口 |
| `adapters/odoo.py` | `OdooAdapter` 接口 |
| `adapters/mock.py` | `MockAdapter`（实现两个接口，可注入延迟 / 错误） |

## 阶段 1 已交付（ISSUE-0107）

真实链路（Core 订单命令 → Odoo 销售单创建）：

```text
Core commerce.order.created 事件
  -> CoreClient 轮询 GET /api/v1/events
  -> 去重（Core 订单已有 odoo_sale_order_id 则跳过）
  -> ExportOrderTask（sync_jobs 幂等键 + Odoo client_order_ref 去重）
  -> HttpOdooAdapter 创建销售单
  -> CoreClient 写回 odoo_sale_order_id（POST /orders/{id}/external-ids）
  -> CoreClient ack 事件（POST /events/{id}/ack）
```

| 模块 | 职责 |
| --- | --- |
| `db.py` | Integration 数据库引擎 / 会话（`sync_jobs` 任务表，`INTEGRATION_DATABASE_URL`） |
| `sync_jobs.py` | `SyncJob` 模型 + `SyncJobsStore`（数据库幂等存储，实现 `IdempotencyStore`） |
| `adapters/odoo_http.py` | `HttpOdooAdapter`（真实 Odoo JSON-RPC：partner/SKU/订单映射 + 幂等去重） |
| `core_client.py` | `CoreClient`（轮询事件 / ack / 写回外部 ID / 读买家） |
| `worker.py` | `OrderExportWorker`（编排：轮询 → 去重 → 导出 → 写回 → ack，失败留待重试） |

幂等键 `core.order.export.{marketplace_order_id}` 持久化到 `sync_jobs`；
同一订单重复触发由三层去重（Core 映射检查、`sync_jobs` 幂等键、Odoo
`client_order_ref` 查找）保证不重复创建销售单。

## 阶段 1 已交付（ISSUE-0109：同步失败、幂等与人工重试）

`sync_jobs` 任务表在幂等键之上扩展重试 / 退避 / 死信字段，形成完整的同步任务生命周期：

```text
running（执行中）
  -> completed（成功，幂等）
  -> failed（失败，按指数退避排期 next_retry_at）
       -> running（退避到期，重试）
       -> dead（重试耗尽或不可重试错误，死信，待人工重试）
```

| 模块 | 职责 |
| --- | --- |
| `sync_jobs.py` | `SyncJob` 重试/死信字段（`attempts` / `max_attempts` / `next_retry_at` / `last_error` / `command_type` / `payload`）+ `SyncJobsStore.mark_failed` / `retry` / `list_jobs` / `get` |
| `retry.py` | `RetryWorker`：拉取到期失败作业重建命令重新分派；`retry_job` 人工重试 |
| `cli.py` | 后台运维 CLI（`python -m shopstore_integration list` / `retry` / `retry-dead`）：失败可见 + 人工重试 |

关键语义：

- 可重试错误（超时 / 连接失败 / 上游瞬时错误）按指数退避排期重试，网络抖动不丢单；
- 不可重试错误（校验 / 鉴权 / 冲突）直接死信；可重试错误在达到 `max_attempts` 后死信；
- 失败记录 `last_error` 持久化，后台可见（`list_jobs` / CLI `list`）；
- 人工重试 `retry(key)` 把失败 / 死信任务重新置为立即到期并重置重试预算；
- 重试命中幂等键去重，不会重复创建 Odoo 销售单。

退避参数由 `RetryConfig`（`SYNC_RETRY_MAX` / `SYNC_RETRY_BACKOFF_SECONDS` /
`SYNC_RETRY_BACKOFF_FACTOR`）控制，见 `config.py`。

## 阶段 1 已交付（ISSUE-0115：履约状态回传长驻轮询 worker）

ISSUE-0108 交付了 `ReportFulfillmentTask`（Odoo 状态映射 + 回传），但缺少读取
Odoo 交货单状态并分派的长驻轮询服务。本任务补齐该 worker：

```text
Core 订单（已写回 odoo_sale_order_id 且未到履约终态）
  -> FulfillmentSyncWorker 轮询 Core GET /api/v1/orders
  -> 读 Odoo 出库交货单（sale.order.picking_ids，outgoing）
  -> 按状态机阶梯（odoo_confirmed -> inventory_reserved -> picking_ready -> shipped）
     补齐中间态，逐状态分派 ReportFulfillmentTask
  -> Core 单向推进（重复 / 乱序 / 倒退由 Core 状态机拒绝）
```

| 模块 | 职责 |
| --- | --- |
| `fulfillment_worker.py` | `FulfillmentSyncWorker`：读 Odoo 交货单状态 → 计算状态阶梯 → 逐状态分派；`fulfillment_status_path` 计算需回传的状态序列 |
| `adapters/odoo.py` / `odoo_http.py` | `OdooAdapter.get_delivery_for_sale_order`：按销售单查交出库交货单（`sale.order.picking_ids`，过滤 `picking_type_id.code == 'outgoing'`） |
| `core_client.py` | `CoreClient.list_orders`：分页列出订单（供 worker 枚举待同步订单） |
| `runtime.py` | 装配真实运行时（Core 客户端 + Odoo Adapter + worker + sync_jobs） |
| `cli.py` | 后台命令 `python -m shopstore_integration poll-fulfillment [--interval N] [--limit N] [--once]` |

关键语义：

- **单向推进**：Odoo 交货单状态比 Core 状态机更粗（`confirmed/assigned/done` vs
  `odoo_confirmed/inventory_reserved/picking_ready/shipped`），worker 按
  `FULFILLMENT_STATUS_LADDER` 补齐被跳过的中间态，逐状态回传，保证状态机单向推进；
- **幂等**：每个 `(odoo_delivery_id, odoo_status)` 一个幂等键，同一状态只回传一次；
- **不倒退**：乱序 / 重复回传由 Core 状态机拒绝（409），worker 每轮重新读 Core
  状态再计算阶梯，不产生倒退迁移；
- **重试 / 退避**：回传失败由 `ReportFulfillmentTask` 复用 `sync_jobs` 的重试 / 退避 /
  死信语义，网络抖动不丢回传；读取 Odoo 失败仅记录日志，下一轮重试。

运行：

```powershell
cd apps/integration
# 长驻轮询（间隔取 SYNC_POLL_INTERVAL_SECONDS）
python -m shopstore_integration poll-fulfillment
# 单次触发（测试 / 手动）
python -m shopstore_integration poll-fulfillment --once
```

## 契约对齐

接口边界遵循 `packages/contracts/`（ISSUE-0007）：

- 幂等键 `{scope}.{entity}.{action}.{source_id}`，同一键 + 同一负载至多执行一次，同一键 + 不同负载返回 `409 Conflict`；
- 追踪：`X-Request-Id`（单次请求）与 `trace_id`（跨系统流转）；
- 金额 `{amount_minor, currency}`（整数最小单位）、时间 RFC 3339 UTC；
- 错误响应结构对齐 `schemas/error.schema.json`。

## 本地开发

```powershell
cd apps/integration
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

## 协作边界

- Core 不直接依赖 Odoo API 细节；Integration 负责对外 API 适配、超时、重试、幂等、错误分类与日志。
- 阶段 1 使用数据库任务表（`sync_jobs`）替代进程内幂等存储；Redis 默认不启用。
