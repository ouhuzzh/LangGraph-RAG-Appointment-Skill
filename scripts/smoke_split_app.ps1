param(
    [int]$ApiPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$SkipInstall,
    [switch]$SkipChat
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$FrontendDir = Join-Path $Root "frontend"
$RuntimeDir = Join-Path $Root "runtime"
$PythonExe = Join-Path $Root "venv\Scripts\python.exe"
$ApiBase = "http://127.0.0.1:$ApiPort"
$FrontendBase = "http://127.0.0.1:$FrontendPort"

New-Item -ItemType Directory -Force $RuntimeDir | Out-Null

if (-not (Test-Path $PythonExe)) {
    throw "Virtual environment not found: $PythonExe"
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm is not available. Please install Node.js/npm first."
}

function Test-PortInUse([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1)
}

function Wait-HttpOk([string]$Url, [int]$TimeoutSeconds = 45) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $response
            }
        } catch {
            Start-Sleep -Milliseconds 800
        }
    } while ((Get-Date) -lt $deadline)
    throw "Timed out waiting for $Url"
}

if (-not $SkipInstall -and -not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Push-Location $FrontendDir
    try {
        npm install
    } finally {
        Pop-Location
    }
}

Push-Location $FrontendDir
try {
    npm run build
} finally {
    Pop-Location
}

$started = @()
try {
    if (-not (Test-PortInUse $ApiPort)) {
        $apiLog = Join-Path $RuntimeDir "smoke_api.log"
        $apiErr = Join-Path $RuntimeDir "smoke_api.err.log"
        $started += Start-Process `
            -FilePath $PythonExe `
            -ArgumentList "project\api_app.py" `
            -WorkingDirectory $Root `
            -RedirectStandardOutput $apiLog `
            -RedirectStandardError $apiErr `
            -WindowStyle Hidden `
            -PassThru
    }

    if (-not (Test-PortInUse $FrontendPort)) {
        $frontendLog = Join-Path $RuntimeDir "smoke_frontend.log"
        $frontendErr = Join-Path $RuntimeDir "smoke_frontend.err.log"
        $started += Start-Process `
            -FilePath "npm.cmd" `
            -ArgumentList "run dev -- --host 127.0.0.1 --port $FrontendPort" `
            -WorkingDirectory $FrontendDir `
            -RedirectStandardOutput $frontendLog `
            -RedirectStandardError $frontendErr `
            -WindowStyle Hidden `
            -PassThru
    }

    Wait-HttpOk "$ApiBase/api/health" | Out-Null
    Wait-HttpOk "$FrontendBase/" | Out-Null

    $status = Invoke-RestMethod -Uri "$ApiBase/api/system/status" -Method GET -TimeoutSec 20
    if (-not $status.state) {
        throw "System status response is missing state"
    }

    $session = Invoke-RestMethod -Uri "$ApiBase/api/chat/session" -Method POST -ContentType "application/json" -Body "{}" -TimeoutSec 20
    if (-not $session.thread_id) {
        throw "Session response is missing thread_id"
    }

    if (-not $SkipChat) {
        $encodedThread = [uri]::EscapeDataString($session.thread_id)
        $encodedMessage = [uri]::EscapeDataString("你好")
        $stream = Invoke-WebRequest -Uri "$ApiBase/api/chat/stream?thread_id=$encodedThread&message=$encodedMessage" -UseBasicParsing -TimeoutSec 120
        if ($stream.Content -notmatch "event: final" -and $stream.Content -notmatch "event: app-error") {
            throw "Chat stream did not emit a final or app-error event"
        }
        if ($stream.Content -match "聊天服务暂时不可用" -and $stream.Content -notmatch "event: app-error") {
            throw "Chat stream contains false service-unavailable copy"
        }
    }

    Write-Host "Split app smoke passed."
    Write-Host "API:      $ApiBase"
    Write-Host "Frontend: $FrontendBase"
} finally {
    foreach ($process in $started) {
        if ($process -and -not $process.HasExited) {
            Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        }
    }
}
