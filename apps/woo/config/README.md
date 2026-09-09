# apps/woo/config 目录（ISSUE-0003，Owner: config）

本目录存放 WooCommerce 基础环境的**配置即代码**，由 `docker/provision.sh` 在容器启动时
只读挂载执行（`/woo-config`），全部幂等、可重复运行：

| 文件 | 作用 | 说明 |
| --- | --- | --- |
| `woo-options.php` | 货币 / 地区 / 结算 / 计量等 WooCommerce 设置 | 值可用 `WOO_*` 环境变量覆盖 |
| `woo-pages.php` | 确保 shop / cart / checkout / my-account 页面存在并写入 WC 页面选项 | 按 slug 幂等创建 |
| `seed-products.php` | 基础商品种子数据（DEMO-SKU-001 / 002） | 按 SKU 幂等 upsert；完整测试数据属 ISSUE-0008 |
| `mu-plugins/woo-no-payment-checkout.php` | 无支付 checkout 阶段 0 占位 | 需真实支付时先停用，由 marketplace-bridge（dev）接管 |

所有权边界（对齐 `apps/woo/README.md`）：

- 本目录为 **config** 管理范围。
- `plugins/marketplace-bridge/`、`theme/` 的代码修改归 **dev**。
- 运行 / 编排 / 备份脚本（`infra/docker`、`infra/scripts`）归 **ops**（ISSUE-0010）。

修改本目录后需在对应 issue 中声明修改范围。
