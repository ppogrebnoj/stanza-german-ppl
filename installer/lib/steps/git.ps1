#Requires -Version 5.1
function Invoke-Step_git {
    param([object]$Ctx)
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) { return New-StepResult -Id 'git' -Status SKIP -Detail "git already in PATH: $($git.Source)" }
    if (-not $Ctx.Yes) {
        return New-StepResult -Id 'git' -Status BLOCK -Rc 2 -Detail 'git missing; use -Yes' -NextCmd 'bootstrap.ps1 -Yes -Steps git'
    }
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        & winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements
        if ($LASTEXITCODE -eq 0) {
            return New-StepResult -Id 'git' -Status OK -Detail 'git installed via winget'
        }
    }
    $exe = Join-Path $Ctx.ArtifactDir 'Git-2.56.1-64-bit.exe'
    $dl = Invoke-Download -Url 'https://github.com/git-for-windows/git/releases/download/v2.56.1.windows.1/Git-2.56.1-64-bit.exe' -Dest $exe -Retries $Ctx.Retries
    if (-not $dl.ok) {
        return New-StepResult -Id 'git' -Status DELIVERY -Rc 5 -Retryable $true -Detail "git installer download failed: $($dl.detail)" -NextCmd 'bootstrap.ps1 -Resume -Steps git'
    }
    & $exe /VERYSILENT /NORESTART
    if ($LASTEXITCODE -ne 0) {
        return New-StepResult -Id 'git' -Status FAIL -Rc 3 -Retryable $true -Detail "git installer rc=$LASTEXITCODE" -NextCmd 'bootstrap.ps1 -Resume -Steps git'
    }
    # Следующие шаги в том же процессе должны видеть свежий PATH из реестра.
    Refresh-ProcessPath
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        return New-StepResult -Id 'git' -Status FAIL -Rc 3 -Retryable $true -Detail 'git installed but not visible in PATH after refresh' -NextCmd 'bootstrap.ps1 -Resume -Steps git,workspace'
    }
    return New-StepResult -Id 'git' -Status OK -Detail 'git installed from official installer'
}
