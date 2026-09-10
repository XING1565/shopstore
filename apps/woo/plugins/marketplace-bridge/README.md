# marketplace-bridge — Woo ↔ Core 轻量桥接插件（ISSUE-0104）

Owner：**dev**。目录 `apps/woo/plugins/marketplace-bridge/`，已由 `apps/woo/compose.yaml`
bind-mount 到容器 `wp-content/plugins/marketplace-bridge`（dev 代码实时可见）。

一句话职责：**Woo 前台展示与下单校验都回 Core，Woo 不落批发价 / MOQ 真相。**

## 契约依据

- `packages/contracts/schemas/product-projections.schema.json` — Woo 投影不含批发价 / MOQ。
- `packages/contracts/openapi/openapi.yaml` — Core HTTP 接口（products / orders / retailers）。
- `docs/商品创建链路与三系统投影契约.md` — §3 边界红线：展示与下单回 Core，禁止 Woo 后台手改批发价 / MOQ。
- `apps/core/app/api/deps.py` — 阶段 1 轻量身份模型（`X-Actor-Role` / `X-Retailer-Id`）。

## 文件结构

| 文件 | 作用 |
| --- | --- |
| `marketplace-bridge.php` | 插件入口与引导（校验 WooCommerce、装配模块） |
| `src/class-ss-bridge-core-client.php` | Core HTTP 客户端（追踪头 / 身份头 / 幂等键 / 统一错误） |
| `src/class-ss-bridge-retailer.php` | Woo 用户 ↔ Core retailer_id 映射与认证状态查询 |
| `src/class-ss-bridge-display.php` | 前台批发价 / MOQ 展示投影 |
| `src/class-ss-bridge-checkout.php` | 下单拦截（认证 + MOQ）与 Woo 订单 → Core 下单桥接 |
| `src/class-ss-bridge-admin.php` | 后台保护：剥离批发价 / MOQ 元数据写入 |
| `plugin.meta.yaml` | 插件元数据（legacy parity） |
| `README.md` | 本文件 |

## 配置

Core 地址通过环境变量 `MARKETPLACE_CORE_URL` 注入（模板见 `infra/env/woo.env.example`，
`apps/woo/compose.yaml` 已透传），缺省 `http://localhost:8000`。也可用过滤钩子覆盖：

```php
add_filter( 'shopstore_bridge_core_url', function () {
	return 'http://core:8000';
} );
```

## 激活

插件目录已挂载进容器，激活是数据库层一步：

```powershell
docker compose exec woo wp --allow-root --path=/var/www/html plugin activate marketplace-bridge
```

激活后前台价格展示、结账拦截、后台元数据保护即生效。激活动作由 config / ISSUE-0105 接入。

## 行为说明

### 前台批发价 / MOQ 展示（display）

按 SKU（三系统稳定业务关联键）向 Core 实时查询商品投影：

| 场景 | 行为 |
| --- | --- |
| SKU 不属于 Core | 保持 Woo 原生价格展示，不干预 |
| 已认证（approved）买家 | 展示 Core 批发价 + MOQ |
| 未登录 / 未认证 / 未映射买家 | 遮罩「批发价仅对认证买家可见」 |
| Core 不可用 | 遮罩并记录日志，不回退 Woo 本地价格 |

### 下单拦截 + 桥接（checkout）

- `woocommerce_after_checkout_validation`：未登录 / 未认证 / 数量低于 MOQ → 桥接层拦截并提示原因。
- `woocommerce_checkout_order_processed`（classic checkout 短代码路径）与
  `woocommerce_store_api_checkout_order_processed`（block checkout / Store API 路径）：
  把订单行提交 Core（`POST /api/v1/orders`），写回 `_shopstore_marketplace_order_id`
  元数据；失败则将 Woo 订单置 `failed`。
- 幂等键 `woo.order.create.{woo_order_id}`，重试不重复创建 Core 订单。
- 对外公开 `ShopStore_Bridge_Checkout::place_core_order( WC_Order $order, int $user_id )`
  作为「Woo 订单 → Core 下单」的桥接接口，供 ISSUE-0105 / 重试逻辑复用。

### 后台保护（admin）

- `woocommerce_process_product_meta` 保存商品时剥离 `_wholesale_price` / `_moq` 等元数据，
  杜绝 Woo 后台手改批发价 / MOQ 覆盖 Core 数据。
- 商品编辑页展示提示，说明批发价 / MOQ 由 Core 管理。

## 验收对照

| 验收标准 | 落点 |
| --- | --- |
| 插件可在 WooCommerce 激活并加载 | 标准插件头 + 引导；激活步骤见上 |
| 批发价 / MOQ 展示与下单校验均来自 Core | `display` 实时读 Core；`checkout` 回 Core 校验 |
| 未认证或低于 MOQ 下单在桥接层被拦截 | `validate_checkout` 拦截并提示原因 |
| 不修改 WooCommerce 核心代码 | 仅通过 WP/WC filter/action 钩子接入 |

## 已知限制（NOT_TESTED / 阶段 1 边界）

- **映射建立依赖注册流程**：Core 未提供「按邮箱查询买家」的公开接口，若 Woo 用户
  对应的邮箱已在 Core 注册但本地无映射（如重建 Woo 数据卷而未重建 Core），`register()`
  无法还原 retailer_id（返回 null，用户被视为未认证，需联系运营处理）。阶段 1 映射在
  买家注册时由 ISSUE-0105 建立。
- **货币换算**：Core 返回 `amount_minor + currency`（阶段 1 为 USD），插件只按货币最小单位
  指数做格式化展示，不做跨币种换算（与 `conventions.md` §7 的 NOT_TESTED 一致）。
- **区块结账下单前拦截**：`woocommerce_after_checkout_validation` 只在 classic checkout
  短代码路径触发，block checkout（Store API）不触发该钩子，故认证 / MOQ 的下单前拦截
  仅覆盖 classic 路径；block checkout 的下单桥接（订单创建后回 Core）已接入
  `woocommerce_store_api_checkout_order_processed`。block checkout 路径的认证 / MOQ
  前置拦截留待后续 issue。
- 未在本机运行 Docker 验证（本 issue 交付以代码为准；端到端验收见 ISSUE-0110）。
