param(
    [switch]$PersistUser,
    [string]$SourceVar = 'DASHSCOPE_API_KEY',
    [string]$TargetVar = 'EDURAG_DASHSCOPE_API_KEY'
)

$ErrorActionPreference = 'Stop'

function Test-DemoLikeKey {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $true
    }

    $v = $Value.Trim().ToLowerInvariant()
    return $v.StartsWith('demo-key') -or $v.Contains('change-me')
}

$existingTarget = [Environment]::GetEnvironmentVariable($TargetVar, 'User')
$processTarget = (Get-Item -Path "Env:$TargetVar" -ErrorAction SilentlyContinue).Value
if (-not [string]::IsNullOrWhiteSpace($processTarget)) {
    $existingTarget = $processTarget
}

$candidate = $null
if (-not (Test-DemoLikeKey -Value $existingTarget)) {
    $candidate = $existingTarget
} else {
    $sourceValue = [Environment]::GetEnvironmentVariable($SourceVar, 'User')
    if ([string]::IsNullOrWhiteSpace($sourceValue)) {
        $sourceValue = (Get-Item -Path "Env:$SourceVar" -ErrorAction SilentlyContinue).Value
    }
    if (-not (Test-DemoLikeKey -Value $sourceValue)) {
        $candidate = $sourceValue
    }
}

if ([string]::IsNullOrWhiteSpace($candidate)) {
    throw "No usable API key found. Set user env '$SourceVar' or '$TargetVar' with a non-demo key."
}

Set-Item -Path "Env:$TargetVar" -Value $candidate

if ($PersistUser) {
    [Environment]::SetEnvironmentVariable($TargetVar, $candidate, 'User')
}

$len = $candidate.Length
$prefixLen = [Math]::Min(6, $len)
$prefix = $candidate.Substring(0, $prefixLen)

Write-Host "Set in current process: $TargetVar (len=$len, prefix=$prefix*** )"
if ($PersistUser) {
    Write-Host "Persisted to user-level env var: $TargetVar"
} else {
    Write-Host "Process-only set. Add -PersistUser to persist."
}
