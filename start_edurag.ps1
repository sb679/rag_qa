$ErrorActionPreference = 'Stop'

$PrimaryEnvPrefix = 'MINING_QA_'
$LegacyEnvPrefix = 'EDURAG_'

function Get-CompatEnvironmentNames {
    param([Parameter(Mandatory = $true)][string]$Name)

    if ($Name.StartsWith($PrimaryEnvPrefix)) {
        $suffix = $Name.Substring($PrimaryEnvPrefix.Length)
        return @($Name, "$LegacyEnvPrefix$suffix")
    }

    if ($Name.StartsWith($LegacyEnvPrefix)) {
        $suffix = $Name.Substring($LegacyEnvPrefix.Length)
        return @("$PrimaryEnvPrefix$suffix", $Name)
    }

    return @($Name)
}

function Get-CompatEnvironmentValue {
    param([Parameter(Mandatory = $true)][string]$Name)

    foreach ($candidate in Get-CompatEnvironmentNames -Name $Name) {
        $processValue = [Environment]::GetEnvironmentVariable($candidate, 'Process')
        if (-not [string]::IsNullOrWhiteSpace($processValue)) {
            return $processValue
        }

        $userValue = [Environment]::GetEnvironmentVariable($candidate, 'User')
        if (-not [string]::IsNullOrWhiteSpace($userValue)) {
            return $userValue
        }

        $machineValue = [Environment]::GetEnvironmentVariable($candidate, 'Machine')
        if (-not [string]::IsNullOrWhiteSpace($machineValue)) {
            return $machineValue
        }
    }

    return $null
}

function Test-CompatEnvironmentValue {
    param([Parameter(Mandatory = $true)][string]$Name)

    return -not [string]::IsNullOrWhiteSpace((Get-CompatEnvironmentValue -Name $Name))
}

function Set-CompatEnvironmentValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value
    )

    foreach ($candidate in Get-CompatEnvironmentNames -Name $Name) {
        [Environment]::SetEnvironmentVariable($candidate, $Value, 'Process')
    }
}

function Get-IntEnvironmentValue {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][int]$DefaultValue
    )

    $rawValue = Get-CompatEnvironmentValue -Name $Name
    if ([string]::IsNullOrWhiteSpace($rawValue)) {
        return $DefaultValue
    }

    $parsedValue = 0
    if (-not [int]::TryParse($rawValue, [ref]$parsedValue)) {
        throw "Environment variable $Name must be an integer, got: $rawValue"
    }

    return $parsedValue
}

function New-PortCandidateList {
    param(
        [Parameter(Mandatory = $true)][int]$PreferredPort,
        [int[]]$FallbackPorts = @(),
        [Parameter(Mandatory = $true)][int]$RandomMin,
        [Parameter(Mandatory = $true)][int]$RandomMax,
        [int]$RandomCount = 8
    )

    $seen = New-Object 'System.Collections.Generic.HashSet[int]'
    $candidates = New-Object 'System.Collections.Generic.List[int]'
    foreach ($port in @($PreferredPort) + $FallbackPorts) {
        if ($port -gt 0 -and $seen.Add($port)) {
            $candidates.Add($port) | Out-Null
        }
    }

    $targetCount = $candidates.Count + [Math]::Max($RandomCount, 0)
    $maxAttempts = [Math]::Max($RandomCount * 12, 24)
    $attempts = 0
    while ($candidates.Count -lt $targetCount -and $attempts -lt $maxAttempts) {
        $candidate = Get-Random -Minimum $RandomMin -Maximum ($RandomMax + 1)
        if ($seen.Add($candidate)) {
            $candidates.Add($candidate) | Out-Null
        }
        $attempts++
    }

    return $candidates.ToArray()
}

$root = $PSScriptRoot
$ragQaRoot = Join-Path $root 'rag_qa'

# Load workspace .env into the current process environment so flags like
# MINING_QA_MILVUS_EXTERNAL_PORT or EDURAG_MILVUS_EXTERNAL_PORT defined there
# are visible to this launcher.
$dotEnvFile = Join-Path $root '.env'
if (Test-Path $dotEnvFile) {
    foreach ($line in Get-Content -Path $dotEnvFile -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        $eq = $trimmed.IndexOf('=')
        if ($eq -lt 1) { continue }
        $key = $trimmed.Substring(0, $eq).Trim()
        $val = $trimmed.Substring($eq + 1).Trim()
        if ($val.Length -ge 2 -and (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'")))) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        if ($key.StartsWith($PrimaryEnvPrefix) -or $key.StartsWith($LegacyEnvPrefix)) {
            if (-not (Test-CompatEnvironmentValue -Name $key)) {
                Set-CompatEnvironmentValue -Name $key -Value $val
            }
        } elseif (-not [Environment]::GetEnvironmentVariable($key)) {
            [Environment]::SetEnvironmentVariable($key, $val, 'Process')
        }
    }
}

$pythonExe = Get-CompatEnvironmentValue -Name 'EDURAG_PYTHON_EXE'
if ([string]::IsNullOrWhiteSpace($pythonExe)) {
    $pythonExe = Join-Path $ragQaRoot '.venv\Scripts\python.exe'
}
$backendDir = Join-Path $ragQaRoot 'web\backend'
$frontendDir = Join-Path $ragQaRoot 'web\frontend'
$frontendNodeModules = Join-Path $frontendDir 'node_modules'
$frontendPackageLock = Join-Path $frontendDir 'package-lock.json'
$launcherLogDir = Join-Path $ragQaRoot 'logs\launcher'
$launchId = [guid]::NewGuid().ToString('N').Substring(0, 8)
$backendLog = Join-Path $launcherLogDir "backend-$launchId.log"
$frontendLog = Join-Path $launcherLogDir "frontend-$launchId.log"
$launcherSessionLog = Join-Path $launcherLogDir "launcher-$launchId.log"
$launcherLatestLog = Join-Path $launcherLogDir 'launcher-latest.log'
$backendOutLog = "$backendLog.out"
$backendErrLog = "$backendLog.err"
$frontendOutLog = "$frontendLog.out"
$frontendErrLog = "$frontendLog.err"
$managedBrowserProfileDir = Join-Path $launcherLogDir "browser-profile-$launchId"
$launcherBackendTimeoutSeconds = 55
$launcherFrontendTimeoutSeconds = 55
$launcherBackendReload = $false
$preferredBackendPort = Get-IntEnvironmentValue -Name 'EDURAG_BACKEND_HOST_PORT' -DefaultValue 8000
$preferredFrontendPort = Get-IntEnvironmentValue -Name 'EDURAG_FRONTEND_HOST_PORT' -DefaultValue 5173
$preferredMinioApiHostPort = Get-IntEnvironmentValue -Name 'EDURAG_MINIO_API_HOST_PORT' -DefaultValue 19000
$preferredMinioConsoleHostPort = Get-IntEnvironmentValue -Name 'EDURAG_MINIO_CONSOLE_HOST_PORT' -DefaultValue 19001
$preferredMilvusHostPort = Get-IntEnvironmentValue -Name 'EDURAG_MILVUS_HOST_PORT' -DefaultValue 19530
$backendCandidates = New-PortCandidateList -PreferredPort $preferredBackendPort -FallbackPorts @(8001, 8002, 8003) -RandomMin 18000 -RandomMax 18999 -RandomCount 10
$frontendCandidates = New-PortCandidateList -PreferredPort $preferredFrontendPort -FallbackPorts @(5174, 5175, 5176, 5177, 5178, 5179, 5180, 5181, 5182, 5183, 5184, 5185) -RandomMin 24000 -RandomMax 24999 -RandomCount 10
$minioApiHostPortCandidates = New-PortCandidateList -PreferredPort $preferredMinioApiHostPort -RandomMin 29000 -RandomMax 29149 -RandomCount 12
$minioConsoleHostPortCandidates = New-PortCandidateList -PreferredPort $preferredMinioConsoleHostPort -RandomMin 29150 -RandomMax 29299 -RandomCount 12
$milvusHostPortCandidates = New-PortCandidateList -PreferredPort $preferredMilvusHostPort -RandomMin 29530 -RandomMax 29699 -RandomCount 12
$backendPort = $preferredBackendPort
$frontendPort = $preferredFrontendPort
$frontendUrl = "http://127.0.0.1:$frontendPort/"
$backendUrl = "http://127.0.0.1:$backendPort/docs"
$minioApiHostPort = $preferredMinioApiHostPort
$minioConsoleHostPort = $preferredMinioConsoleHostPort
$milvusHostPort = $preferredMilvusHostPort

function Write-LauncherLog {
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [ValidateSet('INFO', 'WARN', 'ERROR')][string]$Level = 'INFO'
    )

    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $line = "[$timestamp] [$Level] $Message"
    Write-Host $Message
    Write-LogFileEntry -Path $launcherSessionLog -Value $line
    Write-LogFileEntry -Path $launcherLatestLog -Value $line
}

function Write-Section {
    param([string]$Title)
    Write-Host ''
    Write-Host "=== $Title ==="
    Write-LogFileEntry -Path $launcherSessionLog -Value ''
    Write-LogFileEntry -Path $launcherSessionLog -Value "=== $Title ==="
    Write-LogFileEntry -Path $launcherLatestLog -Value ''
    Write-LogFileEntry -Path $launcherLatestLog -Value "=== $Title ==="
}

function Write-LogFileEntry {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][AllowEmptyString()][string]$Value
    )

    $maxAttempts = 6
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            $fileStream = [System.IO.File]::Open($Path, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::ReadWrite)
            try {
                $writer = New-Object System.IO.StreamWriter($fileStream, [System.Text.UTF8Encoding]::new($false))
                try {
                    $writer.WriteLine($Value)
                } finally {
                    $writer.Dispose()
                }
            } finally {
                $fileStream.Dispose()
            }

            return
        } catch {
            if ($attempt -eq $maxAttempts) {
                throw
            }

            [System.Threading.Thread]::Sleep(75)
        }
    }
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

function Resolve-FreeCandidatePort {
    param(
        [Parameter(Mandatory = $true)][int[]]$Candidates,
        [Parameter(Mandatory = $true)][string]$Name
    )

    foreach ($candidate in $Candidates) {
        $procInfo = Get-ListeningProcessInfo -Port $candidate
        if ($null -eq $procInfo) {
            Write-LauncherLog -Message "$Name candidate port $candidate is free."
            return $candidate
        }

        $owner = if ($procInfo.Name) { "$($procInfo.Name) (PID $($procInfo.PID))" } else { "PID $($procInfo.PID)" }
        Write-LauncherLog -Message "$Name candidate port $candidate is occupied by $owner, trying next port." -Level 'WARN'
    }

    throw "No free candidate port found for $Name. Tried: $($Candidates -join ', ')."
}

function Get-ListeningProcessInfo {
    param([Parameter(Mandatory = $true)][int]$Port)

    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $connection) {
        return $null
    }

    $processId = [int]$connection.OwningProcess
    $proc = Get-Process -Id $processId -ErrorAction SilentlyContinue
    $commandLine = ''
    try {
        $cimProc = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        if ($cimProc) {
            $commandLine = [string]$cimProc.CommandLine
        }
    } catch {
        $commandLine = ''
    }

    return [PSCustomObject]@{
        Port = $Port
        PID = $processId
        Name = if ($proc) { $proc.ProcessName } else { '' }
        Path = if ($proc) { $proc.Path } else { '' }
        CommandLine = $commandLine
    }
}

function Test-RepoFrontendProcess {
    param($ProcessInfo)

    if ($null -eq $ProcessInfo) {
        return $false
    }

    $commandLine = [string]$ProcessInfo.CommandLine
    return $commandLine -match 'vite' -and $commandLine -like "*$frontendDir*"
}

function Test-RepoBackendProcess {
    param($ProcessInfo)

    if ($null -eq $ProcessInfo) {
        return $false
    }

    $commandLine = [string]$ProcessInfo.CommandLine
    return $commandLine -match 'uvicorn' -and $commandLine -like "*$backendDir*"
}

function Stop-ProcessIfOwnedByRepo {
    param(
        [Parameter(Mandatory = $true)]$ProcessInfo,
        [Parameter(Mandatory = $true)][ValidateSet('frontend', 'backend')][string]$Kind
    )

    if ($Kind -eq 'frontend' -and -not (Test-RepoFrontendProcess -ProcessInfo $ProcessInfo)) {
        return $false
    }
    if ($Kind -eq 'backend' -and -not (Test-RepoBackendProcess -ProcessInfo $ProcessInfo)) {
        return $false
    }

    try {
        Stop-Process -Id $ProcessInfo.PID -Force -ErrorAction Stop
        Write-Host "Stopped lingering repo $Kind process PID=$($ProcessInfo.PID) on port $($ProcessInfo.Port)."
        return $true
    } catch {
        Write-Host "Failed to stop lingering repo $Kind process PID=$($ProcessInfo.PID) on port $($ProcessInfo.Port): $($_.Exception.Message)"
        return $false
    }
}

function Resolve-FrontendPort {
    param([Parameter(Mandatory = $true)][int[]]$Candidates)

    foreach ($candidate in $Candidates) {
        $procInfo = Get-ListeningProcessInfo -Port $candidate
        if ($null -eq $procInfo) {
            return $candidate
        }

        if (Test-RepoFrontendProcess -ProcessInfo $procInfo) {
            Write-Host "Frontend port $candidate already has this repo's Vite service. Stopping it so the latest frontend is always started fresh."
            Stop-ProcessIfOwnedByRepo -ProcessInfo $procInfo -Kind 'frontend' | Out-Null
            return $candidate
        }

        if (-not (Test-PortOpen -Port $candidate)) {
            return $candidate
        }

        Write-Host "Frontend candidate port $candidate is occupied by another service, trying next port."
    }

    return (Get-FreePort -Candidates $Candidates -Name 'frontend')
}

function Resolve-BackendPort {
    param([Parameter(Mandatory = $true)][int[]]$Candidates)

    foreach ($candidate in $Candidates) {
        Write-LauncherLog -Message "Probing backend candidate port: $candidate"
        if (-not (Test-PortOpen -Port $candidate)) {
            Write-LauncherLog -Message "Backend candidate port $candidate is free."
            return [PSCustomObject]@{ Port = $candidate; Reuse = $false }
        }

        $procInfo = Get-ListeningProcessInfo -Port $candidate
        if (Test-RepoBackendProcess -ProcessInfo $procInfo) {
            Write-LauncherLog -Message "Backend port $candidate already has this repo's backend. Stopping it so the latest backend is always started fresh."
            Stop-ProcessIfOwnedByRepo -ProcessInfo $procInfo -Kind 'backend' | Out-Null
            return [PSCustomObject]@{ Port = $candidate; Reuse = $false }
        }

        Write-LauncherLog -Message "Backend candidate port $candidate is occupied. Checking health endpoint."
        $health = Test-HttpUrl -Url "http://127.0.0.1:$candidate/api/health"
        if ($health.Ok -and $health.Data.status -eq 'ok') {
            Write-LauncherLog -Message "Backend port $candidate is occupied by another healthy service, trying next backend candidate."
            continue
        }

        if ($null -ne $procInfo) {
            Write-LauncherLog -Message "Backend port $candidate is occupied by another service, trying next backend candidate."
            continue
        }
    }

    throw "No usable backend port found. Tried: $($Candidates -join ', ')."
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

function Get-RecentLogLines {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [int]$Tail = 40
    )

    if (-not (Test-Path $Path)) {
        return @("<log file not created yet>")
    }

    $lines = Get-Content -Path $Path -Tail $Tail -ErrorAction SilentlyContinue
    if (-not $lines) {
        return @("<log file is empty>")
    }

    return $lines
}

function Write-RecentProcessLogs {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$StdoutPath,
        [Parameter(Mandatory = $true)][string]$StderrPath
    )

    Write-LauncherLog -Level 'WARN' -Message "$Name recent stdout:"
    Get-RecentLogLines -Path $StdoutPath | ForEach-Object {
        Write-Host $_
        Write-LogFileEntry -Path $launcherSessionLog -Value $_
    }

    Write-LauncherLog -Level 'WARN' -Message "$Name recent stderr:"
    Get-RecentLogLines -Path $StderrPath | ForEach-Object {
        Write-Host $_
        Write-LogFileEntry -Path $launcherSessionLog -Value $_
    }
}

function Get-ManagedBrowserExecutable {
    $envOverride = Get-CompatEnvironmentValue -Name 'EDURAG_BROWSER_EXE'
    if ($envOverride -and (Test-Path $envOverride)) {
        return $envOverride
    }

    $candidates = @(
        'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
        'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
        'C:\Program Files\Google\Chrome\Application\chrome.exe',
        'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        'C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe',
        'C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe'
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    foreach ($commandName in @('msedge', 'chrome', 'brave')) {
        $cmd = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($cmd) {
            return $cmd.Source
        }
    }

    return $null
}

function Open-ManagedBrowser {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$ProfileDir
    )

    $browserExe = Get-ManagedBrowserExecutable
    if ($null -eq $browserExe) {
        Start-Process $Url | Out-Null
        return $null
    }

    New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null
    $arguments = @(
        '--new-window',
        '--no-first-run',
        '--disable-background-mode',
        '--disable-sync',
        '--disable-session-crashed-bubble',
        "--user-data-dir=$ProfileDir",
        $Url
    )
    return Start-Process -FilePath $browserExe -ArgumentList $arguments -PassThru
}

function Stop-RepoServiceOnPort {
    param(
        [Parameter(Mandatory = $true)][int]$Port,
        [Parameter(Mandatory = $true)][ValidateSet('frontend', 'backend')][string]$Kind
    )

    $procInfo = Get-ListeningProcessInfo -Port $Port
    if ($null -eq $procInfo) {
        return
    }

    Stop-ProcessIfOwnedByRepo -ProcessInfo $procInfo -Kind $Kind | Out-Null
}

function Stop-LauncherInfrastructure {
    Write-Host 'Stopping repo frontend/backend processes...'
    Stop-RepoServiceOnPort -Port $frontendPort -Kind 'frontend'
    Stop-RepoServiceOnPort -Port $backendPort -Kind 'backend'

    Write-Host 'Stopping project Docker services...'
    & $dockerCmd.Source compose -f (Join-Path $root 'docker-compose.yml') down | Out-Null
    if (Test-Path (Join-Path $root 'docker-compose.monitoring.yml')) {
        & $dockerCmd.Source compose -f (Join-Path $root 'docker-compose.monitoring.yml') down | Out-Null
    }
    if (Test-Path (Join-Path $root 'docker-compose.prod.yml')) {
        & $dockerCmd.Source compose -f (Join-Path $root 'docker-compose.prod.yml') down | Out-Null
    }
}

if (-not (Test-Path $launcherLogDir)) {
    New-Item -ItemType Directory -Path $launcherLogDir -Force | Out-Null
}
if (Test-Path $launcherSessionLog) {
    Remove-Item $launcherSessionLog -Force
}
if (Test-Path $launcherLatestLog) {
    Remove-Item $launcherLatestLog -Force
}
New-Item -ItemType File -Path $launcherSessionLog -Force | Out-Null
New-Item -ItemType File -Path $launcherLatestLog -Force | Out-Null

try {
    Write-Section 'EduRAG launcher'
    Write-LauncherLog -Message "Workspace root: $root"
    Write-LauncherLog -Message "Launcher session log: $launcherSessionLog"

    Write-Section 'Environment bootstrap'
    $envSetupScript = Join-Path $root 'scripts\setup_edurag_env.ps1'
    if (-not (Test-Path $envSetupScript)) {
        throw "Environment setup script not found: $envSetupScript"
    }
    & $envSetupScript -PersistUser

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

    Write-Section 'Pre-launch orphan cleanup'
    # 杀掉以前 launcher 留下的、与本仓库相关的 backend/frontend 进程，避免
    # "新代码起在新端口、旧进程占着旧端口、前端代理到旧进程" 的鬼影问题。
    try {
        $rootPattern = [Regex]::Escape($root)
        $orphans = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='node.exe'" -ErrorAction SilentlyContinue |
            Where-Object {
                $_.CommandLine -and (
                    ($_.CommandLine -match 'uvicorn' -and $_.CommandLine -match 'main:app') -or
                    ($_.CommandLine -match $rootPattern -and ($_.CommandLine -match 'vite' -or $_.CommandLine -match 'rag_qa\\web'))
                )
            }
        if ($orphans) {
            foreach ($p in $orphans) {
                try {
                    Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop
                    Write-Host ("  killed orphan PID={0} ({1})" -f $p.ProcessId, $p.Name)
                } catch {
                    Write-Warning ("  failed to kill orphan PID={0}: {1}" -f $p.ProcessId, $_.Exception.Message)
                }
            }
            Start-Sleep -Seconds 1
        } else {
            Write-Host '  no orphan backend/frontend processes detected'
        }
    } catch {
        Write-Warning ("Orphan cleanup skipped: {0}" -f $_.Exception.Message)
    }

    Write-Section 'Infrastructure startup'
    $minioApiHostPort = Resolve-FreeCandidatePort -Candidates $minioApiHostPortCandidates -Name 'MinIO API host'
    $minioConsoleHostPort = Resolve-FreeCandidatePort -Candidates $minioConsoleHostPortCandidates -Name 'MinIO console host'
    Set-CompatEnvironmentValue -Name 'EDURAG_MINIO_API_HOST_PORT' -Value "$minioApiHostPort"
    Set-CompatEnvironmentValue -Name 'EDURAG_MINIO_CONSOLE_HOST_PORT' -Value "$minioConsoleHostPort"

    $externalMilvusPortRaw = Get-CompatEnvironmentValue -Name 'EDURAG_MILVUS_EXTERNAL_PORT'
    $useExternalMilvus = $false
    if ($externalMilvusPortRaw) {
        try {
            $externalMilvusPort = [int]$externalMilvusPortRaw
            if ($externalMilvusPort -gt 0) {
                $useExternalMilvus = $true
                $milvusHostPort = $externalMilvusPort
                Set-CompatEnvironmentValue -Name 'EDURAG_MILVUS_HOST_PORT' -Value "$milvusHostPort"
                Write-LauncherLog -Message "Detected MINING_QA_MILVUS_EXTERNAL_PORT/EDURAG_MILVUS_EXTERNAL_PORT=$milvusHostPort. Will reuse the external Milvus on 127.0.0.1:$milvusHostPort and skip docker compose for milvus/etcd."
                if (-not (Test-PortOpen -Port $milvusHostPort)) {
                    throw "MINING_QA_MILVUS_EXTERNAL_PORT/EDURAG_MILVUS_EXTERNAL_PORT=$milvusHostPort is set, but no service is listening on 127.0.0.1:$milvusHostPort. Start the external Milvus first (e.g. 'docker start milvus-standalone') or unset the external Milvus env var in .env to let docker-compose manage Milvus."
                }
            }
        } catch [System.Management.Automation.RuntimeException] {
            throw
        } catch {
            Write-LauncherLog -Level 'WARN' -Message "Invalid MINING_QA_MILVUS_EXTERNAL_PORT/EDURAG_MILVUS_EXTERNAL_PORT='$externalMilvusPortRaw', falling back to compose-managed Milvus."
        }
    }

    if (-not $useExternalMilvus) {
        $milvusHostPort = Resolve-FreeCandidatePort -Candidates $milvusHostPortCandidates -Name 'Milvus host'
        Set-CompatEnvironmentValue -Name 'EDURAG_MILVUS_HOST_PORT' -Value "$milvusHostPort"
        Write-LauncherLog -Message "MinIO API host port candidates: $($minioApiHostPortCandidates -join ', ')"
        Write-LauncherLog -Message "MinIO console host port candidates: $($minioConsoleHostPortCandidates -join ', ')"
        Write-LauncherLog -Message "Milvus host port candidates: $($milvusHostPortCandidates -join ', ')"
        Write-LauncherLog -Message "Selected infrastructure ports: minio_api=$minioApiHostPort minio_console=$minioConsoleHostPort milvus=$milvusHostPort"
        & $dockerCmd.Source compose -f (Join-Path $root 'docker-compose.yml') up -d minio etcd milvus | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to start MinIO/etcd/Milvus via docker compose.'
        }
    } else {
        Write-LauncherLog -Message "Selected infrastructure ports: minio_api=$minioApiHostPort minio_console=$minioConsoleHostPort milvus=$milvusHostPort (external)"
        & $dockerCmd.Source compose -f (Join-Path $root 'docker-compose.yml') up -d minio | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw 'Failed to start MinIO via docker compose.'
        }
    }

    Write-LauncherLog -Message "Waiting for MinIO on 127.0.0.1:$minioApiHostPort ..."
    Wait-ForPort -Port $minioApiHostPort -TimeoutSeconds 60 -Name 'MinIO'
    Write-LauncherLog -Message "Waiting for Milvus on 127.0.0.1:$milvusHostPort ..."
    Wait-ForPort -Port $milvusHostPort -TimeoutSeconds 120 -Name 'Milvus'
    Write-LauncherLog -Message "MinIO is ready on http://127.0.0.1:$minioApiHostPort (console: http://127.0.0.1:$minioConsoleHostPort)"
    Write-LauncherLog -Message "Milvus is ready on 127.0.0.1:$milvusHostPort"

    $npmCmd = Get-Command npm -ErrorAction SilentlyContinue
    if ($null -eq $npmCmd) {
        throw 'npm command not found. Install Node.js first.'
    }

    Write-Section 'Frontend dependency check'
    if (-not (Test-Path $frontendNodeModules)) {
        if (-not (Test-Path $frontendPackageLock)) {
            throw "package-lock.json not found: $frontendPackageLock"
        }

        Write-LauncherLog -Message 'node_modules not found, running npm ci...'
        $installProcess = Start-Process -FilePath $npmCmd.Source -ArgumentList @('ci') -WorkingDirectory $frontendDir -PassThru -NoNewWindow -Wait
        if ($installProcess.ExitCode -ne 0) {
            throw 'npm ci failed. Check network access and package-lock.json.'
        }
    } else {
        Write-LauncherLog -Message 'node_modules exists, skipping npm ci.'
    }

    Write-Section 'Starting backend'
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:EDURAG_DEV_FAST_STARTUP = '1'
    Set-CompatEnvironmentValue -Name 'EDURAG_STORAGE_BACKEND' -Value 'minio'
    Set-CompatEnvironmentValue -Name 'EDURAG_MINIO_ENDPOINT' -Value "127.0.0.1:$minioApiHostPort"
    $minioRootUser = Get-CompatEnvironmentValue -Name 'EDURAG_MINIO_ROOT_USER'
    if ([string]::IsNullOrWhiteSpace($minioRootUser)) {
        $minioRootUser = 'demo-minio-user'
    }
    $minioRootPassword = Get-CompatEnvironmentValue -Name 'EDURAG_MINIO_ROOT_PASSWORD'
    if ([string]::IsNullOrWhiteSpace($minioRootPassword)) {
        $minioRootPassword = 'demo-minio-password-change-me'
    }
    Set-CompatEnvironmentValue -Name 'EDURAG_MINIO_ACCESS_KEY' -Value $minioRootUser
    Set-CompatEnvironmentValue -Name 'EDURAG_MINIO_SECRET_KEY' -Value $minioRootPassword
    Set-CompatEnvironmentValue -Name 'EDURAG_MINIO_BUCKET' -Value 'edurag-knowledge'
    Set-CompatEnvironmentValue -Name 'EDURAG_MINIO_SECURE' -Value 'false'
    Set-CompatEnvironmentValue -Name 'EDURAG_MILVUS_HOST' -Value '127.0.0.1'
    Set-CompatEnvironmentValue -Name 'EDURAG_MILVUS_PORT' -Value "$milvusHostPort"
    $startedBackend = $false
    $backendDecision = Resolve-BackendPort -Candidates $backendCandidates
    $backendPort = [int]$backendDecision.Port
    if (-not $backendDecision.Reuse) {
        $backendArgs = @('-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', "$backendPort")
        if ($launcherBackendReload) {
            $backendArgs += @(
                '--reload',
                '--reload-dir', (Join-Path $workspaceRoot 'rag_qa\web\backend'),
                '--reload-dir', (Join-Path $workspaceRoot 'rag_qa\core'),
                '--reload-dir', (Join-Path $workspaceRoot 'rag_qa\base')
            )
        }

        $backendProcess = Start-LoggedProcess -FilePath $pythonExe -Arguments $backendArgs -WorkingDirectory $backendDir -LogFile $backendLog
        Write-LauncherLog -Message "Backend PID: $($backendProcess.Id)"
        try {
            Wait-ForHttp -Url "http://127.0.0.1:$backendPort/api/health" -TimeoutSeconds $launcherBackendTimeoutSeconds -Name 'Backend'
        } catch {
            Write-RecentProcessLogs -Name 'Backend' -StdoutPath $backendOutLog -StderrPath $backendErrLog
            throw
        }
        $startedBackend = $true
    }

    $backendUrl = "http://127.0.0.1:$backendPort/docs"
    Set-CompatEnvironmentValue -Name 'EDURAG_BACKEND_HOST_PORT' -Value "$backendPort"

    Write-LauncherLog -Message "Backend is using port: $backendPort"

    Write-Section 'Starting frontend'
    $startedFrontend = $false
    $frontendPort = Resolve-FrontendPort -Candidates $frontendCandidates
    Set-CompatEnvironmentValue -Name 'EDURAG_FRONTEND_HOST_PORT' -Value "$frontendPort"
    $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$backendPort"
    if (-not (Test-PortOpen -Port $frontendPort)) {
        $frontendProcess = Start-LoggedProcess -FilePath $npmCmd.Source -Arguments @('run', 'dev', '--', '--host', '127.0.0.1', '--port', "$frontendPort") -WorkingDirectory $frontendDir -LogFile $frontendLog
        Write-LauncherLog -Message "Frontend PID: $($frontendProcess.Id)"
        $startedFrontend = $true
    } else {
        Write-LauncherLog -Message "Frontend is using port: $frontendPort"
    }

    Write-Section 'Waiting for frontend'
    try {
        Wait-ForPort -Port $frontendPort -TimeoutSeconds $launcherFrontendTimeoutSeconds -Name 'Frontend'
    } catch {
        Write-RecentProcessLogs -Name 'Frontend' -StdoutPath $frontendOutLog -StderrPath $frontendErrLog
        throw
    }

    $frontendUrl = "http://127.0.0.1:$frontendPort/"

    Write-LauncherLog -Message "Frontend is ready: $frontendUrl"
    Write-LauncherLog -Message 'Managed browser uses a temporary isolated profile with sync disabled to avoid pulling third-party extensions into the launcher window.'
    Write-LauncherLog -Message "Opening managed browser to $frontendUrl"
    $browserProcess = Open-ManagedBrowser -Url $frontendUrl -ProfileDir $managedBrowserProfileDir

    Write-Host ''
    Write-LauncherLog -Message "Backend docs: $backendUrl"
    if ($startedBackend) {
        Write-LauncherLog -Message "Backend stdout log: $backendOutLog"
        Write-LauncherLog -Message "Backend stderr log: $backendErrLog"
    }
    if ($startedFrontend) {
        Write-LauncherLog -Message "Frontend stdout log: $frontendOutLog"
        Write-LauncherLog -Message "Frontend stderr log: $frontendErrLog"
    }
    Write-Host ''
    if ($null -eq $browserProcess) {
        Write-LauncherLog -Level 'WARN' -Message 'Managed browser not found. Fell back to the system default browser; auto-stop on browser close is unavailable in this mode.'
        Write-LauncherLog -Message 'Launcher finished. Keep the background processes running to use the app.'
        return
    }

    Write-LauncherLog -Message 'Browser is managed by the launcher. Close that browser window to stop local frontend, backend, and project services automatically.'

    try {
        Wait-Process -Id $browserProcess.Id
    } finally {
        Write-Section 'Browser closed - stopping local services'
        Stop-LauncherInfrastructure
        if (Test-Path $managedBrowserProfileDir) {
            Remove-Item -Path $managedBrowserProfileDir -Recurse -Force -ErrorAction SilentlyContinue
        }
        Write-LauncherLog -Message 'Local services stopped.'
    }
} catch {
    Write-Section 'Launcher failed'
    Write-LauncherLog -Level 'ERROR' -Message $_.Exception.Message
    if ($backendOutLog -or $backendErrLog) {
        Write-LauncherLog -Message "Backend log files: $backendOutLog | $backendErrLog"
    }
    if ($frontendOutLog -or $frontendErrLog) {
        Write-LauncherLog -Message "Frontend log files: $frontendOutLog | $frontendErrLog"
    }
    Write-LauncherLog -Message "Launcher session log: $launcherSessionLog"
    Write-LauncherLog -Message "Launcher latest log: $launcherLatestLog"
    throw
}
