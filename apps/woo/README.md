# apps/woo — WordPress + WooCommerce

前台电商基座（storefront）。

## 目录所有权

| 路径 | 内容 | Owner |
| --- | --- | --- |
| `plugins/marketplace-bridge/` | 连接 Core 的轻量桥接插件代码 | dev |
| `theme/` | 前台主题（storefront 定制） | dev |
| `README.md` | 本文件 | config |
| WordPress / WooCommerce 站点与插件**配置**（版本、站点 URL、货币、Woo 设置） | 由 ISSUE-0003 通过配置/脚本管理 | config |

> WordPress 核心与 WooCommerce 插件本体属于运行时安装产物，不随本仓库提交；
> 版本锁定见 `docs/版本清单.md`（ISSUE-0002）。
> 环境变量模板见 `infra/env/woo.env.example`。

## 协作边界

- 插件/主题**代码**修改归 dev。
- WooCommerce 环境安装与**站点配置**（URL、货币、用户、商品测试数据）归 config。
- 运行/编排/备份归 ops。
