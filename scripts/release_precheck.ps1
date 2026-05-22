$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$envScript = Join-Path $root '.vscode\check_env.ps1'
$repoScript = Join-Path $root 'scripts\repo_self_check.ps1'

$passItems = New-Object System.Collections.Generic.List[string]
$warnItems = New-Object System.Collections.Generic.List[string]
$manualItems = New-Object System.Collections.Generic.List[string]

Set-Location $root

Write-Host '=== Release Preflight Check ==='
Write-Host "Workspace: $root"

Write-Host ''
Write-Host '[1/4] Environment self-check'
if (-not (Test-Path $envScript -PathType Leaf)) {
    throw "Missing environment self-check script: $envScript"
}
& $envScript
if ($LASTEXITCODE -ne 0) {
    throw 'Environment self-check failed.'
}
$passItems.Add('Environment self-check passed via .vscode/check_env.ps1')

Write-Host ''
Write-Host '[2/4] Repository self-check'
if (-not (Test-Path $repoScript -PathType Leaf)) {
    throw "Missing repository self-check script: $repoScript"
}
& $repoScript
if ($LASTEXITCODE -ne 0) {
    throw 'Repository self-check failed.'
}
$passItems.Add('Repository self-check passed via scripts/repo_self_check.ps1')

if (-not (Get-Command gitleaks -ErrorAction SilentlyContinue)) {
    $warnItems.Add('gitleaks not installed locally; secret scan step was skipped by repo self-check')
}

Write-Host ''
Write-Host '[3/4] Release document presence check'
$requiredDocs = @(
    @{ Label = 'README.md'; Path = 'README.md' },
    @{ Label = 'TECHNICAL_DOCUMENTATION.md'; Path = 'TECHNICAL_DOCUMENTATION.md' },
    @{ Label = 'PROJECT_CHARTER_AND_SCOPE.md'; Path = 'PROJECT_CHARTER_AND_SCOPE.md' },
    @{ Label = 'MILESTONES_AND_ITERATION_TRACKER.md'; Path = 'MILESTONES_AND_ITERATION_TRACKER.md' },
    @{ Label = 'TECHNICAL_DECISION_RECORD.md'; Path = 'TECHNICAL_DECISION_RECORD.md' },
    @{ Label = 'DEVELOPMENT_TEST_RELEASE_BASELINE.md'; Path = 'DEVELOPMENT_TEST_RELEASE_BASELINE.md' },
    @{ Label = 'rag_qa/README.md'; Path = 'rag_qa/README.md' }
)

$missingDocs = @()
foreach ($doc in $requiredDocs) {
    $matches = @(Get-ChildItem -Path $doc.Path -File -ErrorAction SilentlyContinue)
    if ($matches.Count -gt 0) {
        Write-Host "OK document: $($doc.Label)"
    } else {
        Write-Warning "Missing document: $($doc.Label)"
        $missingDocs += $doc.Label
    }
}

if ($missingDocs.Count -gt 0) {
    throw ('Release document presence check failed: ' + ($missingDocs -join ', '))
}
$passItems.Add('Required governance, entry, and baseline documents are present')

Write-Host ''
Write-Host '[4/4] Key runtime file presence check'
$requiredFiles = @(
    '.vscode/tasks.json',
    'docker-compose.yml',
    'rag_qa/web/frontend/package-lock.json',
    'rag_qa/web/frontend/Dockerfile',
    'rag_qa/web/Dockerfile.backend',
    'rag_qa/requirements.txt',
    'rag_qa/requirements.lock.txt'
)

$missingFiles = @()
foreach ($file in $requiredFiles) {
    if (Test-Path $file -PathType Leaf) {
        Write-Host "OK file: $file"
    } else {
        Write-Warning "Missing file: $file"
        $missingFiles += $file
    }
}

if ($missingFiles.Count -gt 0) {
    throw ('Key runtime file check failed: ' + ($missingFiles -join ', '))
}

$passItems.Add('Key runtime files for Compose, frontend, backend, and dependency manifests are present')

$manualItems.Add('Confirm frontend page rendering in the browser')
$manualItems.Add('Confirm login flow or minimum entry path works for the intended demo account')
$manualItems.Add('Confirm the intended demo path has been run end-to-end once before presentation')
$manualItems.Add('If demo depends on retrieval or knowledge statistics, confirm Milvus is usable at runtime')
$manualItems.Add('If demo depends on file upload or object access, confirm MinIO is usable at runtime')

Write-Host ''
Write-Host '=== Summary ==='
Write-Host 'PASS:'
foreach ($item in $passItems) {
    Write-Host "- $item"
}

Write-Host ''
Write-Host 'WARN:'
if ($warnItems.Count -gt 0) {
    foreach ($item in $warnItems) {
        Write-Warning $item
    }
} else {
    Write-Host '- none'
}

Write-Host ''
Write-Host 'MANUAL:'
foreach ($item in $manualItems) {
    Write-Host "- $item"
}

Write-Host ''
Write-Host 'Release preflight check passed.'
exit 0