#Requires -Version 5.1
function Invoke-Step_venv {
    param([object]$Ctx)
    $res = Test-CorrectVenv -Root $Ctx.Root
    if ($res.ok) { return New-StepResult -Id 'venv' -Status SKIP -Detail $res.detail }

    $busy = @(Test-VenvBusy -Root $Ctx.Root)
    $warn = @()
    if ($busy.Count -gt 0) { $warn += "venv busy: $($busy -join ' | ')" }

    $pipBroken = ($res.exists -and $res.detail -eq 'pip is missing or broken')
    if ($pipBroken) {
        $next = ".\.venv\Scripts\python.exe -m ensurepip --upgrade; .\bootstrap.ps1 -Steps venv,deps"
        return New-StepResult -Id 'venv' -Status BLOCK -Rc 2 -Detail $res.detail -NextCmd $next -Warnings $warn
    }
    if ($res.exists) {
        $next = "Remove-Item -Recurse -Force .\.venv; .\bootstrap.ps1 -Steps venv,deps"
        return New-StepResult -Id 'venv' -Status BLOCK -Rc 2 -Detail $res.detail -NextCmd $next -Warnings $warn
    }

    $py = Find-Python -Explicit $Ctx.Python -TargetDir $Ctx.TargetDir
    if (-not $py -or -not $py.Usable) {
        return New-StepResult -Id 'venv' -Status BLOCK -Rc 2 -Detail 'no usable Python 3.15 x64 for venv' -NextCmd 'bootstrap.ps1 -Yes -Steps python,venv,deps' -Warnings $warn
    }
    & $py.Path -m venv (Join-Path $Ctx.Root '.venv')
    if ($LASTEXITCODE -ne 0) {
        return New-StepResult -Id 'venv' -Status FAIL -Rc 3 -Retryable $true -Detail "python -m venv rc=$LASTEXITCODE" -NextCmd 'bootstrap.ps1 -Resume -Steps venv,deps' -Warnings $warn
    }
    $again = Test-CorrectVenv -Root $Ctx.Root
    if (-not $again.ok) {
        return New-StepResult -Id 'venv' -Status BLOCK -Rc 2 -Detail $again.detail -NextCmd 'Remove-Item -Recurse -Force .\.venv; .\bootstrap.ps1 -Steps venv,deps' -Warnings $warn
    }
    return New-StepResult -Id 'venv' -Status OK -Detail $again.detail -Warnings $warn
}
