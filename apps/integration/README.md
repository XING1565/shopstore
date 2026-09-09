# apps/integration — Integration Layer

跨系统连接层：Woo / Odoo Adapter、同步任务、重试与日志。

## 目录所有权

| 路径 | 内容 | Owner |
| --- | --- | --- |
| `app/` | Adapter / 同步任务代码 | dev |
| `tests/` | 单元 / Mock Adapter 测试 | dev（qa 协作验收） |
| `README.md` | 本文件 | config |

> 阶段 0：本目录作为骨架由 `config` 建立；`dev` 在 ISSUE-0006 中实现 Adapter 抽象与 Mock。
> 环境变量模板见 `infra/env/integration.env.example`。

## 协作边界

- Core 不直接依赖 Odoo API 细节；Integration 负责对外 API 适配与同步。
- Adapter 接口契约由 architect 定义（ISSUE-0006/0007）。
