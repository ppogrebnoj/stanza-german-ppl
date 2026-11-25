#Requires -Version 5.1
function Invoke-Step_doctor {
    param([object]$Ctx)
    $py = Join-Path $Ctx.Root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $py)) { $py = $Ctx.PythonPath }
    if (-not $py) {
        return New-StepResult -Id 'doctor' -Status BLOCK -Rc 2 -Detail 'no Python interpreter for doctor' -NextCmd 'bootstrap.ps1 -Steps python,venv,deps,doctor'
    }
    $script = Join-Path $Ctx.Root 'scripts\doctor.py'
    $null = & $py $script --json 2>&1
    $rc = $LASTEXITCODE
    if ($rc -ne 0) {
        return New-StepResult -Id 'doctor' -Status FAIL -Rc 1 -Retryable $false -Detail "doctor rc=$rc" -NextCmd 'see doctor output; fix FAIL positions'
    }
    return New-StepResult -Id 'doctor' -Status OK -Detail 'doctor OK'
}
