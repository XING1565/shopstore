# Issue 派发说明

本项目采用 issue 派发给 agent 小队的方式开发。

## Agent 小队

| 角色 | Agent |
| --- | --- |
| PM | rebuild-pm |
| Architect | rebuild-architect |
| Config | rebuild-config |
| Developer | rebuild-dev |
| Review / QA | rebuild-qa |
| Ops / Release | rebuild-ops |

## Issue 格式

```text
# ISSUE-XXXX 标题

## 背景

## 目标

## Owner

## 依赖

## 修改范围

## 输入

## 输出

## 验收标准

## 风险
```

## 派发原则

- 一个 issue 只交给一个主 owner。
- 涉及多个系统时，必须先由 `rebuild-architect` 定义契约。
- 涉及 Product / Order 跨 Woo、Core、Odoo 的实现时，必须先定义投影关系和外部 ID 映射。
- 涉及 Woo / Odoo 环境和配置时，先交给 `rebuild-config`。
- 涉及代码实现时，交给 `rebuild-dev`。
- 每个阶段必须由 `rebuild-qa` 做端到端验收。
- 发布、启动、备份和回滚由 `rebuild-ops` 负责。

## 阶段一关键验收链路

```text
买家注册
  -> 运营审核
  -> 买家查看批发价
  -> 按 MOQ 下单
  -> Core 创建 Marketplace 订单
  -> Odoo 创建销售单
  -> Odoo 创建交货单
  -> 仓库发货
  -> 前台订单状态更新
```
