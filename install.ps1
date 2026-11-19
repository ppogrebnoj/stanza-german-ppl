#Requires -Version 5.1
<#
    install.ps1 — ОДНА команда человека (и агента): тонкий алиас на scripts\all.ps1.
    Никакой логики: все ключи пробрасываются дословно, источник правды один — all.ps1.

        .\install.ps1                      установка до конца (pretty-вывод, живой прогресс)
        .\install.ps1 -Inventory           только «что есть на машине» + по одной команде на каждое MISSING
        .\install.ps1 -CheckOnly -Json     то же, что scripts\all.ps1 -CheckOnly -Json (diff JSON пуст)
        .\install.ps1 -Json -ProgressJson -Log install.log   машинный режим для агента/CI

    Коды выхода совпадают с all.ps1: 0 готово, 2 нужен человек, 3 шаг упал, 4 сломан запуск,
    5 готово, нужно одно действие человека (MCP-конфиг + перезапуск клиента).
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)][object[]]$Rest
)
$ErrorActionPreference = 'Continue'
$target = Join-Path $PSScriptRoot 'scripts\all.ps1'
if (-not (Test-Path $target)) {
    Write-Host "СЛОМАН ЗАПУСК: нет $target — обновите репозиторий" -ForegroundColor Red
    exit 4
}
# проброс «как есть»: -Flag без значения = switch, -Param <значение> = параметр.
# Значений, начинающихся с «-», у ключей all.ps1 нет (пути, числа, списки шагов) — поэтому
# разбор безопасен; всё, что не распарсится, уйдёт в all.ps1 и будет его ошибка привязки (код 4).
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
