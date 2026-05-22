$ErrorActionPreference = 'Stop'

$launcherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ragQaRoot = Split-Path -Parent (Split-Path -Parent $launcherDir)

Set-Location $ragQaRoot
python .\build_strategy_classifier_dataset_v2.py @args