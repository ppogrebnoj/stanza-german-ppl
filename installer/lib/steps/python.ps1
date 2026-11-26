#Requires -Version 5.1
function Invoke-Step_python {
    param([object]$Ctx)
    $info = Find-Python -Explicit $Ctx.Python -TargetDir $Ctx.TargetDir
    if ($info -and $info.Usable) {
        return New-StepResult -Id 'python' -Status OK -Detail "Python $($info.Version) $($info.Bits)bit: $($info.Path)"
    }
    if (-not $Ctx.Yes) {
        $d = if ($info) { "found Python $($info.Version) but unusable: $($info.Reason)" } else { 'Python 3.15 x64 not found' }
        return New-StepResult -Id 'python' -Status BLOCK -Rc 2 -Detail $d -NextCmd 'bootstrap.ps1 -Yes -Steps python'
    }
    $exe = Join-Path $Ctx.ArtifactDir 'python-3.15.2-amd64.exe'
    $dl = Invoke-Download -Url 'https://www.python.org/ftp/python/3.15.2/python-3.15.2-amd64.exe' -Dest $exe -Retries $Ctx.Retries
    if (-not $dl.ok) {
        return New-StepResult -Id 'python' -Status DELIVERY -Rc 5 -Retryable $true -Detail "Python installer download failed: $($dl.detail)" -NextCmd 'bootstrap.ps1 -Resume -Steps python'
    }
    & $exe /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
    $rc = $LASTEXITCODE
    if ($rc -ne 0) {
        return New-StepResult -Id 'python' -Status FAIL -Rc 3 -Retryable $true -Detail "python installer rc=$rc" -NextCmd 'bootstrap.ps1 -Resume -Steps python'
    }
    # /quiet возвращается до того, как инсталлятор дописал реестр и PATH:
    # опрашиваем Find-Python вместо однократной проверки в том же процессе.
    $again = $null
    $deadline = [DateTime]::UtcNow.AddSeconds(180)
    do {
        $again = Find-Python -Explicit $Ctx.Python -TargetDir $Ctx.TargetDir
        if ($again -and $again.Usable) { break }
        Start-Sleep -Seconds 3
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not $again -or -not $again.Usable) {
        return New-StepResult -Id 'python' -Status FAIL -Rc 3 -Retryable $true -Detail 'installer finished but Python 3.15 x64 still not usable after 180s' -NextCmd 'bootstrap.ps1 -Resume -Steps python'
    }
    return New-StepResult -Id 'python' -Status OK -Detail "Python installed: $($again.Path)"
}
