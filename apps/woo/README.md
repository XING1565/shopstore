# apps/woo — WordPress + WooCommerce

前台电商基座（storefront）。本目录同时承载 **ISSUE-0003（WooCommerce 基础环境，config）** 的可运行配置。

## 目录所有权

| 路径 | 内容 | Owner |
| --- | --- | --- |
| `plugins/marketplace-bridge/` | 连接 Core 的轻量桥接插件代码（ISSUE-0003 预留） | dev |
| `theme/` | 前台主题（storefront 定制） | dev |
| `config/` | WooCommerce 设置/页面/种子/占位 mu-plugin（配置即代码） | config |
| `docker/` | 运行时镜像（Dockerfile + entrypoint + provision） | config |
| `compose.yaml` | Woo 本地栈编排（wordpress + mysql，版本锁定） | config |
| `README.md` | 本文件 | config |

> WordPress 核心与 WooCommerce 插件本体属于运行时安装产物（命名卷 web-data），不随本仓库提交；
> 版本锁定见 `docs/版本清单.md`（ISSUE-0002）；环境变量模板见 `infra/env/woo.env.example`。
> 跨服务编排 / start·stop·logs·backup 脚本归 ops（`infra/docker` + `infra/scripts`，ISSUE-0010）。

## 本目录是什么（ISSUE-0003 交付物）

`docker compose up` 一个命令即可得到**可访问、可登录、带基础商品**的 WooCommerce：

- 服务栈：`wordpress:6.9-php8.3-apache` + `mysql:8.0`（tag 用 X.Y，与版本清单粒度一致）
- 首次启动自动完成（`docker/provision.sh`，幂等，不需要人工改动容器内文件）：
  - WordPress 安装（站点 URL = `WOO_BASE_URL`）
  - WooCommerce 插件安装并激活（`WOOCOMMERCE_VERSION` 锁定）
  - 站点 URL / 货币与地区 / 无支付 checkout 基线（占位 mu-plugin）配置
  - 测试管理员与测试买家账号
  - 基础商品 `DEMO-SKU-001` / `DEMO-SKU-002`
  - ISSUE-0008 canonical 测试数据：品牌 `Demo Brand A`、买家 `retailer_pending` / `retailer_approved`（`seed-test-data.php`）
- 数据持久化：`web-data`（WP 整站含 wp-content / 上传 / 已装插件）+ `db-data`（MySQL）

## 本地启动（需要 Docker，含 Docker Compose V2）

```powershell
# 1) 从模板生成本地 .env（默认值即可跑本地演示；对外暴露前务必改密码）
Copy-Item infra/env/woo.env.example apps/woo/.env

# 2) 启动并自动安装 / 配置（首次联网下载 woo 插件）
cd apps/woo
docker compose up -d --build
docker compose logs -f woo        # 观察 provision 日志
```

验证（验收标准映射）：

| 验收项 | 验证方式 |
| --- | --- |
| WordPress 可访问 | 浏览器打开 `http://localhost:8080` |
| WooCommerce 可访问 | `http://localhost:8080/wp-admin` 出现 WooCommerce 菜单；`/shop`、`/cart` 可打开 |
| 管理员可登录 | `WOO_ADMIN_USER` / `WOO_ADMIN_PASSWORD`（见 .env）登录 `/wp-admin` |
| 测试买家可登录 | `WOO_BUYER_USERNAME` / `WOO_BUYER_PASSWORD` 登录 `/my-account` |
| 商品可在 Woo 后台查看 | 后台「商品 → 所有商品」可见 DEMO-SKU-001 / 002 |
| 品牌/买家存在 | 后台可见分类 `Demo Brand A`；用户列表含 retailer_pending / retailer_approved |
| 不依赖人工修改容器文件 | 重启后自动收敛：`docker compose restart woo`，无手工步骤 |

常用操作：

```powershell
docker compose ps            # 状态
docker compose restart woo   # 重启（provision 幂等重放）
docker compose logs woo      # 日志
docker compose down          # 停止（保留数据卷）
docker compose down -v       # 停止并清空数据卷（回到全新状态，下次 up 重新初始化）
```

调试入口（镜像内置 wp-cli）：

```powershell
docker compose exec woo wp --allow-root --path=/var/www/html user list
docker compose exec woo wp --allow-root --path=/var/www/html wc --help
```

## 测试账号

| 账号 | 角色 | 默认值（来自 .env，模板为占位符，需自行设置） |
| --- | --- | --- |
| 管理员 | administrator | `woo_admin` |
| 测试买家（ISSUE-0003 基础） | customer | `retailer_demo` |
| 测试买家（ISSUE-0008，pending） | customer | `retailer_pending` |
| 测试买家（ISSUE-0008，approved） | customer | `retailer_approved` |

测试买家密码统一由 `WOO_RETAILER_PASSWORD`（`.env`）提供；邮箱统一使用 `.test` 域名
（`admin@example.test` / `retailer_demo@example.test` / `retailer_*@example.test`），不出现真实客户资料。
完整测试数据清单见 `docs/测试数据说明.md`。

## 协作边界与后续

- 插件/主题**代码**修改归 dev；WooCommerce 环境安装与**站点配置**归 config；运行/编排/备份归 ops。
- `config/mu-plugins/woo-no-payment-checkout.php` 为阶段 0「无支付」占位，支付/账期策略由后续阶段
  的 marketplace-bridge（dev）接管，接管时先停用该占位。
- ISSUE-0008（config）已扩展完整测试数据集（品牌 / retailer 买家，见 `docs/测试数据说明.md`）；
  ISSUE-0010（ops）将在此基础上固化 `infra/docker` + `infra/scripts` 的一键编排。
