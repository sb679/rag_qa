$ErrorActionPreference = 'Stop'

$root = $PSScriptRoot
$ragQaRoot = Join-Path $root 'rag_qa'
$pythonExe = if ($env:EDURAG_PYTHON_EXE) { $env:EDURAG_PYTHON_EXE } else { Join-Path $ragQaRoot '.venv\Scripts\python.exe' }
$backendDir = Join-Path $ragQaRoot 'web\backend'
$frontendDir = Join-Path $ragQaRoot 'web\frontend'
$frontendNodeModules = Join-Path $frontendDir 'node_modules'
$frontendPackageLock = Join-Path $frontendDir 'package-lock.json'
$launcherLogDir = Join-Path $ragQaRoot 'logs\launcher'
$launchId = [guid]::NewGuid().ToString('N').Substring(0, 8)
$backendLog = Join-Path $launcherLogDir "backend-$launchId.log"
$frontendLog = Join-Path $launcherLogDir "frontend-$launchId.log"
$backendOutLog = "$backendLog.out"
$backendErrLog = "$backendLog.err"
$frontendOutLog = "$frontendLog.out"
$frontendErrLog = "$frontendLog.err"
$preferredBackendPort = 8000
$fallbackBackendPort = 8001
$preferredFrontendPort = 5173
$fallbackFrontendPort = 5174
$backendPort = $preferredBackendPort
$frontendPort = $preferredFrontendPort
$frontendUrl = "http://127.0.0.1:$frontendPort/"
$backendUrl = "http://127.0.0.1:$backendPort/docs"

function Write-Section {
    param([string]$Title)
    Write-Host ''
    Write-Host "=== $Title ==="
}

function Test-PortOpen {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutMs = 500
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $async = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        $waitHandle = $async.AsyncWaitHandle
        if (-not $waitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }

        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Wait-ForPort {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [int]$TimeoutSeconds = 180,
        [string]$Name = 'service'
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortOpen -Port $Port) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }

    throw "$Name did not start within $TimeoutSeconds seconds on port $Port."
}

function Test-HttpUrl {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSec = 2
    )

    try {
        $response = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec $TimeoutSec
        return @{ Ok = $true; Data = $response }
    } catch {
        return @{ Ok = $false; Data = $null }
    }
}

function Wait-ForHttp {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$TimeoutSeconds = 180,
        [string]$Name = 'service'
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $result = Test-HttpUrl -Url $Url
        if ($result.Ok) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    }

    throw "$Name did not become ready within $TimeoutSeconds seconds at $Url."
}

function Get-FreePort {
    param(
        [Parameter(Mandatory = $true)][int[]]$Candidates,
        [Parameter(Mandatory = $true)][string]$Name
    )

    foreach ($candidate in $Candidates) {
        if (-not (Test-PortOpen -Port $candidate)) {
            return $candidate
        }
    }

    throw "No free port found for $Name. Tried: $($Candidates -join ', ')."
}

function Start-LoggedProcess {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [Parameter(Mandatory = $true)][string]$LogFile
    )

    $logDir = Split-Path -Parent $LogFile
    if (-not (Test-Path $logDir)) {
        New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    }

    if (Test-Path $LogFile) {
        Remove-Item $LogFile -Force
    }

    $stdout = "$LogFile.out"
    $stderr = "$LogFile.err"
    if (Test-Path $stdout) { Remove-Item $stdout -Force }
    if (Test-Path $stderr) { Remove-Item $stderr -Force }

    return Start-Process -FilePath $FilePath -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
}

Write-Section 'EduRAG launcher'
Write-Host "Workspace root: $root"

if (-not (Test-Path $pythonExe)) {
    throw "Python interpreter not found: $pythonExe"
}

if (-not (Test-Path $backendDir)) {
    throw "Backend directory not found: $backendDir"
}

if (-not (Test-Path $frontendDir)) {
    throw "Frontend directory not found: $frontendDir"
}

$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue
if ($null -eq $dockerCmd) {
    throw 'docker command not found. Install Docker Desktop first.'
}

& $dockerCmd.Source info >$null 2>&1
if ($LASTEXITCODE -ne 0) {
    throw 'Docker engine is not running. Start Docker Desktop and retry.'
}

Write-Section 'Infrastructure startup'
& $dockerCmd.Source compose -f (Join-Path $root 'docker-compose.yml') up -d mysql minio | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Failed to start MySQL/MinIO via docker compose.'
}

Write-Host 'Waiting for MinIO on 127.0.0.1:19000 ...'
Wait-ForPort -Port 19000 -TimeoutSeconds 60 -Name 'MinIO'
Write-Host 'Waiting for MySQL on 127.0.0.1:3307 ...'
Wait-ForPort -Port 3307 -TimeoutSeconds 60 -Name 'MySQL'
Write-Host 'MySQL is ready on 127.0.0.1:3307'
Write-Host 'MinIO is ready on http://127.0.0.1:19000 (console: http://127.0.0.1:19001)'

$npmCmd = Get-Command npm -ErrorAction SilentlyContinue
if ($null -eq $npmCmd) {
    throw 'npm command not found. Install Node.js first.'
}

Write-Section 'Frontend dependency check'
if (-not (Test-Path $frontendNodeModules)) {
    if (-not (Test-Path $frontendPackageLock)) {
        throw "package-lock.json not found: $frontendPackageLock"
    }

    Write-Host 'node_modules not found, running npm ci...'
    $installProcess = Start-Process -FilePath $npmCmd.Source -ArgumentList @('ci') -WorkingDirectory $frontendDir -PassThru -NoNewWindow -Wait
    if ($installProcess.ExitCode -ne 0) {
        throw 'npm ci failed. Check network access and package-lock.json.'
    }
} else {
    Write-Host 'node_modules exists, skipping npm ci.'
}

Write-Section 'Starting backend'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:EDURAG_STORAGE_BACKEND = 'minio'
$env:EDURAG_MINIO_ENDPOINT = '127.0.0.1:19000'
$env:EDURAG_MINIO_ACCESS_KEY = 'minioadmin'
$env:EDURAG_MINIO_SECRET_KEY = 'minioadmin'
$env:EDURAG_MINIO_BUCKET = 'edurag-knowledge'
$env:EDURAG_MINIO_SECURE = 'false'
$env:EDURAG_MYSQL_HOST = '127.0.0.1'
$env:EDURAG_MYSQL_PORT = '3307'
$env:EDURAG_MYSQL_USER = 'root'
$env:EDURAG_MYSQL_PASSWORD = '1234'
$env:EDURAG_MYSQL_DATABASE = 'subjects_kg'
$startedBackend = $false
if (Test-PortOpen -Port $preferredBackendPort) {
    $health = Test-HttpUrl -Url "http://127.0.0.1:$preferredBackendPort/api/health"
    if ($health.Ok -and $health.Data.status -eq 'ok') {
        Write-Host 'Backend port 8000 already has a healthy EduRAG service, reusing it.'
        $backendPort = $preferredBackendPort
    } else {
        Write-Host 'Port 8000 is occupied by a non-EduRAG service. Falling back to 8001 for this launch.'
        if (Test-PortOpen -Port $fallbackBackendPort) {
            $fallbackHealth = Test-HttpUrl -Url "http://127.0.0.1:$fallbackBackendPort/api/health"
            if ($fallbackHealth.Ok -and $fallbackHealth.Data.status -eq 'ok') {
                Write-Host 'Backend port 8001 already has a healthy EduRAG service, reusing it.'
                $backendPort = $fallbackBackendPort
            } else {
                throw 'Both 8000 and 8001 are occupied, and 8001 is not a healthy EduRAG backend. Stop the conflicting process or free 8001, then retry.'
            }
        } else {
            $backendPort = $fallbackBackendPort
            $backendProcess = Start-LoggedProcess -FilePath $pythonExe -Arguments @('-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', "$backendPort") -WorkingDirectory $backendDir -LogFile $backendLog
            Write-Host "Backend PID: $($backendProcess.Id)"
            Wait-ForHttp -Url "http://127.0.0.1:$backendPort/api/health" -TimeoutSeconds 180 -Name 'Backend'
            $startedBackend = $true
        }
    }
} else {
    $backendPort = $preferredBackendPort
    $backendProcess = Start-LoggedProcess -FilePath $pythonExe -Arguments @('-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', "$backendPort") -WorkingDirectory $backendDir -LogFile $backendLog
    Write-Host "Backend PID: $($backendProcess.Id)"
    Wait-ForHttp -Url "http://127.0.0.1:$backendPort/api/health" -TimeoutSeconds 180 -Name 'Backend'
    $startedBackend = $true
}

$backendUrl = "http://127.0.0.1:$backendPort/docs"

Write-Host "Backend is using port: $backendPort"

Write-Section 'Starting frontend'
$startedFrontend = $false
$frontendPort = Get-FreePort -Candidates @($preferredFrontendPort, $fallbackFrontendPort, 5175) -Name 'frontend'
$env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$backendPort"
$frontendProcess = Start-LoggedProcess -FilePath $npmCmd.Source -Arguments @('run', 'dev', '--', '--host', '127.0.0.1', '--port', "$frontendPort") -WorkingDirectory $frontendDir -LogFile $frontendLog
Write-Host "Frontend PID: $($frontendProcess.Id)"
$startedFrontend = $true

Write-Section 'Waiting for frontend'
Wait-ForPort -Port $frontendPort -TimeoutSeconds 180 -Name 'Frontend'

$frontendUrl = "http://127.0.0.1:$frontendPort/"

Write-Host "Frontend is ready: $frontendUrl"
Write-Host "Opening browser to $frontendUrl"
Start-Process $frontendUrl

Write-Host ''
Write-Host "Backend docs: $backendUrl"
if ($startedBackend) {
    Write-Host "Backend stdout log: $backendOutLog"
    Write-Host "Backend stderr log: $backendErrLog"
}
if ($startedFrontend) {
    Write-Host "Frontend stdout log: $frontendOutLog"
    Write-Host "Frontend stderr log: $frontendErrLog"
}
Write-Host ''
Write-Host 'Launcher finished. Keep the background processes running to use the app.'
