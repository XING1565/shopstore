#!/usr/bin/env bash
# infra/scripts/shopstore.sh — ShopVidi stage-0 one-click orchestration (ops / ISSUE-0010).
#
# Cross-platform entry point (Linux / macOS / Git Bash). Windows users can use the
# equivalent shopstore.ps1. Full docs: infra/scripts/README.md.
#
# Commands:
#   init        first-time bring-up: create .env files, start all stacks, run migrations
#   start       start all stacks (Woo, Odoo, Core) — data volumes kept
#   stop        stop all stacks — data volumes kept
#   status      per-service container status + HTTP health checks
#   logs        tail logs [--service woo|odoo|core|all] [--follow] [--tail N]
#   seed        idempotent test-data import (reuses packages/test-data/scripts)
#   backup      dump all databases + stateful files into backups/<timestamp>/
#   restore     restore from a backup directory (--backup-dir <path>; CONFIRM=yes)
#   test-smoke  ops-level smoke checks (HTTP endpoints + integration mock chain)
#
# Stage-0 note: the Integration Layer is a library with no long-running service;
# it is validated through its test suite in `test-smoke`.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

WOO_COMPOSE=(docker compose -f "$REPO_ROOT/apps/woo/compose.yaml")
ODOO_COMPOSE=(docker compose -f "$REPO_ROOT/apps/odoo/config/docker/compose.yaml" --project-directory "$REPO_ROOT/apps/odoo/config/docker")
CORE_COMPOSE=(docker compose -f "$REPO_ROOT/infra/docker/compose.yaml" --env-file "$REPO_ROOT/apps/core/.env")

WOO_ENV="$REPO_ROOT/apps/woo/.env"
ODOO_ENV="$REPO_ROOT/apps/odoo/config/docker/.env"
CORE_ENV="$REPO_ROOT/apps/core/.env"
INTEGRATION_ENV="$REPO_ROOT/apps/integration/.env"
BACKUP_ROOT="$REPO_ROOT/backups"

ODOO_RUN_SH="$REPO_ROOT/apps/odoo/config/provision/run.sh"
SEED_SH="$REPO_ROOT/packages/test-data/scripts/init-test-data.sh"

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\n[ERROR] %s\n' "$*" >&2; exit 1; }

# Read KEY=VALUE from a dotenv file (no shell eval). Returns $3 if absent/empty.
get_env() {
  local file="$1" key="$2" default="${3:-}" val
  [ -f "$file" ] || { printf '%s' "$default"; return; }
  val="$(grep -E "^[[:space:]]*${key}=" "$file" | head -n1 | cut -d= -f2- \
        | sed -e 's/[[:space:]]*#.*$//' -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//' \
              -e 's/^"//' -e 's/"$//')"
  if [ -n "$val" ]; then printf '%s' "$val"; else printf '%s' "$default"; fi
}

woo_port()  { get_env "$WOO_ENV" 'WOO_PORT' '8080'; }
core_port() { get_env "$CORE_ENV" 'APP_PORT' '8000'; }
odoo_port() { get_env "$ODOO_ENV" 'ODOO_HTTP_PORT' '8069'; }

assert_docker() {
  command -v docker >/dev/null 2>&1 || die "docker not found on PATH (install Docker Engine / Desktop)"
  docker info >/dev/null 2>&1 || die "docker daemon is not running (start Docker Desktop first)"
  docker compose version >/dev/null 2>&1 || die "docker compose (Compose V2) not found"
}

assert_env_files() {
  local f
  for f in "$WOO_ENV" "$ODOO_ENV" "$CORE_ENV" "$INTEGRATION_ENV"; do
    [ -f "$f" ] || die "missing .env file: $f  (run: $0 init)"
  done
}

# check_http <label> <url> — returns 0 on a 2xx/3xx response, 1 otherwise.
check_http() {
  local label="$1" url="$2" code
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$url" 2>/dev/null || true)"
  if [ -n "$code" ] && [ "$code" -ge 200 ] 2>/dev/null && [ "$code" -lt 400 ] 2>/dev/null; then
    printf '  PASS  %-42s (HTTP %s)\n' "$label" "$code"
    return 0
  fi
  printf '  FAIL  %-42s (no healthy HTTP response)\n' "$label"
  return 1
}

cmd_init() {
  assert_docker
  say "creating .env files from templates (existing files kept)"
  [ -f "$WOO_ENV" ] || cp "$REPO_ROOT/infra/env/woo.env.example" "$WOO_ENV"
  [ -f "$ODOO_ENV" ] || cp "$REPO_ROOT/infra/env/odoo.env.example" "$ODOO_ENV"
  [ -f "$CORE_ENV" ] || cp "$REPO_ROOT/infra/env/core.env.example" "$CORE_ENV"
  [ -f "$INTEGRATION_ENV" ] || cp "$REPO_ROOT/infra/env/integration.env.example" "$INTEGRATION_ENV"

  if grep -q 'change_me_in_env_file' "$WOO_ENV" "$ODOO_ENV" "$CORE_ENV" 2>/dev/null; then
    say "WARNING: placeholder passwords (change_me_in_env_file) are still set. Fine for a local demo; change them before sharing."
  fi

  say "[Woo] build + start (auto-provisions WP/WooCommerce + test data)"
  "${WOO_COMPOSE[@]}" up -d --build

  say "[Odoo] init db + install sale/stock + provision + verify (config run.sh all)"
  bash "$ODOO_RUN_SH" all

  say "[Core] build + start core-db + core"
  "${CORE_COMPOSE[@]}" up -d --build

  say "[Core] waiting for core-db readiness"
  local _i
  for _i in $(seq 1 30); do
    "${CORE_COMPOSE[@]}" exec -T core-db pg_isready >/dev/null 2>&1 && break
    sleep 2
  done

  say "[Core] running database migrations"
  "${CORE_COMPOSE[@]}" run --rm core alembic -c migrations/alembic.ini upgrade head

  say "done. Verify with: $0 status   (re)import test data with: $0 seed"
}

cmd_start() {
  assert_docker
  assert_env_files
  say "[Woo] starting"
  "${WOO_COMPOSE[@]}" up -d
  say "[Odoo] starting"
  bash "$ODOO_RUN_SH" up
  say "[Core] starting"
  "${CORE_COMPOSE[@]}" up -d
  say "done. Verify with: $0 status"
}

cmd_stop() {
  assert_docker
  say "[Core] stopping"
  "${CORE_COMPOSE[@]}" down
  say "[Odoo] stopping"
  bash "$ODOO_RUN_SH" down
  say "[Woo] stopping"
  "${WOO_COMPOSE[@]}" down
  say "done. Data volumes kept; restart with: $0 start"
}

cmd_status() {
  assert_docker
  say "[Woo] compose ps"
  "${WOO_COMPOSE[@]}" ps
  say "[Odoo] compose ps"
  "${ODOO_COMPOSE[@]}" ps
  say "[Core] compose ps"
  "${CORE_COMPOSE[@]}" ps
  say "HTTP health checks"
  check_http "Woo front"    "http://localhost:$(woo_port)/"
  check_http "Core /health" "http://localhost:$(core_port)/health"
  check_http "Odoo web"     "http://localhost:$(odoo_port)/web/login"
}

logs_one() {
  local stack="$1" tail="$2" follow="$3"
  local -a comp
  case "$stack" in
    woo)  comp=("${WOO_COMPOSE[@]}") ;;
    odoo) comp=("${ODOO_COMPOSE[@]}") ;;
    core) comp=("${CORE_COMPOSE[@]}") ;;
  esac
  if [ "$follow" = "1" ]; then
    "${comp[@]}" logs -f --tail="$tail"
  else
    "${comp[@]}" logs --tail="$tail"
  fi
}

cmd_logs() {
  assert_docker
  local service="${SERVICE:-all}" tail="${TAIL:-100}" follow="${FOLLOW:-0}"
  case "$service" in
    woo|odoo|core) logs_one "$service" "$tail" "$follow" ;;
    all)
      local s
      for s in woo odoo core; do say "[$s] logs"; logs_one "$s" "$tail" "$follow"; done
      ;;
    *) die "unknown --service '$service' (woo|odoo|core|all)" ;;
  esac
}

cmd_seed() {
  assert_docker
  assert_env_files
  say "importing canonical test data (Woo + Odoo, idempotent)"
  bash "$SEED_SH"
  say "done. See docs/测试数据说明.md for expected data."
}

cmd_backup() {
  assert_docker
  assert_env_files
  local ts out wp_db_root wp_db_name odoo_db_user odoo_db_name core_db_user core_db_name
  ts="$(date +%Y%m%d-%H%M%S)"
  out="$BACKUP_ROOT/$ts"
  mkdir -p "$out"
  say "backing up into $out"

  wp_db_root="$(get_env "$WOO_ENV" 'WP_DB_ROOT_PASSWORD')"
  wp_db_name="$(get_env "$WOO_ENV" 'WP_DB_NAME' 'shopstore_woo')"
  odoo_db_user="$(get_env "$ODOO_ENV" 'ODOO_DB_USER' 'odoo')"
  odoo_db_name="$(get_env "$ODOO_ENV" 'ODOO_DB_NAME' 'shopstore_odoo')"
  core_db_user="$(get_env "$CORE_ENV" 'DB_USERNAME' 'core')"
  core_db_name="$(get_env "$CORE_ENV" 'DB_DATABASE' 'shopstore_core')"

  say "[Woo] dumping MySQL ($wp_db_name)"
  "${WOO_COMPOSE[@]}" exec -T -e MYSQL_PWD="$wp_db_root" db \
    mysqldump -uroot --single-transaction --routines --triggers --result-file=/tmp/woo.sql "$wp_db_name"
  "${WOO_COMPOSE[@]}" cp db:/tmp/woo.sql "$out/woo-mysql.sql"
  "${WOO_COMPOSE[@]}" exec -T db rm -f /tmp/woo.sql

  say "[Woo] archiving wp-content/uploads"
  "${WOO_COMPOSE[@]}" exec -T woo tar -C /var/www/html -czf /tmp/woo-uploads.tar.gz wp-content/uploads
  "${WOO_COMPOSE[@]}" cp woo:/tmp/woo-uploads.tar.gz "$out/woo-uploads.tar.gz"
  "${WOO_COMPOSE[@]}" exec -T woo rm -f /tmp/woo-uploads.tar.gz

  say "[Odoo] dumping PostgreSQL ($odoo_db_name)"
  "${ODOO_COMPOSE[@]}" exec -T db pg_dump -U "$odoo_db_user" -Fc --file=/tmp/odoo.pgdump "$odoo_db_name"
  "${ODOO_COMPOSE[@]}" cp db:/tmp/odoo.pgdump "$out/odoo-postgres.pgdump"
  "${ODOO_COMPOSE[@]}" exec -T db rm -f /tmp/odoo.pgdump

  say "[Odoo] archiving filestore"
  "${ODOO_COMPOSE[@]}" exec -T odoo tar -C /var/lib/odoo -czf /tmp/odoo-filestore.tar.gz filestore
  "${ODOO_COMPOSE[@]}" cp odoo:/tmp/odoo-filestore.tar.gz "$out/odoo-filestore.tar.gz"
  "${ODOO_COMPOSE[@]}" exec -T odoo rm -f /tmp/odoo-filestore.tar.gz

  say "[Core] dumping PostgreSQL ($core_db_name)"
  "${CORE_COMPOSE[@]}" exec -T core-db pg_dump -U "$core_db_user" -Fc --file=/tmp/core.pgdump "$core_db_name"
  "${CORE_COMPOSE[@]}" cp core-db:/tmp/core.pgdump "$out/core-postgres.pgdump"
  "${CORE_COMPOSE[@]}" exec -T core-db rm -f /tmp/core.pgdump

  {
    echo "# Shopstore backup manifest"
    echo "created: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "commit:  $(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
    echo "files:"
    ls -1 "$out"
  } > "$out/manifest.txt"

  say "backup complete: $out"
}

cmd_restore() {
  assert_docker
  assert_env_files
  local src="${BACKUP_DIR:-}" app_env
  [ -n "$src" ] || die "usage: $0 restore --backup-dir <path>"
  [ -d "$src" ] || die "backup dir not found: $src"

  app_env="$(get_env "$CORE_ENV" 'APP_ENV' 'local')"
  if [ "$app_env" != "local" ] && [ "$app_env" != "staging" ]; then
    die "refusing to restore into APP_ENV='$app_env' (only local/staging supported)"
  fi

  say "This will OVERWRITE Woo/Odoo/Core data from: $src"
  if [ "${CONFIRM:-}" != "yes" ]; then
    echo "Re-run with CONFIRM=yes to proceed. See infra/RESTORE.md."
    exit 1
  fi

  local wp_db_root wp_db_name odoo_db_user odoo_db_name core_db_user core_db_name
  wp_db_root="$(get_env "$WOO_ENV" 'WP_DB_ROOT_PASSWORD')"
  wp_db_name="$(get_env "$WOO_ENV" 'WP_DB_NAME' 'shopstore_woo')"
  odoo_db_user="$(get_env "$ODOO_ENV" 'ODOO_DB_USER' 'odoo')"
  odoo_db_name="$(get_env "$ODOO_ENV" 'ODOO_DB_NAME' 'shopstore_odoo')"
  core_db_user="$(get_env "$CORE_ENV" 'DB_USERNAME' 'core')"
  core_db_name="$(get_env "$CORE_ENV" 'DB_DATABASE' 'shopstore_core')"

  say "[Core] restoring PostgreSQL"
  "${CORE_COMPOSE[@]}" stop core
  "${CORE_COMPOSE[@]}" cp "$src/core-postgres.pgdump" core-db:/tmp/core.pgdump
  "${CORE_COMPOSE[@]}" exec -T core-db dropdb -U "$core_db_user" --if-exists "$core_db_name"
  "${CORE_COMPOSE[@]}" exec -T core-db createdb -U "$core_db_user" "$core_db_name"
  "${CORE_COMPOSE[@]}" exec -T core-db pg_restore -U "$core_db_user" -d "$core_db_name" --no-owner --role="$core_db_user" /tmp/core.pgdump
  "${CORE_COMPOSE[@]}" exec -T core-db rm -f /tmp/core.pgdump
  "${CORE_COMPOSE[@]}" start core

  say "[Odoo] restoring PostgreSQL + filestore"
  "${ODOO_COMPOSE[@]}" stop odoo
  "${ODOO_COMPOSE[@]}" cp "$src/odoo-postgres.pgdump" db:/tmp/odoo.pgdump
  "${ODOO_COMPOSE[@]}" exec -T db dropdb -U "$odoo_db_user" --if-exists "$odoo_db_name"
  "${ODOO_COMPOSE[@]}" exec -T db createdb -U "$odoo_db_user" "$odoo_db_name"
  "${ODOO_COMPOSE[@]}" exec -T db pg_restore -U "$odoo_db_user" -d "$odoo_db_name" --no-owner --role="$odoo_db_user" /tmp/odoo.pgdump
  "${ODOO_COMPOSE[@]}" exec -T db rm -f /tmp/odoo.pgdump
  if [ -f "$src/odoo-filestore.tar.gz" ]; then
    "${ODOO_COMPOSE[@]}" cp "$src/odoo-filestore.tar.gz" odoo:/tmp/odoo-filestore.tar.gz
    "${ODOO_COMPOSE[@]}" exec -T odoo sh -c 'rm -rf /var/lib/odoo/filestore && mkdir -p /var/lib/odoo && tar -C /var/lib/odoo -xzf /tmp/odoo-filestore.tar.gz'
    "${ODOO_COMPOSE[@]}" exec -T odoo rm -f /tmp/odoo-filestore.tar.gz
  fi
  "${ODOO_COMPOSE[@]}" start odoo

  say "[Woo] restoring MySQL + uploads"
  "${WOO_COMPOSE[@]}" stop woo
  "${WOO_COMPOSE[@]}" cp "$src/woo-mysql.sql" db:/tmp/woo.sql
  # mysqldump emits DROP TABLE IF EXISTS + CREATE TABLE per table, so re-importing
  # into the existing database overwrites the data. No host-shell redirect is used
  # (works identically under bash and PowerShell).
  "${WOO_COMPOSE[@]}" exec -T -e MYSQL_PWD="$wp_db_root" db sh -c 'mysql -uroot $MYSQL_DATABASE < /tmp/woo.sql'
  "${WOO_COMPOSE[@]}" exec -T db rm -f /tmp/woo.sql
  if [ -f "$src/woo-uploads.tar.gz" ]; then
    "${WOO_COMPOSE[@]}" cp "$src/woo-uploads.tar.gz" woo:/tmp/woo-uploads.tar.gz
    "${WOO_COMPOSE[@]}" exec -T woo tar -C /var/www/html -xzf /tmp/woo-uploads.tar.gz
    "${WOO_COMPOSE[@]}" exec -T woo rm -f /tmp/woo-uploads.tar.gz
  fi
  "${WOO_COMPOSE[@]}" start woo

  say "restore complete. Verify with: $0 test-smoke"
}

cmd_test_smoke() {
  assert_docker
  assert_env_files
  local ok=0
  say "ops smoke checks"
  check_http "Woo front"    "http://localhost:$(woo_port)/" || ok=1
  check_http "Core /health" "http://localhost:$(core_port)/health" || ok=1
  check_http "Core /ready"  "http://localhost:$(core_port)/ready" || ok=1
  check_http "Odoo web"     "http://localhost:$(odoo_port)/web/login" || ok=1

  say "[Integration] running mock-chain test suite"
  if docker compose --profile tests -f "$REPO_ROOT/infra/docker/compose.yaml" --env-file "$CORE_ENV" run --rm integration-tests; then
    printf '  PASS  integration mock chain\n'
  else
    printf '  FAIL  integration mock chain\n'
    ok=1
  fi

  say "Note: the full QA smoke suite (tests/smoke, ISSUE-0009) is separate."
  return "$ok"
}

usage() {
  printf '%s\n' \
    "usage: $0 <command> [options]" \
    "" \
    "commands:" \
    "  init        first-time bring-up (env files, start all, migrations)" \
    "  start       start all stacks" \
    "  stop        stop all stacks (volumes kept)" \
    "  status      container status + HTTP health checks" \
    "  logs        tail logs" \
    "  seed        idempotent test-data import" \
    "  backup      dump databases + stateful files" \
    "  restore     restore from a backup directory" \
    "  test-smoke  ops-level smoke checks" \
    "" \
    "options:" \
    "  --service woo|odoo|core|all   (logs)" \
    "  --follow / -f                 (logs)" \
    "  --tail N                      (logs, default 100)" \
    "  --backup-dir <path>           (restore)" \
    "" \
    "environment:" \
    "  CONFIRM=yes                   (restore: acknowledge overwrite)"
}

CMD="${1:-}"
shift || true

SERVICE="all"; FOLLOW=0; TAIL=100; BACKUP_DIR=""
while [ $# -gt 0 ]; do
  case "$1" in
    --service)      SERVICE="$2"; shift 2 ;;
    --follow|-f)    FOLLOW=1; shift ;;
    --tail)         TAIL="$2"; shift 2 ;;
    --backup-dir)   BACKUP_DIR="$2"; shift 2 ;;
    *)              die "unknown option: $1 (see --help)" ;;
  esac
done

case "$CMD" in
  init)       cmd_init ;;
  start)      cmd_start ;;
  stop)       cmd_stop ;;
  status)     cmd_status ;;
  logs)       cmd_logs ;;
  seed)       cmd_seed ;;
  backup)     cmd_backup ;;
  restore)    cmd_restore ;;
  test-smoke) cmd_test_smoke ;;
  help|-h|--help|"") usage ;;
  *)          die "unknown command '$CMD' (see --help)" ;;
esac
