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
| `tasks/export_order.py` | 示例任务：导出订单到 Odoo（占位） |
| `adapters/woo.py` | `WooAdapter` 接口 |
| `adapters/odoo.py` | `OdooAdapter` 接口 |
| `adapters/mock.py` | `MockAdapter`（实现两个接口，可注入延迟 / 错误） |

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
