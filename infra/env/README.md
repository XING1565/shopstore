# infra/env 目录说明

本目录保存**环境变量模板**（`*.env.example`）。所有真实配置、密码、密钥一律不提交，
只提交模板；本地复制为实际运行用的 `.env` 后填写。

## 模板文件

| 文件 | 对应应用 | 复制目标（本地约定） |
| --- | --- | --- |
| `core.env.example` | Marketplace Core | `apps/core/.env` 或由启动脚本读取 |
| `woo.env.example` | WordPress / WooCommerce | `apps/woo/.env`（`docker compose` 读取） |
| `odoo.env.example` | Odoo | `apps/odoo/config/` 引用的环境 |
| `integration.env.example` | Integration Layer | `apps/integration/.env` |

## 使用方式

1. 复制模板到目标位置（不以 `.example` 结尾）：
   ```powershell
   Copy-Item infra/env/core.env.example apps/core/.env
   ```
2. 在 `.env` 中填入本机真实值（`example.test` 域名、本机端口、本地密码）。
3. 不要在任何时候把 `.env` 提交进 git —— `.gitignore` 已覆盖。

## 不变量

- 仓库内不允许出现真实密钥、密码、token。
- 本地数据库文件、`wp-content/uploads`、Odoo filestore 等运行时数据不进 git。
- 环境变量命名遵循 `docs/开发规范.md` 中的命名规则。
