#Requires -Version 5.1
<#
    scripts\install.ps1 — алиас на scripts\all.ps1 (тот же контракт, что у корневого install.ps1).
    Нужен, чтобы «одна команда» была одинаковой из корня и из scripts\. Логики нет.
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)][object[]]$Rest
)
$ErrorActionPreference = 'Continue'
$target = Join-Path $PSScriptRoot 'all.ps1'
if (-not (Test-Path $target)) {
    Write-Host "СЛОМАН ЗАПУСК: нет $target — обновите репозиторий" -ForegroundColor Red
    exit 4
}
$bound = @{}
$i = 0
while ($Rest -and $i -lt $Rest.Count) {
    $a = "$($Rest[$i])"
    if ($a -like '-*') {
        $name = $a.TrimStart('-')
        if ($i + 1 -lt $Rest.Count -and "$($Rest[$i + 1])" -notlike '-*') { $bound[$name] = $Rest[$i + 1]; $i += 2 }
        else { $bound[$name] = $true; $i += 1 }
    } else { $i += 1 }
}
if ($bound.Count -gt 0) { & $target @bound } else { & $target }
exit $LASTEXITCODE
