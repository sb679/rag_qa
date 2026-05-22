$ErrorActionPreference = 'Stop'

$launcherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$experimentDir = Split-Path -Parent $launcherDir
$teacherDemoRoot = Split-Path -Parent $experimentDir
$ragQaRoot = Split-Path -Parent $teacherDemoRoot
$pythonExe = Join-Path $ragQaRoot '.venv\Scripts\python.exe'

Set-Location $ragQaRoot

& $pythonExe .\evaluate_strategy_selector.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

& $pythonExe .\teacher_demo_experiments\02_strategy_selector\generate_strategy_selector_artifacts.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }