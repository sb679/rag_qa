$ErrorActionPreference = 'Stop'

$launcherDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$experimentDir = Split-Path -Parent $launcherDir
$teacherDemoRoot = Split-Path -Parent $experimentDir
$ragQaRoot = Split-Path -Parent $teacherDemoRoot
$pythonExe = Join-Path $ragQaRoot '.venv\Scripts\python.exe'
$datasetPath = '.\teacher_demo_experiments\04_ragas_dataset_quality\artifacts\datasets\metallurgy_test.json'

Set-Location $ragQaRoot

& $pythonExe .\benchmark_km_triplets.py --dataset $datasetPath --max-queries 20 --per-query-timeout 45 --min-interval-sec 2.5 --output .\teacher_demo_experiments\01_chunking_performance\artifacts\benchmark_km_report.json
& $pythonExe .\teacher_demo_experiments\01_chunking_performance\generate_chunking_benchmark_artifacts.py