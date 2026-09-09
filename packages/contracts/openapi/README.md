# OpenAPI（HTTP 接口契约）

本目录承载 Core 服务的 OpenAPI 3.1 契约。阶段 0 只定义健康检查与通用组件，业务资源（Product / Order）在 ISSUE-0005 / ISSUE-0006 冻结接口时补齐。

## 文件

| 文件 | 用途 |
| --- | --- |
| `openapi.yaml` | Core API 根契约（健康检查 + 通用组件） |

## 当前已定义

- `GET /health`、`GET /ready`、`GET /api/v1/health`（对应 ISSUE-0005 建议接口）
- 通用组件：`Health`、`ErrorEnvelope`（引用 `schemas/error.schema.json`）
- 通用头：`X-Request-Id`、`Idempotency-Key`
- 通用参数：分页 `limit` / `offset`
- 通用响应：`BadRequest`、`NotFound`、`Conflict`、`ServiceUnavailable`

## 使用约定

- 版本化：URL 路径版本 `/api/v1/...`，破坏性变更升主版本（见 `conventions.md`）。
- 所有响应 `application/json`；错误统一走 `ErrorEnvelope`。
- 服务端必须在响应头回显 `X-Request-Id`。
- 领域资源的数据形状以 `schemas/` 为权威，OpenAPI 引用其 schema（OpenAPI 3.1 原生支持 JSON Schema `$ref`）。

## 校验

本地可用任意支持 OpenAPI 3.1 的工具校验（如 `npx @redocly/cli lint`）。阶段 0 不强制引入工具链，由 ISSUE-0005 落地 CI 校验。
