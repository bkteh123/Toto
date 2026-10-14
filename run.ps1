# One-command launcher for Royal Yellow Analyzer (no Docker needed).
#   .\run.cmd            first run: creates the venv, installs deps, then starts everything
#   .\run.cmd -NoBrowser don't open the browser
# Ctrl+C stops all services. Data lives in %LOCALAPPDATA%\RoyalYellow.
param([switch]$NoBrowser, [switch]$Reinstall)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$venv = Join-Path $env:USERPROFILE '.venvs\royal-yellow'   # outside OneDrive on purpose
$py = Join-Path $venv 'Scripts\python.exe'
$req = Join-Path $root 'backend\requirements-dev.txt'

function Fail($m) { Write-Host "[royal-yellow] ERROR: $m" -ForegroundColor Red; exit 1 }

# Node installed via winget may not be on PATH of an already-open shell.
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    $node = 'C:\Program Files\nodejs'
    if (Test-Path (Join-Path $node 'npm.cmd')) { $env:Path = "$node;$env:Path" }
    else { Fail 'Node.js not found. Install it: winget install OpenJS.NodeJS.LTS  (then reopen the terminal)' }
}

# --- Python virtualenv -------------------------------------------------------
if (-not (Test-Path $py)) {
    Write-Host '[royal-yellow] creating virtualenv (first run)...'
    New-Item -ItemType Directory -Force (Split-Path $venv) | Out-Null
    if (Get-Command py -ErrorAction SilentlyContinue) { py -3.12 -m venv $venv }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { python -m venv $venv }
    else { Fail 'Python 3.11+ not found. Install it: winget install Python.Python.3.12' }
    if ($LASTEXITCODE -ne 0) { Fail 'could not create the virtualenv (Python 3.12 expected)' }
}

# --- Python dependencies (re-installed only when requirements change) --------
$stamp = Join-Path $venv '.requirements.sha256'
$hash = (Get-FileHash $req -Algorithm SHA256).Hash + (Get-FileHash (Join-Path $root 'backend\requirements.txt') -Algorithm SHA256).Hash
if ($Reinstall -or -not (Test-Path $stamp) -or (Get-Content $stamp -Raw).Trim() -ne $hash) {
    Write-Host '[royal-yellow] installing Python dependencies...'
    & $py -m pip install --disable-pip-version-check -q -r $req
    if ($LASTEXITCODE -ne 0) { Fail 'pip install failed' }
    Set-Content -Path $stamp -Value $hash -Encoding ascii
}

# --- Frontend dependencies ---------------------------------------------------
$fe = Join-Path $root 'frontend'
if ($Reinstall -or -not (Test-Path (Join-Path $fe 'node_modules\.package-lock.json'))) {
    Write-Host '[royal-yellow] installing frontend dependencies (first run, can take a minute)...'
    Push-Location $fe
    try { npm.cmd ci --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { Fail 'npm ci failed' } }
    finally { Pop-Location }
}

# --- Go ----------------------------------------------------------------------
$argsList = @('-I', (Join-Path $root 'scripts\run_local.py'))
if ($NoBrowser) { $argsList += '--no-browser' }
& $py @argsList
exit $LASTEXITCODE
