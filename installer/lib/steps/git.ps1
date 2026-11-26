#Requires -Version 5.1
function Invoke-Step_git {
    param([object]$Ctx)
    $gitPath = Ensure-GitOnPath
    if ($gitPath) { return New-StepResult -Id 'git' -Status SKIP -Detail "git already available: $gitPath" }
    if (-not $Ctx.Yes) {
        return New-StepResult -Id 'git' -Status BLOCK -Rc 2 -Detail 'git missing; use -Yes' -NextCmd 'bootstrap.ps1 -Yes -Steps git'
    }
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        $wa = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\winget.exe'
        if (Test-Path -LiteralPath $wa) { $winget = [pscustomobject]@{ Source = $wa } }
    }
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
    $installerRc = $LASTEXITCODE
    # Inno Setup /VERYSILENT возвращается раньше, чем git.exe появится на диске.
    # Ждём появления бинарника, затем подмешиваем его каталог в PATH процесса.
    $gitPath = ''
    $deadline = [DateTime]::UtcNow.AddSeconds(180)
    do {
        Refresh-ProcessPath
        $gitPath = Ensure-GitOnPath
        if ($gitPath) { break }
        Start-Sleep -Seconds 3
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $gitPath) {
        $detail = if ($installerRc -ne 0) { "git installer rc=$installerRc and git.exe not found after 180s" } else { 'git.exe not found after 180s (installer rc=0)' }
        return New-StepResult -Id 'git' -Status FAIL -Rc 3 -Retryable $true -Detail $detail -NextCmd 'bootstrap.ps1 -Resume -Steps git,workspace'
    }
    return New-StepResult -Id 'git' -Status OK -Detail "git installed from official installer: $gitPath"
}
