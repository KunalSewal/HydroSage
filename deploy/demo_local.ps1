<#
.SYNOPSIS
Runs HydroSage on this Windows machine exactly as it is deployed on the four
lab containers: two analysis API instances behind the load-balancing gateway,
which also serves the website. No Docker, database, Redis or MinIO needed.

.DESCRIPTION
First run sets up the backend virtualenv and frontend packages (a few
minutes); later runs start in ~20 seconds. Needs Python 3.12, Node 20+, and
OPENTOPOGRAPHY_API_KEY in backend\.env. Logs go to .demo\*.log.

.EXAMPLE
.\deploy\demo_local.ps1              # set up if needed, start, open the browser
.\deploy\demo_local.ps1 -SkipSetup   # start without reinstalling or rebuilding
.\deploy\demo_local.ps1 -Stop        # stop everything this script started
#>
param(
    [switch]$Stop,
    [switch]$SkipSetup,
    [switch]$NoBrowser,
    [int]$Port = 8080,
    [int[]]$ApiPorts = @(8101, 8102)
)

# Not 'Stop': Windows PowerShell 5.1 turns any stderr line from a native
# program (pip's upgrade notice, npm warnings) into a terminating error.
# Native steps check $LASTEXITCODE instead, and failures `throw` explicitly.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
$demo = Join-Path $root '.demo'
$pidFile = Join-Path $demo 'pids.txt'
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$python = Join-Path $backend '.venv\Scripts\python.exe'
$web = Join-Path $demo 'web'

function Stop-Demo {
    if (Test-Path $pidFile) {
        foreach ($id in Get-Content $pidFile) {
            # /T takes uvicorn's worker children down with it.
            & taskkill.exe /PID $id /T /F 2>&1 | Out-Null
        }
        Remove-Item $pidFile
    }
}

function Test-PortFree([int]$p) {
    -not (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}

if ($Stop) {
    Stop-Demo
    Write-Host 'HydroSage demo stopped.'
    return
}

Stop-Demo  # anything left over from a previous run
New-Item -ItemType Directory -Force $demo | Out-Null

foreach ($p in @($Port) + $ApiPorts) {
    if (-not (Test-PortFree $p)) {
        throw "Port $p is already in use by another program. Pick others, e.g. -Port 8090 -ApiPorts 8111,8112"
    }
}

if (-not $SkipSetup) {
    if (-not (Test-Path $python)) {
        Write-Host 'Creating the backend virtualenv...'
        & py -3.12 -m venv (Join-Path $backend '.venv')
        if ($LASTEXITCODE -ne 0) { throw 'could not create the virtualenv; is Python 3.12 installed?' }
    }
    Write-Host 'Installing backend packages (quick if already installed)...'
    # Through cmd so pip's stderr notices merge into ordinary output instead
    # of rendering as PowerShell error records.
    & cmd.exe /c "`"$python`" -m pip install -q --disable-pip-version-check -e `"$backend`" 2>&1"
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }

    Write-Host 'Installing frontend packages and building the site...'
    Push-Location $frontend
    try {
        & npm install --no-audit --no-fund --loglevel=error
        if ($LASTEXITCODE -ne 0) { throw 'npm install failed' }
        # Same build CI publishes for the lab deployment (frontend\.env.deploy).
        & npx vite build --mode deploy --outDir $web --emptyOutDir --logLevel error
        if ($LASTEXITCODE -ne 0) { throw 'frontend build failed' }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path (Join-Path $web 'index.html'))) {
    throw "No built site in $web; run once without -SkipSetup."
}

# Settings go through uvicorn's --env-file rather than $env: because two of
# them are deliberately empty, and Windows PowerShell deletes a variable that
# is set to an empty string. backend\.env (with the API key) is still read.
$apiEnv = Join-Path $demo 'api.env'
@(
    'REDIS_URL='                                       # no Redis: in-process catchment cache
    "DEM_CACHE_DIR=$(Join-Path $demo 'dem-cache')"     # no MinIO: elevation cached on disk
    'CORS_ALLOWED_ORIGINS='                            # same origin through the gateway
) | Set-Content -Encoding ascii $apiEnv

$gatewayEnv = Join-Path $demo 'gateway.env'
@(
    "GATEWAY_BACKENDS=$(($ApiPorts | ForEach-Object { "http://127.0.0.1:$_" }) -join ',')"
    "GATEWAY_STATIC_DIR=$web"
) | Set-Content -Encoding ascii $gatewayEnv

function Start-Uvicorn([string]$name, [string]$module, [int]$p, [string]$envFile) {
    $uvicornArgs = @('-m', 'uvicorn', $module, '--host', '127.0.0.1', '--port', "$p", '--env-file', "`"$envFile`"")
    $process = Start-Process -FilePath $python -ArgumentList $uvicornArgs -WorkingDirectory $backend `
        -RedirectStandardOutput (Join-Path $demo "$name.log") `
        -RedirectStandardError (Join-Path $demo "$name.err.log") `
        -WindowStyle Hidden -PassThru
    Add-Content $pidFile $process.Id
}

Write-Host 'Starting two analysis instances and the gateway...'
$i = 1
foreach ($p in $ApiPorts) {
    Start-Uvicorn "api$i" 'app.analyze_only:app' $p $apiEnv
    $i++
}
Start-Uvicorn 'gateway' 'app.gateway:app' $Port $gatewayEnv

# The analysis instances take ~15-20 s to import the geospatial libraries.
$deadline = (Get-Date).AddSeconds(90)
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        $status = Invoke-RestMethod "http://127.0.0.1:$Port/gateway/status" -TimeoutSec 3
        $up = @($ApiPorts | Where-Object {
            try { (Invoke-RestMethod "http://127.0.0.1:$_/health" -TimeoutSec 3).status -eq 'ok' } catch { $false }
        })
        if ($up.Count -eq $ApiPorts.Count) { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 2
}

if (-not $ready) {
    Write-Warning "Not everything answered within 90 s. Check the logs in $demo, then run with -Stop."
    return
}

$url = "http://localhost:$Port"
Write-Host ''
Write-Host "HydroSage is running at $url" -ForegroundColor Green
Write-Host "  Fleet status: $url/gateway/status"
Write-Host "  API docs:     $url/docs"
Write-Host "  Stop it with: .\deploy\demo_local.ps1 -Stop"
if (-not $NoBrowser) { Start-Process $url }
