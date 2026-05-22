$ErrorActionPreference = 'Stop'

$launcherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ragQaRoot = Split-Path -Parent (Split-Path -Parent $launcherDir)

Set-Location $ragQaRoot
.\.venv\Scripts\python.exe .\build_metallurgy_dataset_experiments_offline.py @args