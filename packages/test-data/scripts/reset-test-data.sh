#!/usr/bin/env bash
#
# reset-test-data.sh — wipe and rebuild test data for WooCommerce + Odoo
# (config / ISSUE-0008).
#
# DESTRUCTIVE: removes all docker volumes of the local demo stacks (`down -v`)
# then brings services back up, which re-runs the idempotent per-app
# provisioning (Woo docker/provision.sh incl. seed-test-data.php; Odoo
# provision_odoo.py). Only for a local / throwaway environment, never shared.
#
# Run from the repository root. Prereq: .env files exist (see app READMEs).
# Project-level one-click wrappers are owned by ops (ISSUE-0010, infra/scripts).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

if [ "${CONFIRM:-}" != "yes" ]; then
  echo "This will DELETE all WooCommerce + Odoo local data volumes, then re-provision."
  echo "Re-run with CONFIRM=yes to proceed."
  exit 1
fi

echo "==> [Woo] resetting data volumes (down -v)"
docker compose -f apps/woo/compose.yaml down -v

echo "==> [Odoo] resetting data volumes (down -v)"
docker compose -f apps/odoo/config/docker/compose.yaml \
  --project-directory apps/odoo/config/docker down -v

echo "==> [Woo] starting + auto-provisioning (incl. ISSUE-0008 seed)"
docker compose -f apps/woo/compose.yaml up -d --build

echo "==> [Odoo] init db + provision + verify (run.sh all)"
bash apps/odoo/config/provision/run.sh all

echo "==> done. Canonical test data imported; see docs/测试数据说明.md."
