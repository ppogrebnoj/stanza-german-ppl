#Requires -Version 5.1
function Invoke-Step_powershell {
    param([object]$Ctx)
    if (Get-Command pwsh -ErrorAction SilentlyContinue) {
        return New-StepResult -Id 'powershell' -Status SKIP -Detail 'pwsh already in PATH'
    }
    if (-not $Ctx.Yes) {
        return New-StepResult -Id 'powershell' -Status BLOCK -Rc 2 -Detail 'PowerShell 7.7 missing; use -Yes' -NextCmd 'bootstrap.ps1 -Yes -Steps powershell'
    }
    $base = 'https://github.com/PowerShell/PowerShell/releases/download/v7.7.0'
    $msix = Join-Path $Ctx.ArtifactDir 'PowerShell-7.7.0.msixbundle'
    $dl = Invoke-Download -Url "$base/PowerShell-7.7.0.msixbundle" -Dest $msix -Retries $Ctx.Retries
    if ($dl.ok) {
        try {
            Add-AppxPackage -Path $msix -ErrorAction Stop
            return New-StepResult -Id 'powershell' -Status OK -Detail 'PowerShell 7.7 MSIX installed'
        } catch { }
    }
    $zip = Join-Path $Ctx.ArtifactDir 'PowerShell-7.7.0-win-x64.zip'
    $dl2 = Invoke-Download -Url "$base/PowerShell-7.7.0-win-x64.zip" -Dest $zip -Retries $Ctx.Retries
    if (-not $dl2.ok) {
        return New-StepResult -Id 'powershell' -Status DELIVERY -Rc 5 -Retryable $true -Detail "PowerShell download failed: $($dl2.detail)" -NextCmd 'bootstrap.ps1 -Resume -Steps powershell'
    }
    $dest = Join-Path $env:LOCALAPPDATA 'Programs\PowerShell\7.7.0'
    try {
        if (-not (Test-Path -LiteralPath $dest)) { New-Item -ItemType Directory -Force -Path $dest | Out-Null }
        Expand-Archive -LiteralPath $zip -DestinationPath $dest -Force -ErrorAction Stop
        return New-StepResult -Id 'powershell' -Status OK -Detail "portable PowerShell installed: $dest"
    } catch {
        return New-StepResult -Id 'powershell' -Status FAIL -Rc 1 -Detail "portable PowerShell unpack failed: $_"
    }
}
