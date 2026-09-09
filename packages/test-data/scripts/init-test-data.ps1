# init-test-data.ps1 — idempotent import of canonical marketplace test data
# into an already-running WooCommerce + Odoo stack (config / ISSUE-0008).
#
# Safe to re-run: every seed is keyed by a unique id (SKU / username / ref) and
# converges rather than duplicates. Run from the repository root.
#
# Prereq: docker compose stacks are up and their .env files exist (see
# apps/woo/README.md and apps/odoo/config/README.md). No passwords are stored
# in this repository.
$ErrorActionPreference = 'Stop'

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
Set-Location $repoRoot

Write-Host '==> [Woo] importing ISSUE-0008 canonical test data (seed-test-data.php)'
docker compose -f apps/woo/compose.yaml exec -T woo `
  wp --allow-root --path=/var/www/html eval-file /woo-config/seed-test-data.php
if ($LASTEXITCODE -ne 0) { throw 'Woo test-data import failed' }

Write-Host '==> [Odoo] importing ISSUE-0008 canonical test data (provision_odoo.py)'
docker compose -f apps/odoo/config/docker/compose.yaml `
  --project-directory apps/odoo/config/docker exec -T odoo sh -c 'odoo shell --no-http --db_host=db --db_port=5432 --db_user="$ODOO_DB_USER" --db_password="$ODOO_DB_PASSWORD" --database="$ODOO_DB_NAME" < /opt/odoo-provision/provision_odoo.py'
if ($LASTEXITCODE -ne 0) { throw 'Odoo test-data import failed' }

Write-Host '==> done. Verify with docs/测试数据说明.md or apps/odoo config provision verify.'
