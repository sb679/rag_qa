$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host '=== Repo Self Check ==='
Write-Host "Workspace: $root"

Write-Host ''
Write-Host '[1/5] Ignore rules sanity'
$ignored = @('.env', 'rag_qa/config.ini', 'rag_qa/web/frontend/node_modules')
foreach ($path in $ignored) {
    $result = git check-ignore $path 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "OK ignored: $path"
    } else {
        Write-Warning "NOT ignored: $path"
    }
}

Write-Host ''
Write-Host '[2/5] Working tree state'
git status --short

Write-Host ''
Write-Host '[3/5] Optional gitleaks scan'
$gitleaks = Get-Command gitleaks -ErrorAction SilentlyContinue
if ($gitleaks) {
    gitleaks detect --source . --no-banner
} else {
    Write-Warning 'gitleaks not found, skip. Install: https://github.com/gitleaks/gitleaks'
}

Write-Host ''
Write-Host '[4/5] Docker Compose config check'
$compose = Get-Command docker -ErrorAction SilentlyContinue
if ($compose) {
    docker compose config | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'docker compose config: OK'
    } else {
        Write-Warning 'docker compose config: FAILED'
    }
} else {
    Write-Warning 'docker command not found, skip compose validation.'
}

Write-Host ''
Write-Host '[5/5] Python dependency file check'
if ((Test-Path 'rag_qa/requirements.txt' -PathType Leaf) -and (Test-Path 'rag_qa/requirements.lock.txt' -PathType Leaf)) {
    Write-Host 'requirements.txt + requirements.lock.txt: OK'
} else {
    Write-Warning 'requirements files missing.'
}

Write-Host ''
Write-Host 'Repo self-check completed.'
