param(
    [int]$ApiPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$RuntimeDir = Join-Path $Root "runtime"
$FrontendDir = Join-Path $Root "frontend"
$PythonExe = Join-Path $Root "venv\Scripts\python.exe"

New-Item -ItemType Directory -Force $RuntimeDir | Out-Null

if (-not (Test-Path $PythonExe)) {
    throw "Virtual environment not found: $PythonExe. Please create venv and install requirements first."
}

if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is not available. Please install Node.js/npm first."
}

if (-not $SkipInstall -and -not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "Installing frontend dependencies..."
    Push-Location $FrontendDir
    try {
        npm install
    } finally {
        Pop-Location
    }
}

$apiLog = Join-Path $RuntimeDir "api_server.log"
$apiErr = Join-Path $RuntimeDir "api_server.err.log"
$frontendLog = Join-Path $RuntimeDir "frontend_server.log"
$frontendErr = Join-Path $RuntimeDir "frontend_server.err.log"

$existingApi = Get-NetTCPConnection -LocalPort $ApiPort -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $existingApi) {
    Write-Host "Starting FastAPI backend on http://127.0.0.1:$ApiPort ..."
    Start-Process `
        -FilePath $PythonExe `
        -ArgumentList "project\api_app.py" `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $apiLog `
        -RedirectStandardError $apiErr `
        -WindowStyle Hidden
} else {
    Write-Host "FastAPI backend already appears to be running on port $ApiPort."
}

$existingFrontend = Get-NetTCPConnection -LocalPort $FrontendPort -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $existingFrontend) {
    Write-Host "Starting React frontend on http://127.0.0.1:$FrontendPort ..."
    Start-Process `
        -FilePath "npm.cmd" `
        -ArgumentList "run dev -- --host 127.0.0.1 --port $FrontendPort" `
        -WorkingDirectory $FrontendDir `
        -RedirectStandardOutput $frontendLog `
        -RedirectStandardError $frontendErr `
        -WindowStyle Hidden
} else {
    Write-Host "React frontend already appears to be running on port $FrontendPort."
}

Start-Sleep -Seconds 3

Write-Host ""
Write-Host "User frontend: http://127.0.0.1:$FrontendPort"
Write-Host "API docs:      http://127.0.0.1:$ApiPort/docs"
Write-Host "API health:    http://127.0.0.1:$ApiPort/api/health"
Write-Host ""
Write-Host "Logs:"
Write-Host "  $apiLog"
Write-Host "  $apiErr"
Write-Host "  $frontendLog"
Write-Host "  $frontendErr"

