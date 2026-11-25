#Requires -Version 5.1
function Invoke-Step_acceptance {
    param([object]$Ctx)
    $py = Join-Path $Ctx.Root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $py)) { $py = $Ctx.PythonPath }
    $runner = Join-Path $Ctx.Root 'scripts\run_checks.py'
    if (-not $py -or -not (Test-Path -LiteralPath $runner)) {
        return New-StepResult -Id 'acceptance' -Status BLOCK -Rc 2 -Detail 'acceptance prerequisites missing' -NextCmd 'bootstrap.ps1 -Steps venv,deps,models,doctor,acceptance'
    }
    $null = & $py $runner --check acceptance --json 2>&1
    $rc = $LASTEXITCODE
    if ($rc -ne 0) {
        return New-StepResult -Id 'acceptance' -Status FAIL -Rc 1 -Retryable $false -Detail "acceptance rc=$rc (F1 mismatch or gate failed)" -NextCmd 'check acceptance output; do not update rule numbers'
    }
    return New-StepResult -Id 'acceptance' -Status OK -Detail 'acceptance OK: F1 0.777 / 0.686'
}
