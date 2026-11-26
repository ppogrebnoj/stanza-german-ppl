#Requires -Version 5.1
function Invoke-Step_winget {
    param([object]$Ctx)
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        $alias = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps\winget.exe'
        if (Test-Path -LiteralPath $alias) { $winget = [pscustomobject]@{ Source = $alias } }
    }
    if ($winget) {
        return New-StepResult -Id 'winget' -Status SKIP -Detail "winget already in PATH: $($winget.Source)"
    }

    # winget — необязательный компонент: все его шаги имеют прямые загрузки.
    # Раньше Repair-WinGetPackageManager падал в headless-хосте без App Installer
    # и отравлял итоговый код rc=3. Регистрация App Installer — ручная операция
    # владельца машины, установщик её НЕ требует и НЕ выполняет.
    return New-StepResult -Id 'winget' -Status SKIP -Detail 'winget unavailable; optional step skipped (direct downloads are used)' -Warnings @('App Installer (winget) не найден; шаг опционален, итоговый код не меняется')
}
