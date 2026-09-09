#!/usr/bin/env bash
#
# init-test-data.sh — idempotent import of canonical test data into a running
# WooCommerce + Odoo stack (config / ISSUE-0008).
#
# Safe to re-run: every seed is keyed by a unique id (SKU / username / ref) and
# converges rather than duplicates. Run from the repository root.
#
# Prereq: docker compose stacks are up and their .env files exist (see
# apps/woo/README.md and apps/odoo/config/README.md). No passwords are stored
# in this repository.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

echo "==> [Woo] importing base products (seed-products.php)"
docker compose -f apps/woo/compose.yaml exec -T woo \
  wp --allow-root --path=/var/www/html eval-file /woo-config/seed-products.php

echo "==> [Woo] importing ISSUE-0008 canonical test data (seed-test-data.php)"
# compose.yaml exposes config/ at /woo-config (ro); wp-cli is bundled in image.
docker compose -f apps/woo/compose.yaml exec -T woo \
  wp --allow-root --path=/var/www/html eval-file /woo-config/seed-test-data.php

echo "==> [Odoo] importing ISSUE-0008 canonical test data (provision_odoo.py)"
docker compose \
  -f apps/odoo/config/docker/compose.yaml \
  --project-directory apps/odoo/config/docker \
  exec -T odoo sh -c 'odoo shell --no-http --db_host=db --db_port=5432 \
    --db_user="$ODOO_DB_USER" --db_password="$ODOO_DB_PASSWORD" \
    --database="$ODOO_DB_NAME" < /opt/odoo-provision/provision_odoo.py'

echo "==> done. Verify with docs/测试数据说明.md or apps/odoo run.sh verify."
