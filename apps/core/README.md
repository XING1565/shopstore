# apps/core — Marketplace Core

Marketplace Core 保存 marketplace 的业务模型和业务规则，不直接依赖 Odoo / Woo 的 API 细节。

## 目录所有权

| 路径 | 内容 | Owner |
| --- | --- | --- |
| `app/` | Core 应用代码（API、配置、日志、错误处理、数据库访问） | dev |
| `migrations/` | Alembic 数据库迁移 | dev |
| `tests/` | 单元 / 集成测试 | dev（qa 协作验收） |
| `pyproject.toml` | 依赖与工具配置 | dev |
| `README.md` | 本文件 | config / dev |

## 技术栈（见 docs/版本清单.md）

- Python 3.12
- FastAPI 0.115.x
- SQLAlchemy 2.0.x + Alembic 1.x
- Pydantic 2.x（含 pydantic-settings）
- PostgreSQL 16.x（Core 独立数据库 `shopstore_core`）

## 环境变量

从 `infra/env/core.env.example` 复制为 `apps/core/.env` 后填写本机值（真实 `.env` 不提交）。
应用通过环境变量加载配置（见 `app/config.py`），代码不写死任何环境相关值。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_ENV` | `local` | 运行环境 local / staging / prod |
| `APP_DEBUG` | `false` | 调试模式 |
| `APP_HOST` | `0.0.0.0` | 监听地址 |
| `APP_PORT` | `8000` | 监听端口 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `DB_CONNECTION` | `postgresql` | 数据库类型 |
| `DB_HOST` | `127.0.0.1` | 数据库地址 |
| `DB_PORT` | `5432` | 数据库端口 |
| `DB_DATABASE` | `shopstore_core` | 数据库名 |
| `DB_USERNAME` | `core` | 数据库账号 |
| `DB_PASSWORD` | `change_me_in_env_file` | 数据库密码 |
| `WOO_BASE_URL` | `http://localhost:8080` | Woo 地址（阶段 0 保留） |
| `ODOO_BASE_URL` | `http://localhost:8069` | Odoo 地址（阶段 0 保留） |
| `API_V1_PREFIX` | `/api/v1` | API 版本前缀 |
| `DATABASE_URL` | （空） | 可选：完整 SQLAlchemy URL 覆盖（测试 / CI） |

## 本地运行

```powershell
# 1. 准备独立 PostgreSQL（Core 专属库 shopstore_core）
#    本地可用任意 PostgreSQL 16+ 实例；此处以 docker 为例：
docker run --name shopstore-core-db -e POSTGRES_USER=core `
  -e POSTGRES_PASSWORD=change_me_in_env_file -e POSTGRES_DB=shopstore_core `
  -p 5432:5432 -d postgres:16

# 2. 安装依赖（建议使用虚拟环境）
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 3. 执行数据库迁移
alembic -c migrations/alembic.ini upgrade head

# 4. 启动服务
python -m app
# 或
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 健康检查

| 端点 | 含义 | 成功响应 |
| --- | --- | --- |
| `GET /health` | 存活探针 | `200 {"status":"ok"}` |
| `GET /ready` | 就绪探针（检查数据库） | `200 {"status":"ok","checks":{...}}`；依赖不可用 `503` |
| `GET /api/v1/health` | 版本化存活探针 | `200 {"status":"ok"}` |

- 响应头回显 `X-Request-Id`（请求追踪 ID，缺失时服务端生成）。
- 错误响应统一为 `{"error": {"code", "message", "details"?, "request_id"?}}`，
  见 `packages/contracts/schemas/error.schema.json`。

## 阶段 1 API（ISSUE-0103）

| 端点 | 方法 | 说明 | 访问控制 |
| --- | --- | --- | --- |
| `/api/v1/retailers` | POST | 注册买家（默认 `pending`） | 公开 |
| `/api/v1/retailers` | GET | 分页列出买家 | 运营 |
| `/api/v1/retailers/{id}` | GET | 查询单个买家 | 运营 / 本人 |
| `/api/v1/retailers/{id}/approve` | POST | 审核通过（`pending → approved`） | 运营 |
| `/api/v1/retailers/{id}/reject` | POST | 审核拒绝（`pending → rejected`） | 运营 |
| `/api/v1/brands` | GET / POST | 分页列出 / 创建品牌 | 运营 |
| `/api/v1/brands/{id}` | GET / PATCH / DELETE | 查询 / 更新 / 删除（仅无商品时） | 运营 |
| `/api/v1/products` | GET / POST | 分页列出 / 创建草稿 | 查询公开；创建需运营 |
| `/api/v1/products/{id}` | GET / PATCH | 查询 / 更新 | 查询公开；更新需运营 |
| `/api/v1/products/{id}/publish` | POST | 发布（`draft → published`） | 运营 |
| `/api/v1/products/{id}/archive` | POST | 下架（`published → archived`） | 运营 |
| `/api/v1/orders` | POST | 无支付下单（MOQ 校验，`Submitted`） | 已认证买家 |
| `/api/v1/orders` | GET | 分页列出订单 | 运营全部 / 买家本人 |
| `/api/v1/orders/{id}` | GET | 查询订单 | 运营 / 本人 |

### 身份模型（阶段 1 轻量 header，后续替换为 JWT / OIDC）

| Header | 取值 | 说明 |
| --- | --- | --- |
| `X-Actor-Role` | `operator` / `retailer` | 缺省为匿名 |
| `X-Retailer-Id` | UUID v4 | role=retailer 时必填 |
| `X-Operator-Name` | string | 可选，运营审计人 |

鉴权语义（PRD §7）：未认证买家不可见批发价与 MOQ、不能下单；已认证（`approved`）
买家可见批发价 / MOQ、可下单；运营可审核买家、维护商品、查看全部。

### 领域事件

Core 以 outbox 模式（`domain_events` 表）发布领域事件，不 import Woo / Odoo Adapter。
事件类型：`identity.retailer.registered/approved/rejected`、
`catalog.product.created/updated/published/archived`、`commerce.order.created`。
Integration（ISSUE-0107 等）消费并投影到 Woo / Odoo。

## 测试

```powershell
pytest
```

测试默认使用 SQLite 内存库（`DATABASE_URL` 可覆盖），不依赖本机 PostgreSQL。

## 迁移

```powershell
alembic -c migrations/alembic.ini upgrade head    # 应用迁移
alembic -c migrations/alembic.ini downgrade base  # 回滚
alembic -c migrations/alembic.ini current         # 查看当前版本
```

阶段 0 仅建立迁移基线（`versions/0001_initial.py`），暂无业务表。

## 协作边界

- Core 只保存 marketplace 必需数据；Odoo 全量数据留在 Odoo。
- Core 只发布领域命令 / 领域事件；对外 API 适配由 `integration/` 负责。
- 契约（openapi / events / schemas）定义在 `packages/contracts/`，归 architect，Core 只读使用。
