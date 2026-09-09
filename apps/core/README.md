# apps/core — Marketplace Core

Core 保存 marketplace 的业务模型和业务规则，不直接依赖 Odoo / Woo 的 API 细节。

## 目录所有权

| 路径 | 内容 | Owner |
| --- | --- | --- |
| `app/` | Core 应用代码（API、领域模型、业务规则） | dev |
| `migrations/` | 数据库迁移 | dev |
| `tests/` | 单元 / 集成测试 | dev（qa 协作验收） |
| `README.md` | 本文件 | config |

> 阶段 0：本目录作为骨架由 `config` 建立；`dev` 在 ISSUE-0005 中填充服务骨架。
> 环境变量模板见 `infra/env/core.env.example`。

## 协作边界

- Core 只保存 marketplace 必需数据；Odoo 全量数据留在 Odoo。
- Core 只发布领域命令 / 领域事件；对外 API 适配由 `integration/` 负责。
- 契约（openapi / events / schemas）定义在 `packages/contracts/`，归 architect。
