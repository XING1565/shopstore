# tests — 验收测试

跨服务 / 端到端测试层，归 `qa` Agent 管理（ISSUE-0009），`dev`、`config` 协作提供被测环境与测试数据。

| 目录 | 内容 | Owner |
| --- | --- | --- |
| `smoke/` | 基础冒烟测试（各服务可访问、健康检查、SKU 存在等） | qa |
| `integration/` | 跨服务集成测试 | qa（dev 协作） |
| `e2e/` | 端到端业务链路测试 | qa（dev 协作） |

> 各应用内的单元测试仍留在 `apps/*/tests/`，归对应应用的代码 Owner。
