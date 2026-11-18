param(
    [int]$TrainingProcessId = 0,
    [string]$Run = 'output/training/runs/reviewed-v2',
    [string]$Data = 'output/training/dataset-v2',
    [string]$LabelInput = 'output/training/reviewed-v2.jsonl',
    [string]$LabelOutput = 'output/training/auto-label-v1'
)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
$trainingPython = Join-Path (Get-Location) '.venv-training/Scripts/python.exe'
try {
    if ($TrainingProcessId -gt 0) {
        Wait-Process -Id $TrainingProcessId -ErrorAction SilentlyContinue
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Run 'training-report.json'))) {
        throw 'Training did not produce a completed report. Inspect the training process output.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Run 'generation-evaluation.json'))) {
        & $trainingPython -m training.evaluate_adapter --run $Run --data $Data --threads 4
        if ($LASTEXITCODE -ne 0) { throw 'Generation evaluation failed.' }
    }
    if (-not (Test-Path -LiteralPath (Join-Path $Run 'import-report.json'))) {
        & $trainingPython -m training.export_model --run $Run
        if ($LASTEXITCODE -ne 0) { throw 'Experimental model export/import failed.' }
    }
} catch {
    Write-Output "Training follow-up stopped: $_"
} finally {
    # Run sequentially to avoid competing with training for laptop memory/CPU.
    & $trainingPython -m training.auto_label $LabelInput $LabelOutput
    if ($LASTEXITCODE -ne 0) { throw 'Labeling stopped; inspect logs and rerun to resume.' }
}
