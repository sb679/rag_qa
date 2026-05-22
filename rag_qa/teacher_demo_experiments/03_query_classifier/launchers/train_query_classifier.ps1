$ErrorActionPreference = 'Stop'

$launcherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ragQaRoot = Split-Path -Parent (Split-Path -Parent $launcherDir)

Set-Location $ragQaRoot
python .\train_classifier.py @args