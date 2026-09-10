# Contracts（契约包）

本目录是 ShopVidi 的跨系统契约中心，是 Developer 与 QA 的单一事实来源（single source of truth）。

## 目录结构

```text
packages/contracts/
  README.md            # 本文件
  conventions.md       # 权威约定：ID 映射、SKU、追踪、幂等、时间/金额、状态、版本策略
  openapi/
    openapi.yaml       # Core HTTP API 契约（健康检查 + 通用组件）
    README.md
  events/
    envelope.schema.json      # 领域事件信封
    product-events.schema.json  # 商品领域事件负载（created/published/updated/archived）
    README.md                  # 事件命名与示例
  schemas/
    money.schema.json
    timestamp.schema.json
    error.schema.json
    external-ids.schema.json   # 外部 ID 映射与 SKU 规则
    product.schema.json        # Core Product（批发价 / MOQ 真相）
    product-projections.schema.json  # Woo / Odoo 投影边界
    order.schema.json          # Marketplace Order 骨架
    README.md
```

## 谁用什么

| 角色 | 使用方式 |
| --- | --- |
| Developer | 依据 `openapi.yaml` 实现 Core 接口；依据 `schemas/` 定义数据模型；依据 `events/` 实现事件收发 |
| QA | 依据 `schemas/` 与 `openapi.yaml` 编写契约校验与冒烟断言；依据 `conventions.md` 校验字段/时间/金额格式 |
| Architect | 冻结契约、变更时更新版本策略并通知下游 |

## 快速上手

1. 先读 `conventions.md`，掌握 ID 映射、SKU、时间、金额、状态、幂等、追踪与版本规则。
2. 数据形状看 `schemas/`；HTTP 接口看 `openapi/`；跨系统事件看 `events/`。

## 所有权与边界

- 本目录由 `rebuild-architect` 负责冻结与变更。
- `rebuild-dev` / `rebuild-qa` 只读使用；需要变更时向 architect 提 issue，不直接改契约。
- 契约变更遵循 `conventions.md` 第 9 节的版本策略。
