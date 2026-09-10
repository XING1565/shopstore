#!/usr/bin/env bash
# apps/odoo/config/provision/run.sh
# 跨平台版本的 apps/odoo/config/provision/run.ps1（用法与之一致）。
# ops（ISSUE-0010）后续提供项目级一键脚本；本脚本只覆盖 Odoo 自身生命周期。
#
# 前置：Docker + Docker Compose v2；复制 infra/env/odoo.env.example -> apps/odoo/config/docker/.env 并填值。
# 用法：bash apps/odoo/config/provision/run.sh <all|init|up|provision|verify|fulfill|login-check|status|logs|down>
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$CONFIG_DIR/docker"
COMPOSE_FILE="$DOCKER_DIR/compose.yaml"
ENV_FILE="$DOCKER_DIR/.env"

ACTION="${1:-all}"

if [ ! -f "$ENV_FILE" ]; then
  echo "缺少 $ENV_FILE 。请先复制模板：cp infra/env/odoo.env.example apps/odoo/config/docker/.env ，再填写真实值。" >&2
  exit 1
fi

compose() {
  docker compose -f "$COMPOSE_FILE" --project-directory "$DOCKER_DIR" --env-file "$ENV_FILE" "$@"
}

get_env() {
  grep -E "^$1=" "$ENV_FILE" | head -n1 | cut -d= -f2- || true
}

odoo_shell() {
  local script="$1"
  compose exec -T odoo sh -c "odoo shell --no-http --db_host=db --db_port=5432 --db_user=\"\$ODOO_DB_USER\" --db_password=\"\$ODOO_DB_PASSWORD\" --database=\"\$ODOO_DB_NAME\" < /opt/odoo-provision/$script"
}

case "$ACTION" in
  init)
    DB="$(get_env ODOO_DB_NAME)"; DB="${DB:-shopstore_odoo}"
    echo "==> 启动数据库并初始化（安装 sale/stock，一次性）"
    compose up -d db
    compose run --rm -T odoo odoo -d "$DB" -i sale,stock --without-demo=all --stop-after-init
    echo "==> 启动 Odoo 服务"
    compose up -d
    ;;
  up)
    compose up -d
    ;;
  provision)
    echo "==> 幂等配置（provision_odoo.py）"
    odoo_shell provision_odoo.py
    ;;
  verify)
    echo "==> 验收校验（verify_odoo.py）"
    odoo_shell verify_odoo.py
    echo "==> 登录校验（login_check.py）"
    compose exec -T odoo sh -c 'python3 /opt/odoo-provision/login_check.py'
    ;;
  fulfill)
    echo "==> 阶段一映射与履约校验（verify_fulfillment.py）"
    odoo_shell verify_fulfillment.py
    ;;
  login-check)
    compose exec -T odoo sh -c 'python3 /opt/odoo-provision/login_check.py'
    ;;
  all)
    "$0" init
    "$0" provision
    "$0" verify
    "$0" fulfill
    ;;
  status)
    compose ps
    ;;
  logs)
    compose logs -f --tail=100
    ;;
  down)
    compose down
    echo "已停止（数据卷保留；如需清库重建，另执行 docker compose down -v）"
    ;;
  *)
    echo "未知 Action: $ACTION" >&2
    exit 2
    ;;
esac
