#Requires -Version 5.1
function Invoke-Step_winget {
    param([object]$Ctx)
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        return New-StepResult -Id 'winget' -Status SKIP -Detail 'winget already in PATH'
    }
    if (-not $Ctx.Yes) {
        return New-StepResult -Id 'winget' -Status BLOCK -Rc 2 -Detail 'winget missing; use -Yes to install components' -NextCmd 'bootstrap.ps1 -Yes'
    }
    try {
        Install-Module Microsoft.WinGet.Client -Force -Repository PSGallery -Scope CurrentUser -ErrorAction Stop
        Import-Module Microsoft.WinGet.Client -Force -ErrorAction Stop
        Repair-WinGetPackageManager -AllUsers -ErrorAction Stop
        return New-StepResult -Id 'winget' -Status OK -Detail 'winget bootstrap completed'
    } catch {
        return New-StepResult -Id 'winget' -Status FAIL -Rc 3 -Retryable $true -Detail "winget bootstrap failed: $_" -NextCmd 'bootstrap.ps1 -Resume -Steps winget'
    }
}
