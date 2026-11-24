#Requires -Version 5.1
<#
    install.ps1 — публичный интерфейс установки (человек, агент, bootstrap.ps1, CI).
    Логики нет: параметры пробрасываются в scripts\all.ps1 без изменений.
    Реестр разрешённых ключей — docs/flags.json; неизвестный ключ даёт код 4.

        .\install.ps1 -Yes
        .\install.ps1 -Check inventory -Json
        .\install.ps1 -Acceptance -Json -ProgressJson
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)][object[]]$Rest
)
$ErrorActionPreference = 'Continue'
$root = (Resolve-Path $PSScriptRoot).Path
$target = Join-Path $root 'scripts\all.ps1'
$bound = @{}
$errors = @()
$flags = @()
$flagsPath = Join-Path $root 'docs\flags.json'
if (Test-Path -LiteralPath $flagsPath) {
    try {
        $reg = Get-Content -LiteralPath $flagsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $flags = @($reg.flags)
    } catch { }
}
$byName = @{}
foreach ($f in $flags) { $byName["$($f.name)"] = $f }

$i = 0
while ($Rest -and $i -lt $Rest.Count) {
    $a = "$($Rest[$i])"
    if ($a -like '-*') {
        $name = $a.TrimStart('-')
        if (-not $byName.ContainsKey($name)) {
            $errors += "неизвестный параметр -$name"
            $i++
            continue
        }
        $kind = "$($byName[$name].kind)"
        if ($kind -eq 'switch') {
            $bound[$name] = $true
            $i++
        } else {
            if ($i + 1 -ge $Rest.Count -or "$($Rest[$i + 1])" -like '-*') {
                $errors += "параметр -$name требует значения"
                $i++
            } else {
                $bound[$name] = "$($Rest[$i + 1])"
                $i += 2
            }
        }
    } else { $i++ }   # позиционные аргументы игнорируются (их нет в контракте)
}

$wantsJson = $bound.ContainsKey('Json')
if ($wantsJson) { try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { } }
if ($errors.Count) {
    if (-not $wantsJson) { foreach ($e in $errors) { Write-Host "СЛОМАН ЗАПУСК: $e (код 4)" -ForegroundColor Red } }
    if ($wantsJson) {
        $msg = ($errors -join '; ')
        [Console]::Out.WriteLine(([pscustomobject][ordered]@{
            code = 4; ok = $false
            failures = @([pscustomobject]@{ id = 'params'; detail = $msg; retryable = $false })
        } | ConvertTo-Json -Depth 5))
    }
    exit 4
}
if (-not (Test-Path -LiteralPath $target)) {
    if ($wantsJson) {
        [Console]::Out.WriteLine(([pscustomobject][ordered]@{ code = 4; ok = $false; failures = @([pscustomobject]@{ id = 'entry'; detail = "нет $target"; retryable = $false }) } | ConvertTo-Json -Depth 5))
    } else { Write-Host "СЛОМАН ЗАПУСК: нет $target — обновите репозиторий" -ForegroundColor Red }
    exit 4
}
if ($bound.Count -gt 0) { & $target @bound } else { & $target }
exit $LASTEXITCODE
