# apps/odoo/config/provision/run.ps1
# Odoo local environment convenience script (ISSUE-0004, owned by config).
# ops (ISSUE-0010) will later provide project-wide one-click scripts; this one
# only covers the Odoo service lifecycle.
#
# Prereq: Docker + Docker Compose v2. Copy infra/env/odoo.env.example to
#         apps/odoo/config/docker/.env and fill in real values (.env is gitignored).
#
# Usage (from repo root):
#   powershell -ExecutionPolicy Bypass -File apps/odoo/config/provision/run.ps1 -Action all
#   powershell -ExecutionPolicy Bypass -File apps/odoo/config/provision/run.ps1 -Action provision
#
# Actions:
#   all         = init -> provision -> verify -> fulfill (first-time bring-up)
#   init        = start db, init database and install sale/stock (one-time)
#   up          = start db + odoo services
#   provision   = idempotent config: company/warehouse/users/customer/vendor/products SKU/initial stock
#   verify      = stage-0 acceptance checks (incl. demo sale order + delivery order)
#   fulfill     = stage-1 acceptance: mapping rules + sale->confirm->delivery->ship (ISSUE-0106)
#   login-check = XML-RPC reachability + admin/warehouse login
#   status      = compose service status
#   logs        = tail odoo + db logs
#   down        = stop (keep data volumes)

param(
    [ValidateSet('all', 'init', 'up', 'provision', 'verify', 'fulfill', 'login-check', 'status', 'logs', 'down')]
    [string]$Action = 'all'
)

$ErrorActionPreference = 'Stop'

$provisionDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$configDir = Split-Path -Parent $provisionDir
$dockerDir = Join-Path $configDir 'docker'
$composeFile = Join-Path $dockerDir 'compose.yaml'
$envFile = Join-Path $dockerDir '.env'

if (-not (Test-Path -LiteralPath $envFile)) {
    Write-Error "Missing $envFile. Copy infra/env/odoo.env.example to apps/odoo/config/docker/.env and fill in real values."
}

$baseArgs = @('-f', $composeFile, '--project-directory', $dockerDir, '--env-file', $envFile)

function Invoke-Compose {
    param([Parameter(Mandatory = $true)][string[]]$Cmd)
    & docker compose @baseArgs @Cmd
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed: $($Cmd -join ' ')" }
}

function Get-EnvVal {
    param([string]$Key)
    $line = Get-Content -LiteralPath $envFile -Encoding UTF8 | Where-Object { $_ -match "^$Key=" } | Select-Object -First 1
    if ($line) { return ($line -split '=', 2)[1] }
    return $null
}

function Invoke-OdooShell {
    param([Parameter(Mandatory = $true)][string]$Script)
    $shell = 'odoo shell --no-http --db_host=db --db_port=5432 --db_user="$ODOO_DB_USER" --db_password="$ODOO_DB_PASSWORD" --database="$ODOO_DB_NAME" < /opt/odoo-provision/' + $Script
    Invoke-Compose @('exec', '-T', 'odoo', 'sh', '-c', $shell)
}

switch ($Action) {
    'init' {
        $db = Get-EnvVal 'ODOO_DB_NAME'
        if (-not $db) { $db = 'shopstore_odoo' }
        Write-Host '==> start db and init (install sale/stock, one-time)'
        Invoke-Compose @('up', '-d', 'db')
        Invoke-Compose @('run', '--rm', '-T', 'odoo', 'odoo', '-d', $db, '-i', 'sale,stock', '--without-demo=all', '--stop-after-init')
        Write-Host '==> start odoo service'
        Invoke-Compose @('up', '-d')
    }
    'up' {
        Invoke-Compose @('up', '-d')
    }
    'provision' {
        Write-Host '==> idempotent config (provision_odoo.py)'
        Invoke-OdooShell 'provision_odoo.py'
    }
    'verify' {
        Write-Host '==> acceptance checks (verify_odoo.py)'
        Invoke-OdooShell 'verify_odoo.py'
        Write-Host '==> login checks (login_check.py)'
        Invoke-Compose @('exec', '-T', 'odoo', 'sh', '-c', 'python3 /opt/odoo-provision/login_check.py')
    }
    'fulfill' {
        Write-Host '==> stage-1 mapping + fulfilment checks (verify_fulfillment.py)'
        Invoke-OdooShell 'verify_fulfillment.py'
    }
    'login-check' {
        Invoke-Compose @('exec', '-T', 'odoo', 'sh', '-c', 'python3 /opt/odoo-provision/login_check.py')
    }
    'all' {
        & $MyInvocation.MyCommand.Path -Action init
        if ($LASTEXITCODE -ne 0) { throw 'init failed' }
        & $MyInvocation.MyCommand.Path -Action provision
        if ($LASTEXITCODE -ne 0) { throw 'provision failed' }
        & $MyInvocation.MyCommand.Path -Action verify
        if ($LASTEXITCODE -ne 0) { throw 'verify failed' }
        & $MyInvocation.MyCommand.Path -Action fulfill
        if ($LASTEXITCODE -ne 0) { throw 'fulfill failed' }
    }
    'status' {
        Invoke-Compose @('ps')
    }
    'logs' {
        Invoke-Compose @('logs', '-f', '--tail=100')
    }
    'down' {
        Invoke-Compose @('down')
        Write-Host 'Stopped (volumes kept). To wipe data: docker compose down -v (deletes all data).'
    }
}
