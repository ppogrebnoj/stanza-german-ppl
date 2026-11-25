#Requires -Version 5.1
function Invoke-Step_models {
    param([object]$Ctx)
    $py = Join-Path $Ctx.Root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $py)) {
        return New-StepResult -Id 'models' -Status BLOCK -Rc 2 -Detail '.venv missing' -NextCmd 'bootstrap.ps1 -Steps venv,deps,models'
    }
    $resources = if ($Ctx.ModelsDir) { $Ctx.ModelsDir } else { Join-Path $Ctx.Root '.stanza\models' }
    $busy = @(Test-VenvBusy -Root $Ctx.Root)
    $warn = @()
    if ($busy.Count -gt 0) { $warn += "venv busy: $($busy -join ' | ')" }

    $old = $env:STANZA_RESOURCES_DIR
    $env:STANZA_RESOURCES_DIR = $resources
    try {
        $code = "import stanza; stanza.download('de', processors='tokenize,mwt,pos,lemma,depparse', verbose=False)"
        $null = & $py -c $code 2>&1
        $rc = $LASTEXITCODE
        if ($rc -ne 0) {
            return New-StepResult -Id 'models' -Status FAIL -Rc 3 -Retryable $true -Detail "stanza.download rc=$rc" -NextCmd 'bootstrap.ps1 -Resume -Steps models' -Warnings $warn
        }
        $checker = Join-Path $Ctx.Root 'scripts\check_models.py'
        if (Test-Path -LiteralPath $checker) {
            $null = & $py $checker --json 2>&1
            if ($LASTEXITCODE -ne 0) {
                return New-StepResult -Id 'models' -Status FAIL -Rc 3 -Retryable $true -Detail 'model processor check failed' -NextCmd 'bootstrap.ps1 -Resume -Steps models' -Warnings $warn
            }
        }
        return New-StepResult -Id 'models' -Status OK -Detail "models ready: $resources" -Warnings $warn
    } finally {
        $env:STANZA_RESOURCES_DIR = $old
    }
}
