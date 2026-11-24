#Requires -Version 5.1
<#
    test-contract.ps1 — регресс текущего контракта без Python и сети.

        powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\test-contract.ps1

    Проверяет: неизвестный параметр = код 4, -Check только чтение, capabilities = docs/flags.json,
    одинаковый вывод install.ps1 и scripts/all.ps1, поля отчёта, NDJSON в файле, Resume SKIP,
    нормализацию архитектуры. Код выхода 0 = все тесты зелёные.
#>
$ErrorActionPreference = 'Continue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$entry = Join-Path $root 'install.ps1'
$inner = Join-Path $root 'scripts\all.ps1'
$failures = @()
$total = 0

function Check-Ok { param([bool]$Ok, [string]$Name, [string]$Detail = '')
    $script:total++
    if ($Ok) { Write-Host ("  PASS  " + $Name) -ForegroundColor Green }
    else { Write-Host ("  FAIL  " + $Name + " :: " + $Detail) -ForegroundColor Red; $script:failures += $Name }
}
function Invoke-Ki {
    param([string]$File, [string[]]$ArgList)
    $lines = @(& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $File @ArgList 2>&1 | ForEach-Object { "$_" })
    $rc = $LASTEXITCODE
    $final = $null
    $start = -1
    # итоговый JSON начинается с '{' без отступа; вложенные объекты ConvertTo-Json indentation
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ("$($lines[$i])" -match '^\{\r?$') { $start = $i; break }
    }
    if ($start -ge 0) {
        $tail = @($lines[$start..($lines.Count - 1)])
        try { $final = ($tail -join [Environment]::NewLine) | ConvertFrom-Json } catch { }
    }
    return [pscustomobject]@{ rc = $rc; lines = $lines; json = $final }
}

Write-Host "текущий контракт: $root" Cyan

# 1. неизвестный параметр
$r = Invoke-Ki $entry @('-Bogus','1','-Json')
Check-Ok ($r.rc -eq 4 -and $r.json -and $r.json.code -eq 4) 'unknown flag => code 4' ("rc=" + $r.rc + " out=" + ($r.lines -join ' '))

# 2. capabilities == docs/flags.json
$r1 = Invoke-Ki $entry @('-Check','capabilities','-Json')
$r2 = Invoke-Ki $inner @('-Check','capabilities','-Json')
$reg = Get-Content -LiteralPath (Join-Path $root 'docs\flags.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$namesReg = @($reg.flags | ForEach-Object { $_.name }) -join ','
$namesOut = @($r1.json.capabilities.flags | ForEach-Object { $_.name }) -join ','
Check-Ok ($r1.rc -eq 0 -and $namesReg -eq $namesOut) 'capabilities == docs/flags.json' ("reg=$namesReg out=$namesOut")
Check-Ok (($r1.json | ConvertTo-Json -Depth 8) -eq ($r2.json | ConvertTo-Json -Depth 8)) 'install.ps1 == all.ps1 output'

# 2b. bootstrap.ps1 самодостаточен: его реестр ключей обязан совпадать с docs/flags.json
$bootText = [IO.File]::ReadAllText((Join-Path $root 'bootstrap.ps1'))
$bootFlags = @()
foreach ($var in @('switchNames', 'valueNames')) {
    $m = [regex]::Match($bootText, ('\$' + $var + "\s*=\s*@\(([^)]*)\)"))
    if ($m.Success) {
        foreach ($q in [regex]::Matches($m.Groups[1].Value, "'([^']+)'")) { $bootFlags += $q.Groups[1].Value }
    }
}
$bootJoined = (($bootFlags | Sort-Object -Unique) -join ',')
$regJoined = (($namesReg -split ',') | Sort-Object -Unique) -join ','
Check-Ok ($bootJoined -eq $regJoined) 'bootstrap flags == docs/flags.json' ("bootstrap=$bootJoined registry=$regJoined")

# 3. -Check не пишет файлы
$tmp = Join-Path $env:TEMP ('ki-contract-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
$before = @(Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName + '|' + $_.Length })
$r = Invoke-Ki $entry @('-Check','inventory','-Json','-ArtifactDir',$tmp)
$after = @(Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName + '|' + $_.Length })
Check-Ok (-not (Get-ChildItem -LiteralPath $tmp -Force | Where-Object { $_.Name -notlike 'ki-*' }) -and ($before -join "`n") -eq ($after -join "`n")) 'check modes are read-only' ('artifact dir: ' + ((Get-ChildItem $tmp -Force | Select-Object -ExpandProperty Name) -join ','))

# 4. -Check mcp объясняет причину
$r = Invoke-Ki $entry @('-Check','mcp','-Json')
Check-Ok ($r.rc -eq 2 -and "$($r.json.snippet.reason)" -match 'mcp-snippet' -and "$($r.json.hint)" -match 'RULE_ROOT|snippet|клиент') 'check mcp explains reason' ("rc=" + $r.rc + " " + $r.json.snippet.reason)

# 5. отчёт + NDJSON в файле
$art = Join-Path $tmp 'art'
$r = Invoke-Ki $entry @('-Steps','doctor','-Json','-ProgressJson','-ArtifactDir',$art)
$report = $null
try { $report = Get-Content -LiteralPath (Join-Path $art 'install-report.json') -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
$need = @('code','ok','arch','mode','mcp_registration','report_path','mcp_snippet_path','python_path','stanza_resources','steps','blockers','failures','next_action','sizes','timings','acceptance')
$missing = @($need | Where-Object { $null -eq $report.PSObject.Properties[$_] })
# Код 2 = doctor не нашёл python (BLOCK), код 3 = doctor отработал и вернул FAIL.
# Оба означают «не установлено», и оба обязаны дать полный отчёт — проверяем это.
Check-Ok (@(2, 3) -contains $r.json.code -and $missing.Count -eq 0 -and (Test-Path -LiteralPath (Join-Path $art 'install.log'))) 'report fields and artifacts' ("code=" + $r.json.code + " missing=" + ($missing -join ','))
$ndjson = @(Get-Content -LiteralPath (Join-Path $art 'progress.ndjson') -ErrorAction SilentlyContinue | Where-Object { $_.Trim() })
$parsed = 0
foreach ($line in $ndjson) { try { $null = $line | ConvertFrom-Json; $parsed++ } catch { } }
Check-Ok ($parsed -eq $ndjson.Count -and $parsed -gt 0) 'progress.ndjson parses line by line' ("$parsed/$($ndjson.Count)")
Check-Ok (@(Get-ChildItem -LiteralPath $art -Filter 'install-report-*.json').Count -ge 1) 'timestamped report saved'

# 6. Resume: готовый шаг -> SKIP
$seed = [ordered]@{ code = 0; steps = @([pscustomobject]@{ id='doctor'; status='OK'; seconds=1; detail='seed' }) }
[IO.File]::WriteAllText((Join-Path $art 'install-report.json'), ($seed | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))
$r = Invoke-Ki $entry @('-Steps','doctor','-Resume','-Json','-ArtifactDir',$art)
Check-Ok ($r.rc -eq 0 -and $r.json.steps[0].status -eq 'SKIP') 'Resume skips ready steps' ("rc=" + $r.rc + " status=" + $r.json.steps[0].status)

# 7. нормализация архитектуры
$env:_KI_SAVED_ARCH = $env:PROCESSOR_ARCHITECTURE
$env:_KI_SAVED_WOW = $env:PROCESSOR_ARCHITEW6432
. (Join-Path $root 'scripts\_env.ps1')
$env:PROCESSOR_ARCHITECTURE = 'x86'; $env:PROCESSOR_ARCHITEW6432 = 'AMD64'
$a1 = Get-MachineArch
$env:PROCESSOR_ARCHITECTURE = 'x86_64'; $env:PROCESSOR_ARCHITEW6432 = ''
$a2 = Get-MachineArch
$env:PROCESSOR_ARCHITECTURE = $env:_KI_SAVED_ARCH; $env:PROCESSOR_ARCHITEW6432 = $env:_KI_SAVED_WOW
Remove-Item Env:\_KI_SAVED_ARCH -ErrorAction SilentlyContinue; Remove-Item Env:\_KI_SAVED_WOW -ErrorAction SilentlyContinue
Check-Ok ($a1 -eq 'AMD64' -and $a2 -eq 'AMD64') 'arch normalization' ("$a1 / $a2")

# 8. файлы установки лежат в installer\, корневые entry-point остаются на месте
$needInstaller = @('УСТАНОВКА.md', 'requirements.txt', 'requirements.lock', 'bootstrap.ps1.sha256')
$missingInstaller = @($needInstaller | Where-Object { -not (Test-Path -LiteralPath (Join-Path $root ('installer\' + $_))) })
$rootLeftovers = @($needInstaller | Where-Object { Test-Path -LiteralPath (Join-Path $root $_) })
Check-Ok ($missingInstaller.Count -eq 0 -and $rootLeftovers.Count -eq 0 -and
          (Test-Path -LiteralPath (Join-Path $root 'install.ps1')) -and
          (Test-Path -LiteralPath (Join-Path $root 'bootstrap.ps1'))) 'installer layout' ("missing=$($missingInstaller -join ',') root=$($rootLeftovers -join ',')")

Write-Host "`nитого: $total проверок, ошибок $($failures.Count)" $(if ($failures.Count) { 'Red' } else { 'Green' })
if ($failures.Count) { exit 1 }
exit 0
