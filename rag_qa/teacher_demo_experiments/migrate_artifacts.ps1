param()

$ErrorActionPreference = 'Stop'

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ragQaRoot = Split-Path -Parent $scriptDir

function Ensure-Directory {
    param(
        [Parameter(Mandatory = $true)][string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Copy-Artifact {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Target
    )

    if (-not (Test-Path -LiteralPath $Source)) {
        Write-Host "skip missing: $Source"
        return
    }

    $targetParent = Split-Path -Parent $Target
    if ($targetParent) {
        Ensure-Directory -Path $targetParent
    }

    if (Test-Path -LiteralPath $Target) {
        Write-Host "skip existing target: $Target"
        return
    }

    Copy-Item -LiteralPath $Source -Destination $Target -Recurse -Force
    Write-Host "copied: $Source -> $Target"
}

function Copy-DirectoryContents {
    param(
        [Parameter(Mandatory = $true)][string]$SourceDir,
        [Parameter(Mandatory = $true)][string]$TargetDir
    )

    if (-not (Test-Path -LiteralPath $SourceDir)) {
        Write-Host "skip missing: $SourceDir"
        return
    }

    Ensure-Directory -Path $TargetDir

    Get-ChildItem -LiteralPath $SourceDir -Force | ForEach-Object {
        $targetPath = Join-Path $TargetDir $_.Name
        if (Test-Path -LiteralPath $targetPath) {
            Write-Host "skip existing target: $targetPath"
            return
        }

        Copy-Item -LiteralPath $_.FullName -Destination $targetPath -Recurse -Force
        Write-Host "copied: $($_.FullName) -> $targetPath"
    }
}

$requiredDirs = @(
    '01_chunking_performance\artifacts',
    '01_chunking_performance\launchers',
    '02_strategy_selector\artifacts',
    '02_strategy_selector\launchers',
    '03_query_classifier\artifacts',
    '03_query_classifier\launchers',
    '03_query_classifier\model_snapshot',
    '04_ragas_dataset_quality\artifacts',
    '04_ragas_dataset_quality\launchers',
    '05_ragas_evaluation\artifacts',
    '05_ragas_evaluation\launchers'
)

foreach ($relativeDir in $requiredDirs) {
    Ensure-Directory -Path (Join-Path $scriptDir $relativeDir)
}

Copy-DirectoryContents -SourceDir (Join-Path $ragQaRoot 'ragas_paper_bundle\strategy_selector_experiment') -TargetDir (Join-Path $scriptDir '02_strategy_selector\artifacts')
Copy-DirectoryContents -SourceDir (Join-Path $ragQaRoot 'classify_data') -TargetDir (Join-Path $scriptDir '03_query_classifier\artifacts')
Copy-Artifact -Source (Join-Path $ragQaRoot 'bert_query_classifier_new') -Target (Join-Path $scriptDir '03_query_classifier\model_snapshot\bert_query_classifier_new')

Copy-Artifact -Source (Join-Path $ragQaRoot 'ragas_paper_bundle\datasets') -Target (Join-Path $scriptDir '04_ragas_dataset_quality\artifacts\datasets')
Copy-Artifact -Source (Join-Path $ragQaRoot 'ragas_paper_bundle\results') -Target (Join-Path $scriptDir '04_ragas_dataset_quality\artifacts\results')
Copy-Artifact -Source (Join-Path $ragQaRoot 'ragas_paper_bundle\plots') -Target (Join-Path $scriptDir '04_ragas_dataset_quality\artifacts\plots')
Copy-Artifact -Source (Join-Path $ragQaRoot 'ragas_paper_bundle\illustrative_only') -Target (Join-Path $scriptDir '04_ragas_dataset_quality\artifacts\illustrative_only')

Copy-Artifact -Source (Join-Path $ragQaRoot 'rag_assesment\generated_datasets\metallurgy_dataset_suite') -Target (Join-Path $scriptDir '04_ragas_dataset_quality\artifacts\generated_datasets\metallurgy_dataset_suite')
Copy-Artifact -Source (Join-Path $ragQaRoot 'rag_assesment\generated_datasets\metallurgy_method_experiments') -Target (Join-Path $scriptDir '04_ragas_dataset_quality\artifacts\generated_datasets\metallurgy_method_experiments')
Copy-Artifact -Source (Join-Path $ragQaRoot 'rag_assesment\generated_datasets\metallurgy_safety_testset.json') -Target (Join-Path $scriptDir '04_ragas_dataset_quality\artifacts\generated_datasets\metallurgy_safety_testset.json')
Copy-Artifact -Source (Join-Path $ragQaRoot 'rag_assesment\generated_datasets\metallurgy_safety_testset.summary.json') -Target (Join-Path $scriptDir '04_ragas_dataset_quality\artifacts\generated_datasets\metallurgy_safety_testset.summary.json')

Copy-Artifact -Source (Join-Path $ragQaRoot 'rag_assesment\generated_datasets\official_ragas_eval') -Target (Join-Path $scriptDir '05_ragas_evaluation\artifacts\official_ragas_eval')

Copy-Artifact -Source (Join-Path $ragQaRoot 'rag_assesment\generated_datasets\benchmark_km_report.json') -Target (Join-Path $scriptDir '01_chunking_performance\artifacts\benchmark_km_report.json')
Copy-Artifact -Source (Join-Path $ragQaRoot 'rag_assesment\generated_datasets\testset_20260417_183026.json') -Target (Join-Path $scriptDir '01_chunking_performance\artifacts\testset_20260417_183026.json')

Write-Host 'teacher_demo_artifacts_copied'