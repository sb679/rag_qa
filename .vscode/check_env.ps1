$ErrorActionPreference = 'Stop'

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$expectedPython = Join-Path $workspaceRoot 'rag_qa\.venv\Scripts\python.exe'
$backendDir = Join-Path $workspaceRoot 'rag_qa\web\backend'

Write-Output '=== EduRAG Environment Self-Check ==='
Write-Output "Workspace: $workspaceRoot"
Write-Output "Expected interpreter: $expectedPython"

if (-not (Test-Path $expectedPython)) {
    Write-Error "Expected interpreter not found: $expectedPython"
    exit 1
}

$currentPythonCmd = Get-Command python -ErrorAction SilentlyContinue
if ($null -ne $currentPythonCmd) {
    Write-Output "Shell python command: $($currentPythonCmd.Source)"
} else {
    Write-Output 'Shell python command: NOT FOUND'
}

$checkCode = @'
import importlib
import platform
import sys

print(f'Interpreter in use: {sys.executable}')
print(f'Python version: {platform.python_version()}')

modules = ['fastapi', 'uvicorn', 'jwt', 'langchain', 'torch']
failed = []
for name in modules:
    try:
        module = importlib.import_module(name)
        version = getattr(module, '__version__', 'unknown')
        print(f'{name}: OK ({version})')
    except Exception as exc:
        print(f'{name}: ERROR ({type(exc).__name__}: {exc})')
        failed.append(name)

if failed:
    print('Missing/broken modules:', ', '.join(failed))
    raise SystemExit(1)
'@

Write-Output ''
Write-Output '--- Core dependency check in rag_qa/.venv ---'
& $expectedPython -c $checkCode
if ($LASTEXITCODE -ne 0) {
    Write-Error 'Core dependency check failed.'
    exit 1
}

Write-Output ''
Write-Output '--- Backend entry import check ---'
Push-Location $backendDir
try {
    & $expectedPython -c "import main; print('backend_main_import: OK')"
    if ($LASTEXITCODE -ne 0) {
        throw 'backend_main_import failed'
    }
} finally {
    Pop-Location
}

Write-Output ''
Write-Output 'Environment check passed.'
exit 0
