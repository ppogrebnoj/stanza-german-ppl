#Requires -Version 5.1
function Invoke-Step_acceptance {
    param([object]$Ctx)
    $py = Join-Path $Ctx.Root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $py)) { $py = $Ctx.PythonPath }
    $runner = Join-Path $Ctx.Root 'scripts\run_checks.py'
    if (-not $py -or -not (Test-Path -LiteralPath $runner)) {
        return New-StepResult -Id 'acceptance' -Status BLOCK -Rc 2 -Detail 'acceptance prerequisites missing' -NextCmd 'bootstrap.ps1 -Steps venv,deps,models,doctor,acceptance'
    }
    # Приёмка (doctor + smoke + mcp_probe) должна видеть тот же каталог моделей,
    # что и шаг models: без env ищется %LOCALAPPDATA%\StanfordNLP и всё падает.
    $resources = if ($Ctx.ModelsDir) { $Ctx.ModelsDir } else { Join-Path $Ctx.Root '.stanza\models' }
    $oldStan = $env:STANZA_RESOURCES_DIR
    $oldUtf8 = $env:PYTHONUTF8
    $env:STANZA_RESOURCES_DIR = $resources
    $env:PYTHONUTF8 = '1'
    try {
        $null = & $py $runner --check acceptance --json 2>&1
        $rc = $LASTEXITCODE
    } finally {
        $env:STANZA_RESOURCES_DIR = $oldStan
        $env:PYTHONUTF8 = $oldUtf8
    }
    if ($rc -ne 0) {
        return New-StepResult -Id 'acceptance' -Status FAIL -Rc 1 -Retryable $false -Detail "acceptance rc=$rc (F1 mismatch or gate failed)" -NextCmd 'check acceptance output; do not update rule numbers'
    }
    return New-StepResult -Id 'acceptance' -Status OK -Detail 'acceptance OK: F1 0.777 / 0.686'
}
