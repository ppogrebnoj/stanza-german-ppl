#Requires -Version 5.1
function Invoke-Step_deps {
    param([object]$Ctx)
    $py = Join-Path $Ctx.Root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $py)) {
        return New-StepResult -Id 'deps' -Status BLOCK -Rc 2 -Detail '.venv missing' -NextCmd 'bootstrap.ps1 -Steps venv,deps'
    }
    $busy = @(Test-VenvBusy -Root $Ctx.Root)
    $warn = @()
    if ($busy.Count -gt 0) { $warn += "venv busy: $($busy -join ' | ')" }

    # KI_DEPS_TOTAL_TIMEOUT_SEC is the total import-smoke budget (default 900s).
    # KI_IMPORT_TIMEOUT_SEC is kept as a legacy alias when the total is not set.
    $timeoutMs = 900000
    $timeoutVar = 'KI_DEPS_TOTAL_TIMEOUT_SEC'
    if (-not [Environment]::GetEnvironmentVariable($timeoutVar) -and $env:KI_IMPORT_TIMEOUT_SEC) { $timeoutVar = 'KI_IMPORT_TIMEOUT_SEC' }
    $raw = [Environment]::GetEnvironmentVariable($timeoutVar)
    if ($raw) {
        $n = 0
        if ([int]::TryParse($raw, [ref]$n) -and $n -gt 0) { $timeoutMs = $n * 1000 }
    }
    $state = Test-DepsState -Root $Ctx.Root -ArtifactDir $Ctx.ArtifactDir -TimeoutMs $timeoutMs
    if ($state.ok -and -not $Ctx.Resume) {
        return New-StepResult -Id 'deps' -Status SKIP -Detail $state.detail -Warnings (@($warn) + @($state.warnings))
    }

    # -Resume -Steps deps always reinstalls from lock; idempotent by design.
    Remove-LockInstalledMarker -ArtifactDir $Ctx.ArtifactDir
    $lock = Join-Path $Ctx.Root 'installer\requirements.lock'
    $null = & $py -m pip install --only-binary=:all: --retries $Ctx.Retries --timeout 60 -r $lock 2>&1
    $rc = $LASTEXITCODE
    if ($rc -ne 0) {
        return New-StepResult -Id 'deps' -Status FAIL -Rc 3 -Retryable $true -Detail "pip install rc=$rc" -NextCmd 'bootstrap.ps1 -Resume -Steps deps' -Warnings $warn
    }
    Set-LockInstalledMarker -ArtifactDir $Ctx.ArtifactDir

    $again = Test-DepsState -Root $Ctx.Root -ArtifactDir $Ctx.ArtifactDir -TimeoutMs $timeoutMs
    if ($again.ok) {
        return New-StepResult -Id 'deps' -Status OK -Detail $again.detail -Warnings (@($warn) + @($again.warnings))
    }
    return New-StepResult -Id 'deps' -Status FAIL -Rc $again.rc -Retryable $again.retryable -Detail $again.detail -NextCmd 'Remove-Item -Recurse -Force .\.venv; .\bootstrap.ps1 -Steps venv,deps' -Warnings (@($warn) + @($again.warnings))
}
