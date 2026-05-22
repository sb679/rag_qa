param(
    [switch]$PersistUser,
    [string]$SourceVar = 'DASHSCOPE_API_KEY',
    [string]$TargetVar = 'MINING_QA_DASHSCOPE_API_KEY'
)

$ErrorActionPreference = 'Stop'
$PrimaryEnvPrefix = 'MINING_QA_'
$LegacyEnvPrefix = 'EDURAG_'

function Get-CompatVariableNames {
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

function Get-FirstAvailableVariableValue {
    param([Parameter(Mandatory = $true)][string[]]$Names)

    foreach ($name in $Names) {
        $processValue = (Get-Item -Path "Env:$name" -ErrorAction SilentlyContinue).Value
        if (-not [string]::IsNullOrWhiteSpace($processValue)) {
            return $processValue
        }

        $userValue = [Environment]::GetEnvironmentVariable($name, 'User')
        if (-not [string]::IsNullOrWhiteSpace($userValue)) {
            return $userValue
        }
    }

    return $null
}

function Test-DemoLikeKey {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $true
    }

    $v = $Value.Trim().ToLowerInvariant()
    return $v.StartsWith('demo-key') -or $v.Contains('change-me')
}

$targetNames = Get-CompatVariableNames -Name $TargetVar
$existingTarget = Get-FirstAvailableVariableValue -Names $targetNames

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
    throw "No usable API key found. Set user env '$SourceVar' or one of '$($targetNames -join "', '")' with a non-demo key."
}

foreach ($targetName in $targetNames) {
    Set-Item -Path "Env:$targetName" -Value $candidate
}

if ($PersistUser) {
    foreach ($targetName in $targetNames) {
        [Environment]::SetEnvironmentVariable($targetName, $candidate, 'User')
    }
}

$len = $candidate.Length
$prefixLen = [Math]::Min(6, $len)
$prefix = $candidate.Substring(0, $prefixLen)

Write-Host "Set in current process: $($targetNames -join ', ') (len=$len, prefix=$prefix*** )"
if ($PersistUser) {
    Write-Host "Persisted to user-level env vars: $($targetNames -join ', ')"
} else {
    Write-Host "Process-only set. Add -PersistUser to persist."
}
