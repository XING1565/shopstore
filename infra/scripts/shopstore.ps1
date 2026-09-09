# infra/scripts/shopstore.ps1 — ShopVidi stage-0 one-click orchestration (ops / ISSUE-0010).
# Windows entry point (PowerShell 5.1+). Linux/macOS/Git Bash users can use shopstore.sh.
# Full docs: infra/scripts/README.md.
#
# Commands (see README for details):
#   init        first-time bring-up: create .env files, start all stacks, run migrations
#   start       start all stacks (Woo, Odoo, Core)
#   stop        stop all stacks (data volumes kept)
#   status      per-service container status + HTTP health checks
#   logs        tail logs -Service woo|odoo|core|all [-Follow] [-Tail N]
#   seed        idempotent test-data import (reuses packages/test-data/scripts)
#   backup      dump all databases + stateful files into backups\<timestamp>\
#   restore     restore from a backup directory (-BackupDir <path>)
#   test-smoke  ops-level smoke checks (HTTP endpoints + integration mock chain)
#
# Stage-0 note: the Integration Layer is a library with no long-running service;
# it is validated through its test suite in `test-smoke`.

param(
    [Parameter(Position = 0, Mandatory = $true)]
    [ValidateSet('init', 'start', 'stop', 'status', 'logs', 'seed', 'backup', 'restore', 'test-smoke', 'help')]
    [string]$Command,

    [ValidateSet('woo', 'odoo', 'core', 'all')]
    [string]$Service = 'all',

    [switch]$Follow,

    [int]$Tail = 100,

    [string]$BackupDir
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path

$WooComposeFile    = Join-Path $RepoRoot 'apps\woo\compose.yaml'
$OdooComposeFile   = Join-Path $RepoRoot 'apps\odoo\config\docker\compose.yaml'
$OdooProjectDir    = Join-Path $RepoRoot 'apps\odoo\config\docker'
$CoreComposeFile   = Join-Path $RepoRoot 'infra\docker\compose.yaml'

$WooEnvFile        = Join-Path $RepoRoot 'apps\woo\.env'
$OdooEnvFile       = Join-Path $RepoRoot 'apps\odoo\config\docker\.env'
$CoreEnvFile       = Join-Path $RepoRoot 'apps\core\.env'
$IntegrationEnvFile = Join-Path $RepoRoot 'apps\integration\.env'
$BackupRoot        = Join-Path $RepoRoot 'backups'

$WooComposeArgs  = @('-f', $WooComposeFile)
$OdooComposeArgs = @('-f', $OdooComposeFile, '--project-directory', $OdooProjectDir)
$CoreComposeArgs = @('-f', $CoreComposeFile, '--env-file', $CoreEnvFile)

$OdooRunPs1 = Join-Path $RepoRoot 'apps\odoo\config\provision\run.ps1'
$SeedPs1    = Join-Path $RepoRoot 'packages\test-data\scripts\init-test-data.ps1'

# Run a native command with $ErrorActionPreference lowered, so that stderr does not
# become a terminating NativeCommandError (PowerShell 5.1 quirk when EAP = Stop).
# -Silent discards all output (health probes); otherwise stderr is merged to stdout
# (2>&1) so it prints normally. Stores the exit code in $script:LastNativeExit.
function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)][string]$File,
        [Parameter(Mandatory = $true)][string[]]$Args,
        [switch]$Silent
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    if ($Silent) { & $File @Args *> $null } else { & $File @Args 2>&1 }
    $script:LastNativeExit = $LASTEXITCODE
    $ErrorActionPreference = $prev
}

function Invoke-Compose {
    param([Parameter(Mandatory = $true)][string[]]$Args)
    Invoke-Native -File 'docker' -Args (@('compose') + $Args)
    if ($script:LastNativeExit -ne 0) { throw "docker compose $($Args -join ' ') failed (exit $($script:LastNativeExit))" }
}

function Get-EnvValue {
    param([string]$FilePath, [string]$Key, [string]$Default = '')
    if (-not (Test-Path -LiteralPath $FilePath)) { return $Default }
    $line = Get-Content -LiteralPath $FilePath -Encoding UTF8 |
        Where-Object { $_ -match "^[ \t]*$([regex]::Escape($Key))[ \t]*=" } |
        Select-Object -First 1
    if ($line) {
        $value = ($line -split '=', 2)[1]
        $value = $value -replace '[ \t]*#.*$', ''
        $value = $value.Trim().Trim('"').Trim("'")
        if ($value) { return $value }
    }
    return $Default
}

function Assert-Docker {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'docker not found on PATH. Install Docker Desktop / Docker Engine.'
    }
    Invoke-Native -File 'docker' -Args @('info') -Silent
    if ($script:LastNativeExit -ne 0) { throw 'docker daemon is not running. Start Docker Desktop first.' }
    Invoke-Native -File 'docker' -Args @('compose', 'version') -Silent
    if ($script:LastNativeExit -ne 0) { throw 'docker compose (Compose V2) not found.' }
}

function Assert-EnvFiles {
    foreach ($f in @($WooEnvFile, $OdooEnvFile, $CoreEnvFile, $IntegrationEnvFile)) {
        if (-not (Test-Path -LiteralPath $f)) {
            throw "missing .env file: $f  (run: .\infra\scripts\shopstore.ps1 init)"
        }
    }
}

function Initialize-EnvFiles {
    $pairs = @(
        @( (Join-Path $RepoRoot 'infra\env\woo.env.example'),  $WooEnvFile ),
        @( (Join-Path $RepoRoot 'infra\env\odoo.env.example'), $OdooEnvFile ),
        @( (Join-Path $RepoRoot 'infra\env\core.env.example'), $CoreEnvFile ),
        @( (Join-Path $RepoRoot 'infra\env\integration.env.example'), $IntegrationEnvFile )
    )
    foreach ($p in $pairs) {
        if (-not (Test-Path -LiteralPath $p[1])) {
            Copy-Item -LiteralPath $p[0] -Destination $p[1]
            Write-Host ("  created {0}" -f $p[1])
        }
    }
}

function Invoke-OdooRunScript {
    param([string]$Action)
    Invoke-Native -File 'powershell' -Args @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $OdooRunPs1, '-Action', $Action)
    if ($script:LastNativeExit -ne 0) { throw "odoo run.ps1 -Action $Action failed" }
}

function Test-Http {
    param([string]$Url)
    try {
        $null = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5 -MaximumRedirection 5
        return $true
    }
    catch { return $false }
}

function Show-HttpCheck {
    param([string]$Label, [string]$Url)
    if (Test-Http -Url $Url) {
        Write-Host ("  PASS  {0}" -f $Label)
        return $true
    }
    Write-Host ("  FAIL  {0}" -f $Label) -ForegroundColor Red
    return $false
}

function Get-Ports {
    $script:WooPort  = Get-EnvValue $WooEnvFile  'WOO_PORT' '8080'
    $script:CorePort = Get-EnvValue $CoreEnvFile 'APP_PORT' '8000'
    $script:OdooPort = Get-EnvValue $OdooEnvFile 'ODOO_HTTP_PORT' '8069'
}

function Invoke-Init {
    Assert-Docker
    Write-Host '==> creating .env files from templates (existing files kept)'
    Initialize-EnvFiles

    Write-Host '==> [Woo] build + start (auto-provisions WP/WooCommerce + test data)'
    Invoke-Compose @($WooComposeArgs + @('up', '-d', '--build'))

    Write-Host '==> [Odoo] init db + install sale/stock + provision + verify'
    Invoke-OdooRunScript 'all'

    Write-Host '==> [Core] build + start core-db + core'
    Invoke-Compose @($CoreComposeArgs + @('up', '-d', '--build'))

    Write-Host '==> [Core] waiting for core-db readiness'
    $ready = $false
    $probe = $CoreComposeArgs + @('exec', '-T', 'core-db', 'pg_isready')
    for ($i = 0; $i -lt 30; $i++) {
        Invoke-Native -File 'docker' -Args (@('compose') + $probe) -Silent
        if ($script:LastNativeExit -eq 0) { $ready = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $ready) { throw 'core-db did not become ready in time' }

    Write-Host '==> [Core] running database migrations'
    Invoke-Compose @($CoreComposeArgs + @('run', '--rm', 'core', 'alembic', '-c', 'migrations/alembic.ini', 'upgrade', 'head'))

    Write-Host 'done. Verify with: status  /  (re)import test data with: seed'
}

function Invoke-Start {
    Assert-Docker
    Assert-EnvFiles
    Write-Host '==> [Woo] starting'
    Invoke-Compose @($WooComposeArgs + @('up', '-d'))
    Write-Host '==> [Odoo] starting'
    Invoke-OdooRunScript 'up'
    Write-Host '==> [Core] starting'
    Invoke-Compose @($CoreComposeArgs + @('up', '-d'))
    Write-Host 'done. Verify with: status'
}

function Invoke-Stop {
    Assert-Docker
    Write-Host '==> [Core] stopping'
    Invoke-Compose @($CoreComposeArgs + @('down'))
    Write-Host '==> [Odoo] stopping'
    Invoke-OdooRunScript 'down'
    Write-Host '==> [Woo] stopping'
    Invoke-Compose @($WooComposeArgs + @('down'))
    Write-Host 'done. Data volumes kept; restart with: start'
}

function Invoke-Status {
    Assert-Docker
    Write-Host '==> [Woo] compose ps'
    Invoke-Compose @($WooComposeArgs + @('ps'))
    Write-Host '==> [Odoo] compose ps'
    Invoke-Compose @($OdooComposeArgs + @('ps'))
    Write-Host '==> [Core] compose ps'
    Invoke-Compose @($CoreComposeArgs + @('ps'))

    Get-Ports
    Write-Host '==> HTTP health checks'
    Show-HttpCheck 'Woo front'    ("http://localhost:{0}/" -f $WooPort)
    Show-HttpCheck 'Core /health' ("http://localhost:{0}/health" -f $CorePort)
    Show-HttpCheck 'Odoo web'     ("http://localhost:{0}/web/login" -f $OdooPort)
}

function Invoke-Logs {
    Assert-Docker
    $followArgs = @()
    if ($Follow) { $followArgs = @('-f') }
    $tailArg = @('--tail', $Tail.ToString())
    switch ($Service) {
        'woo'  { Invoke-Compose @($WooComposeArgs + @('logs') + $followArgs + $tailArg) }
        'odoo' { Invoke-Compose @($OdooComposeArgs + @('logs') + $followArgs + $tailArg) }
        'core' { Invoke-Compose @($CoreComposeArgs + @('logs') + $followArgs + $tailArg) }
        'all'  {
            Write-Host '==> [Woo] logs';  Invoke-Compose @($WooComposeArgs + @('logs') + $followArgs + $tailArg)
            Write-Host '==> [Odoo] logs'; Invoke-Compose @($OdooComposeArgs + @('logs') + $followArgs + $tailArg)
            Write-Host '==> [Core] logs'; Invoke-Compose @($CoreComposeArgs + @('logs') + $followArgs + $tailArg)
        }
    }
}

function Invoke-Seed {
    Assert-Docker
    Assert-EnvFiles
    Write-Host '==> importing canonical test data (Woo + Odoo, idempotent)'
    Invoke-Native -File 'powershell' -Args @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $SeedPs1)
    if ($script:LastNativeExit -ne 0) { throw 'test-data import failed' }
    Write-Host 'done. See docs/测试数据说明.md for expected data.'
}

function Invoke-Backup {
    Assert-Docker
    Assert-EnvFiles
    $ts = Get-Date -Format 'yyyyMMdd-HHmmss'
    $out = Join-Path $BackupRoot $ts
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    Write-Host "==> backing up into $out"

    $wpDbRoot     = Get-EnvValue $WooEnvFile  'WP_DB_ROOT_PASSWORD' ''
    $wpDbName     = Get-EnvValue $WooEnvFile  'WP_DB_NAME' 'shopstore_woo'
    $odooDbUser   = Get-EnvValue $OdooEnvFile 'ODOO_DB_USER' 'odoo'
    $odooDbName   = Get-EnvValue $OdooEnvFile 'ODOO_DB_NAME' 'shopstore_odoo'
    $coreDbUser   = Get-EnvValue $CoreEnvFile 'DB_USERNAME' 'core'
    $coreDbName   = Get-EnvValue $CoreEnvFile 'DB_DATABASE' 'shopstore_core'

    Write-Host "==> [Woo] dumping MySQL ($wpDbName)"
    Invoke-Compose @($WooComposeArgs + @('exec', '-T', '-e', "MYSQL_PWD=$wpDbRoot", 'db',
        'mysqldump', '-uroot', '--single-transaction', '--routines', '--triggers', '--result-file=/tmp/woo.sql', $wpDbName))
    Invoke-Compose @($WooComposeArgs + @('cp', 'db:/tmp/woo.sql', (Join-Path $out 'woo-mysql.sql')))
    Invoke-Compose @($WooComposeArgs + @('exec', '-T', 'db', 'rm', '-f', '/tmp/woo.sql'))

    Write-Host '==> [Woo] archiving wp-content/uploads'
    Invoke-Compose @($WooComposeArgs + @('exec', '-T', 'woo', 'tar', '-C', '/var/www/html', '-czf', '/tmp/woo-uploads.tar.gz', 'wp-content/uploads'))
    Invoke-Compose @($WooComposeArgs + @('cp', 'woo:/tmp/woo-uploads.tar.gz', (Join-Path $out 'woo-uploads.tar.gz')))
    Invoke-Compose @($WooComposeArgs + @('exec', '-T', 'woo', 'rm', '-f', '/tmp/woo-uploads.tar.gz'))

    Write-Host "==> [Odoo] dumping PostgreSQL ($odooDbName)"
    Invoke-Compose @($OdooComposeArgs + @('exec', '-T', 'db', 'pg_dump', '-U', $odooDbUser, '-Fc', '--file=/tmp/odoo.pgdump', $odooDbName))
    Invoke-Compose @($OdooComposeArgs + @('cp', 'db:/tmp/odoo.pgdump', (Join-Path $out 'odoo-postgres.pgdump')))
    Invoke-Compose @($OdooComposeArgs + @('exec', '-T', 'db', 'rm', '-f', '/tmp/odoo.pgdump'))

    Write-Host '==> [Odoo] archiving filestore'
    Invoke-Compose @($OdooComposeArgs + @('exec', '-T', 'odoo', 'tar', '-C', '/var/lib/odoo', '-czf', '/tmp/odoo-filestore.tar.gz', 'filestore'))
    Invoke-Compose @($OdooComposeArgs + @('cp', 'odoo:/tmp/odoo-filestore.tar.gz', (Join-Path $out 'odoo-filestore.tar.gz')))
    Invoke-Compose @($OdooComposeArgs + @('exec', '-T', 'odoo', 'rm', '-f', '/tmp/odoo-filestore.tar.gz'))

    Write-Host "==> [Core] dumping PostgreSQL ($coreDbName)"
    Invoke-Compose @($CoreComposeArgs + @('exec', '-T', 'core-db', 'pg_dump', '-U', $coreDbUser, '-Fc', '--file=/tmp/core.pgdump', $coreDbName))
    Invoke-Compose @($CoreComposeArgs + @('cp', 'core-db:/tmp/core.pgdump', (Join-Path $out 'core-postgres.pgdump')))
    Invoke-Compose @($CoreComposeArgs + @('exec', '-T', 'core-db', 'rm', '-f', '/tmp/core.pgdump'))

    Invoke-Native -File 'git' -Args @('-C', $RepoRoot, 'rev-parse', 'HEAD') -Silent
    $commit = 'unknown'
    if ($script:LastNativeExit -eq 0) { $commit = (git -C $RepoRoot rev-parse HEAD).Trim() }
    $manifest = @(
        '# Shopstore backup manifest',
        "created: $(Get-Date -Format o)",
        "commit:  $commit",
        'files:',
        (Get-ChildItem -LiteralPath $out -Name)
    )
    $manifest | Out-File -LiteralPath (Join-Path $out 'manifest.txt') -Encoding UTF8

    Write-Host "backup complete: $out"
}

function Invoke-Restore {
    Assert-Docker
    Assert-EnvFiles
    if (-not $BackupDir) { throw 'usage: shopstore.ps1 restore -BackupDir <path>' }
    if (-not (Test-Path -LiteralPath $BackupDir)) { throw "backup dir not found: $BackupDir" }

    $appEnv = Get-EnvValue $CoreEnvFile 'APP_ENV' 'local'
    if ($appEnv -ne 'local' -and $appEnv -ne 'staging') {
        throw "refusing to restore into APP_ENV='$appEnv' (only local/staging supported)"
    }

    Write-Host "==> This will OVERWRITE Woo/Odoo/Core data from: $BackupDir"
    if ($env:CONFIRM -ne 'yes') {
        Write-Host 'Re-run with $env:CONFIRM="yes" to proceed. See infra/RESTORE.md.'
        return
    }

    $wpDbRoot     = Get-EnvValue $WooEnvFile  'WP_DB_ROOT_PASSWORD' ''
    $wpDbName     = Get-EnvValue $WooEnvFile  'WP_DB_NAME' 'shopstore_woo'
    $odooDbUser   = Get-EnvValue $OdooEnvFile 'ODOO_DB_USER' 'odoo'
    $odooDbName   = Get-EnvValue $OdooEnvFile 'ODOO_DB_NAME' 'shopstore_odoo'
    $coreDbUser   = Get-EnvValue $CoreEnvFile 'DB_USERNAME' 'core'
    $coreDbName   = Get-EnvValue $CoreEnvFile 'DB_DATABASE' 'shopstore_core'

    Write-Host '==> [Core] restoring PostgreSQL'
    Invoke-Compose @($CoreComposeArgs + @('stop', 'core'))
    Invoke-Compose @($CoreComposeArgs + @('cp', (Join-Path $BackupDir 'core-postgres.pgdump'), 'core-db:/tmp/core.pgdump'))
    Invoke-Compose @($CoreComposeArgs + @('exec', '-T', 'core-db', 'dropdb', '-U', $coreDbUser, '--if-exists', $coreDbName))
    Invoke-Compose @($CoreComposeArgs + @('exec', '-T', 'core-db', 'createdb', '-U', $coreDbUser, $coreDbName))
    Invoke-Compose @($CoreComposeArgs + @('exec', '-T', 'core-db', 'pg_restore', '-U', $coreDbUser, '-d', $coreDbName, '--no-owner', "--role=$coreDbUser", '/tmp/core.pgdump'))
    Invoke-Compose @($CoreComposeArgs + @('exec', '-T', 'core-db', 'rm', '-f', '/tmp/core.pgdump'))
    Invoke-Compose @($CoreComposeArgs + @('start', 'core'))

    Write-Host '==> [Odoo] restoring PostgreSQL + filestore'
    Invoke-Compose @($OdooComposeArgs + @('stop', 'odoo'))
    Invoke-Compose @($OdooComposeArgs + @('cp', (Join-Path $BackupDir 'odoo-postgres.pgdump'), 'db:/tmp/odoo.pgdump'))
    Invoke-Compose @($OdooComposeArgs + @('exec', '-T', 'db', 'dropdb', '-U', $odooDbUser, '--if-exists', $odooDbName))
    Invoke-Compose @($OdooComposeArgs + @('exec', '-T', 'db', 'createdb', '-U', $odooDbUser, $odooDbName))
    Invoke-Compose @($OdooComposeArgs + @('exec', '-T', 'db', 'pg_restore', '-U', $odooDbUser, '-d', $odooDbName, '--no-owner', "--role=$odooDbUser", '/tmp/odoo.pgdump'))
    Invoke-Compose @($OdooComposeArgs + @('exec', '-T', 'db', 'rm', '-f', '/tmp/odoo.pgdump'))
    $filestoreArchive = Join-Path $BackupDir 'odoo-filestore.tar.gz'
    if (Test-Path -LiteralPath $filestoreArchive) {
        Invoke-Compose @($OdooComposeArgs + @('cp', $filestoreArchive, 'odoo:/tmp/odoo-filestore.tar.gz'))
        Invoke-Compose @($OdooComposeArgs + @('exec', '-T', 'odoo', 'sh', '-c', 'rm -rf /var/lib/odoo/filestore && mkdir -p /var/lib/odoo && tar -C /var/lib/odoo -xzf /tmp/odoo-filestore.tar.gz'))
        Invoke-Compose @($OdooComposeArgs + @('exec', '-T', 'odoo', 'rm', '-f', '/tmp/odoo-filestore.tar.gz'))
    }
    Invoke-Compose @($OdooComposeArgs + @('start', 'odoo'))

    Write-Host '==> [Woo] restoring MySQL + uploads'
    Invoke-Compose @($WooComposeArgs + @('stop', 'woo'))
    Invoke-Compose @($WooComposeArgs + @('cp', (Join-Path $BackupDir 'woo-mysql.sql'), 'db:/tmp/woo.sql'))
    # mysqldump emits DROP TABLE IF EXISTS + CREATE TABLE per table, so re-importing
    # into the existing database overwrites the data. The redirect runs inside the
    # container (no host-shell redirection, so no PowerShell encoding pitfalls).
    Invoke-Compose @($WooComposeArgs + @('exec', '-T', '-e', "MYSQL_PWD=$wpDbRoot", 'db', 'sh', '-c', 'mysql -uroot $MYSQL_DATABASE < /tmp/woo.sql'))
    Invoke-Compose @($WooComposeArgs + @('exec', '-T', 'db', 'rm', '-f', '/tmp/woo.sql'))
    $uploadsArchive = Join-Path $BackupDir 'woo-uploads.tar.gz'
    if (Test-Path -LiteralPath $uploadsArchive) {
        Invoke-Compose @($WooComposeArgs + @('cp', $uploadsArchive, 'woo:/tmp/woo-uploads.tar.gz'))
        Invoke-Compose @($WooComposeArgs + @('exec', '-T', 'woo', 'tar', '-C', '/var/www/html', '-xzf', '/tmp/woo-uploads.tar.gz'))
        Invoke-Compose @($WooComposeArgs + @('exec', '-T', 'woo', 'rm', '-f', '/tmp/woo-uploads.tar.gz'))
    }
    Invoke-Compose @($WooComposeArgs + @('start', 'woo'))

    Write-Host 'restore complete. Verify with: test-smoke'
}

function Invoke-TestSmoke {
    Assert-Docker
    Assert-EnvFiles
    Get-Ports
    $ok = $true
    Write-Host '==> ops smoke checks'
    if (-not (Show-HttpCheck 'Woo front'    ("http://localhost:{0}/" -f $WooPort))) { $ok = $false }
    if (-not (Show-HttpCheck 'Core /health' ("http://localhost:{0}/health" -f $CorePort))) { $ok = $false }
    if (-not (Show-HttpCheck 'Core /ready'  ("http://localhost:{0}/ready" -f $CorePort))) { $ok = $false }
    if (-not (Show-HttpCheck 'Odoo web'     ("http://localhost:{0}/web/login" -f $OdooPort))) { $ok = $false }

    Write-Host '==> [Integration] running mock-chain test suite'
    $smokeArgs = $CoreComposeArgs + @('run', '--rm', 'integration-tests')
    Invoke-Native -File 'docker' -Args (@('compose', '--profile', 'tests') + $smokeArgs)
    if ($script:LastNativeExit -eq 0) {
        Write-Host '  PASS  integration mock chain'
    }
    else {
        Write-Host '  FAIL  integration mock chain' -ForegroundColor Red
        $ok = $false
    }

    Write-Host 'Note: the full QA smoke suite (tests/smoke, ISSUE-0009) is separate.'
    if (-not $ok) { throw 'smoke checks failed' }
}

function Show-Usage {
    @'
usage: .\infra\scripts\shopstore.ps1 <command> [options]

commands:
  init        first-time bring-up (env files, start all, migrations)
  start       start all stacks
  stop        stop all stacks (volumes kept)
  status      container status + HTTP health checks
  logs        tail logs
  seed        idempotent test-data import
  backup      dump databases + stateful files
  restore     restore from a backup directory
  test-smoke  ops-level smoke checks

options:
  -Service woo|odoo|core|all   (logs)
  -Follow                      (logs)
  -Tail N                      (logs, default 100)
  -BackupDir <path>            (restore)

environment:
  $env:CONFIRM = "yes"         (restore: acknowledge overwrite)
'@
}

switch ($Command) {
    'init'       { Invoke-Init }
    'start'      { Invoke-Start }
    'stop'       { Invoke-Stop }
    'status'     { Invoke-Status }
    'logs'       { Invoke-Logs }
    'seed'       { Invoke-Seed }
    'backup'     { Invoke-Backup }
    'restore'    { Invoke-Restore }
    'test-smoke' { Invoke-TestSmoke }
    'help'       { Show-Usage }
}
