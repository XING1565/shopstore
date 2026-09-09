# reset-test-data.ps1 — wipe and rebuild test data for WooCommerce + Odoo
# (config / ISSUE-0008).
#
# DESTRUCTIVE: removes all docker volumes of the local demo stacks (`down -v`)
# then brings services back up, which re-runs the idempotent per-app
# provisioning (Woo docker/provision.sh incl. seed-test-data.php; Odoo
# provision_odoo.py). Only for a local / throwaway environment, never shared.
#
# Run from the repository root. Prereq: .env files exist (see app READMEs).
# Project-level one-click wrappers are owned by ops (ISSUE-0010, infra/scripts).
$ErrorActionPreference = 'Stop'

if ($env:CONFIRM -ne 'yes') {
  Write-Host 'This will DELETE all WooCommerce + Odoo local data volumes, then re-provision.'
  Write-Host 'Re-run with CONFIRM=yes to proceed.'
  exit 1
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
Set-Location $repoRoot

Write-Host '==> [Woo] resetting data volumes (down -v)'
docker compose -f apps/woo/compose.yaml down -v
if ($LASTEXITCODE -ne 0) { throw 'Woo down -v failed' }

Write-Host '==> [Odoo] resetting data volumes (down -v)'
docker compose -f apps/odoo/config/docker/compose.yaml --project-directory apps/odoo/config/docker down -v
if ($LASTEXITCODE -ne 0) { throw 'Odoo down -v failed' }

Write-Host '==> [Woo] starting + auto-provisioning (incl. ISSUE-0008 seed)'
docker compose -f apps/woo/compose.yaml up -d --build
if ($LASTEXITCODE -ne 0) { throw 'Woo up failed' }

Write-Host '==> [Odoo] init db + provision + verify (run.ps1 -Action all)'
powershell -ExecutionPolicy Bypass -File apps/odoo/config/provision/run.ps1 -Action all

Write-Host '==> done. Canonical test data imported; see docs/测试数据说明.md.'
