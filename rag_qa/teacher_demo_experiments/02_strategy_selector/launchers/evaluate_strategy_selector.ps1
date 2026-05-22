$ErrorActionPreference = 'Stop'

$launcherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$experimentDir = Split-Path -Parent $launcherDir
$teacherDemoRoot = Split-Path -Parent $experimentDir
$ragQaRoot = Split-Path -Parent $teacherDemoRoot
$pythonExe = Join-Path $ragQaRoot '.venv\Scripts\python.exe'

Set-Location $ragQaRoot
& $pythonExe .\evaluate_strategy_selector.py @args