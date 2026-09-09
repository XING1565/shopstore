# packages — 共享包

跨应用共享的契约与测试数据。

| 目录 | 内容 | Owner Agent |
| --- | --- | --- |
| `contracts/` | OpenAPI、事件、JSON Schema、外部 ID 映射契约 | architect |
| `test-data/` | 固定测试数据（retailers / brands / products / orders） | config |

## 契约（contracts）

- 归 `architect` 管理（ISSUE-0007），Developer 与 QA 使用。
- API 变更有版本策略；Product / Order 外部 ID 映射、SKU、金额/时间/状态命名以契约为准。
- 目录：`openapi/`（接口）、`events/`（事件）、`schemas/`（JSON Schema 与 ID 映射结构）。

## 测试数据（test-data）

- 归 `config` 管理（ISSUE-0008），与 `qa`、`ops` 协作初始化。
- 使用固定命名空间与 `.test` 域名；重复初始化不得产生不可控重复数据。
- 目录：`retailers/`（买家）、`brands/`（品牌）、`products/`（商品与 SKU）、`orders/`（订单）。
- 测试账号密码不写入公开仓库（见 `docs/测试数据说明.md`，ISSUE-0008 提供）。
