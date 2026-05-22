$ErrorActionPreference = 'Stop'

$launcherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$experimentRoot = Split-Path -Parent $launcherDir
$ragQaRoot = Split-Path -Parent (Split-Path -Parent $experimentRoot)

Set-Location $ragQaRoot
python .\teacher_demo_experiments\01_chunking_performance\benchmark_chunk_configs_internal.py @args

$reportPath = Join-Path $ragQaRoot 'teacher_demo_experiments\01_chunking_performance\artifacts\chunk_config_internal\chunk_config_internal_report.json'
if (Test-Path $reportPath) {
    python .\teacher_demo_experiments\01_chunking_performance\generate_chunk_config_internal_artifacts.py --report $reportPath
}