#Requires -Version 5.1
<#
    scripts\install.ps1 — алиас корневого install.ps1 для вызова из каталога scripts.
    Тот же контракт v2: реестр ключей docs/flags.json, неизвестный ключ = код 4.
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)][object[]]$Rest
)
$ErrorActionPreference = 'Continue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$target = Join-Path $PSScriptRoot 'all.ps1'
$bound = @{}
$errors = @()
$flagsPath = Join-Path $root 'docs\flags.json'
$byName = @{}
if (Test-Path -LiteralPath $flagsPath) {
    try {
        $reg = Get-Content -LiteralPath $flagsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($f in @($reg.flags)) { $byName["$($f.name)"] = $f }
    } catch { }
}
$i = 0
while ($Rest -and $i -lt $Rest.Count) {
    $a = "$($Rest[$i])"
    if ($a -like '-*') {
        $name = $a.TrimStart('-')
        if (-not $byName.ContainsKey($name)) { $errors += "неизвестный параметр -$name"; $i++; continue }
        if ("$($byName[$name].kind)" -eq 'switch') { $bound[$name] = $true; $i++ }
        elseif ($i + 1 -lt $Rest.Count -and "$($Rest[$i+1])" -notlike '-*') { $bound[$name] = "$($Rest[$i+1])"; $i += 2 }
        else { $errors += "-$name требует значения"; $i++ }
    } else { $i++ }
}
$wantsJson = $bound.ContainsKey('Json')
if ($wantsJson) { try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { } }
if ($errors.Count) {
    if (-not $wantsJson) { foreach ($e in $errors) { Write-Host "СЛОМАН ЗАПУСК: $e (код 4)" -ForegroundColor Red } }
    else { [Console]::Out.WriteLine(([pscustomobject][ordered]@{ schema_version = 2; code = 4; ok = $false; failures = @([pscustomobject]@{ id = 'params'; detail = ($errors -join '; '); retryable = $false }) } | ConvertTo-Json -Depth 5)) }
    exit 4
}
if (-not (Test-Path -LiteralPath $target)) {
    Write-Host "СЛОМАН ЗАПУСК: нет $target" -ForegroundColor Red
    exit 4
}
if ($bound.Count -gt 0) { & $target @bound } else { & $target }
exit $LASTEXITCODE
