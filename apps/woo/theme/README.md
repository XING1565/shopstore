# apps/woo/theme — B2B 前台主题（ISSUE-0105）

Owner：**dev**。目录 `apps/woo/theme/`，主题 slug 为 `shopstore`。

职责一句话：**前台体验与页面模板**。批发价 / MOQ 展示、下单校验与 Core 下单桥接由
`marketplace-bridge` 插件（ISSUE-0104）承担，本主题负责页面模板、买家注册 / 认证状态
与订单状态投影，Woo 不落批发价 / MOQ / 订单主权。

## 契约依据

- `packages/contracts/openapi/openapi.yaml` — Core 订单接口（`GET /api/v1/orders` 等）
- `packages/contracts/schemas/product-projections.schema.json` — Woo 投影不含批发价 / MOQ
- `docs/架构方案.md` §4.1 / §7 — Woo 前台职责与「订单状态投影（Core → Woo）」
- `docs/PRD.md` §5 页面清单 — 品牌发现 / 商品详情 / 注册登录 / 采购单 / 无支付结账 / 我的订单
- `apps/core/app/api/deps.py` — 阶段 1 轻量身份模型（`X-Actor-Role` / `X-Retailer-Id`）

## 文件结构

| 文件 | 作用 |
| --- | --- |
| `style.css` | 主题头 + 基础变量 / 全局样式 |
| `functions.php` | 主题设置、WooCommerce 支持、样式注册、业务模块装配、单页 MOQ 提示 |
| `header.php` / `footer.php` / `index.php` / `page.php` / `single.php` | 基础模板 |
| `woocommerce/archive-product.php` | 商店 / 商品归档 |
| `woocommerce/taxonomy-product_cat.php` | 品牌页（阶段 1 品牌 = 商品分类） |
| `woocommerce/content-product.php` | 商品卡片（品牌 + 价格投影 + MOQ） |
| `page-templates/my-orders.php` | 订单状态展示页模板（`[shopstore_my_orders]`） |
| `inc/class-ss-theme-core-client.php` | 主题侧 Core 订单查询客户端（订单状态投影用） |
| `inc/class-ss-theme-retailer.php` | 买家注册 → Core 映射 + 认证状态展示 |
| `inc/class-ss-theme-orders.php` | 订单状态投影 + `[shopstore_my_orders]` shortcode |
| `inc/template-tags.php` | 状态标签 / 金额 / 时间 / 短 ID 等展示辅助 |
| `assets/theme.css` | 布局 + 批发价投影 + 状态徽章 + 订单表样式 |
| `theme.meta.yaml` | 主题元数据（legacy parity） |

## 集成点（依赖 ISSUE-0104 marketplace-bridge）

主题通过 bridge 公开类完成 Core 交互（映射 usermeta 与插件共享，主题持有自身实例）：

- 买家注册：`woocommerce_created_customer` → `ShopStore_Bridge_Retailer::register()`
  建立 Woo 用户 ↔ Core `retailer_id` 映射（注册后状态 `pending`）。
- 认证状态：`ShopStore_Bridge_Retailer::status()`，前台经 `[shopstore_account_status]`
  与 my-account 仪表盘展示 Pending / Approved。
- 批发价 / MOQ 展示：由 bridge 的 `woocommerce_get_price_html` 过滤钩子投影；
  主题在商品卡片与单页额外用 `ShopStore_Bridge_Core_Client::find_product_by_sku()`
  展示 MOQ 标签，并用 `.ss-bridge-wholesale` / `.ss-bridge-masked` 样式承接。
- 下单校验 / 桥接：由 bridge 在 checkout 钩子完成（认证 + MOQ 拦截、Core 建单）。
- 订单状态投影：bridge 未暴露订单查询，主题用自身 `SS_Theme_Core_Client` 查询
  `GET /api/v1/orders`（身份头与 bridge 一致）。

bridge 缺失时所有入口优雅降级（不建映射、状态提示「桥接未启用」），不产生致命错误。

## 页面 / 短代码

| 短代码 | 作用 |
| --- | --- |
| `[shopstore_account_status]` | 当前买家认证状态提示 |
| `[shopstore_my_orders]` | 当前买家的 Core 订单状态列表（订单号 / 状态 / 行明细 / 总额 / 时间） |

页面模板 `page-templates/my-orders.php`（模板名 `My Orders (B2B)`）输出
`[shopstore_my_orders]`；也可在任意页面正文直接使用该 shortcode。

## 激活（协调 config，见 compose.yaml / provision.sh）

主题已 bind-mount 进容器 `wp-content/themes/shopstore`，激活是数据库层一步：

```powershell
docker compose exec woo wp --allow-root --path=/var/www/html theme activate shopstore
```

`apps/woo/docker/provision.sh` 已加入该步骤（及 `marketplace-bridge` 插件激活）——该文件
归 config 所有，此处改动属 ISSUE-0105 的接入协调，见对应 issue 说明。

## 行为对照（验收标准）

| 验收标准 | 落点 |
| --- | --- |
| 前台可注册 / 登录买家 | WooCommerce my-account 原生注册 / 登录；注册表单追加公司名，注册后映射 Core |
| 认证买家能看到批发价与 MOQ | bridge 价格投影 + 主题 MOQ 标签 |
| 无支付 checkout 可提交满足 MOQ 的订单 | WooCommerce 经典 checkout（config 无支付 mu-plugin）+ bridge 校验 / 建单 |
| 低于 MOQ 的订单被拒绝并提示原因 | bridge `validate_checkout` 拦截并提示（Woo 原生错误展示） |
| 前台能展示最新订单状态 | `[shopstore_my_orders]` 实时查询 Core 订单 |

## 已知限制（阶段 1 边界）

- 订单状态投影为**实时查询** Core，无前端缓存；Core 不可用时订单列表降级为「暂不可用」。
- 货币：Core 返回 `amount_minor + currency`（阶段 1 USD），主题按 ISO 4217 最小单位指数
  格式化展示，不做跨币种换算（与 `conventions.md` §7 NOT_TESTED 一致）。
- 本机未运行 Docker 验证（交付以代码为准，端到端验收由 ISSUE-0110 在干净环境执行）。
