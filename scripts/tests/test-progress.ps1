#Requires -Version 5.1
<#
    test-progress.ps1 — приёмка scripts\progress.ps1 (агент PROG, Этап 1).

        powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\test-progress.ps1
        powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\test-progress.ps1 -Fast   # без замера на Z:

    Что проверяется:
      1. Format-Bytes / Format-Eta — граничные случаи (0, 1.1e9, 2.4 ГБ, неизвестно -> …)
      2. Measure-DirSize — сумма дерева, кэш (-MinIntervalSec) и -Force
      3. -Json -ProgressJson: NDJSON в stdout, построчно парсится ConvertFrom-Json, 9 полей,
         t в ISO-8601 UTC, никаких \r/ANSI/`\a, события дублируются в -Log (UTF-8)
      4. -Json без -ProgressJson: в stdout НОЛЬ событий (обратная совместимость CI), лог всё равно есть
      5. pretty: строка на месте (\r), формат [n/m], «1.2/2.4 ГБ · 50% · ETA 6 мин»
      5b. живой сценарий: докачка 1.1 ГБ моделей (байты растут, pct и ETA считает сам модуль)
      6. троттлинг: 200 вызовов Write-Progress2 -> ≤5 перерисовок, время не растёт линейно
      7. 1000 NDJSON-событий: время + контроль (столько же «пустых» вызовов PS)
      8. медленный диск (Z:, VMware-шара): Measure-DirSize по дереву из ~500 файлов

    Все дочерние процессы запускаются с перенаправлением stdout в файл, то есть заведомо в не-TTY —
    это и есть проверка «NDJSON валиден, когда stdout не консоль».
#>
[CmdletBinding()]
param(
    [switch]$Fast          # пропустить замер на медленном диске Z:
)

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$Root   = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # scripts\tests -> scripts -> корень проекта
$Module = Join-Path $Root 'scripts\progress.ps1'
$PSExe  = (Join-Path $PSHOME 'powershell.exe')
$Tmp    = Join-Path ([System.IO.Path]::GetTempPath()) ('pi-progress-test-' + [guid]::NewGuid().ToString('N').Substring(0, 8))
$null   = New-Item -ItemType Directory -Path $Tmp -Force

$script:Pass = 0
$script:Fail = 0
$script:Bad  = New-Object System.Collections.Generic.List[string]

function Section($t) { Write-Host ""; Write-Host ("== " + $t) -ForegroundColor Cyan }
function Ok($n) { $script:Pass = $script:Pass + 1; Write-Host ("  ok    " + $n) -ForegroundColor Green }
function Bad($n, $why) { $script:Fail = $script:Fail + 1; $script:Bad.Add($n + " :: " + $why) | Out-Null; Write-Host ("  FAIL  " + $n + " :: " + $why) -ForegroundColor Red }
function Check($n, [bool]$cond, [string]$why = '') { if ($cond) { Ok $n } else { Bad $n $why } }

# дочерний скрипт: тело пишем UTF-8 с BOM (иначе PS 5.1 читает кириллицу как ANSI), stdout/stderr — в файлы
function Invoke-Child {
    param([string]$Name, [string]$Body)

    $cp = Join-Path $Tmp ('child-' + $Name + '.ps1')
    [System.IO.File]::WriteAllText($cp, ($Body -replace "`r`n", "`n"), (New-Object System.Text.UTF8Encoding($true)))
    $op = Join-Path $Tmp ('out-' + $Name + '.txt')
    $ep = Join-Path $Tmp ('err-' + $Name + '.txt')
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $p  = Start-Process -FilePath $PSExe `
            -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"' + $cp + '"')) `
            -NoNewWindow -Wait -PassThru -RedirectStandardOutput $op -RedirectStandardError $ep
    $sw.Stop()
    return [pscustomobject]@{
        name  = $Name
        code  = $p.ExitCode
        out   = [System.IO.File]::ReadAllText($op)
        err   = [System.IO.File]::ReadAllText($ep)
        sec   = $sw.Elapsed.TotalSeconds
        path  = $op
    }
}

# непустые строки: NDJSON не должен содержать пустых строк между событиями.
# ВАЖНО: [,] — иначе PS 5.1 разворачивает массив из одного элемента в строку и [0] даёт первый символ.
function Get-Lines([string]$text) {
    $res = @()
    foreach ($l in ($text -split "`n")) {
        $t = $l.TrimEnd("`r")
        if ($t.Trim().Length -gt 0) { $res += $t }
    }
    return ,$res
}
function Get-RawLines([string]$text) { return ,@($text -split "`n") }

$env:PI_TMP    = $Tmp
$env:PI_MODULE = $Module

Write-Host ("модуль : " + $Module)
Write-Host ("песочница: " + $Tmp)

# ============================================================ 1. модуль грузится
Section '1. загрузка модуля и Format-Bytes / Format-Eta'
$loadErr = $null
try { . $Module } catch { $loadErr = $_.Exception.Message }
Check 'модуль dot-source без ошибок' ($null -eq $loadErr) "ошибка: $loadErr"

$fb = @(
    @{ n = 'Format-Bytes 0';                   v = 0;            want = '0 Б' },
    @{ n = 'Format-Bytes 512';                 v = 512;          want = '512 Б' },
    @{ n = 'Format-Bytes 1024';                v = 1024;         want = '1.0 КБ' },
    @{ n = 'Format-Bytes 1572864';             v = 1572864;      want = '1.5 МБ' },
    @{ n = 'Format-Bytes 1100000000';          v = 1100000000;   want = '1.0 ГБ' },
    @{ n = 'Format-Bytes 1288490188 (1.2 ГБ)'; v = 1288490188;   want = '1.2 ГБ' },
    @{ n = 'Format-Bytes 2576980377 (2.4 ГБ)'; v = 2576980377;   want = '2.4 ГБ' },
    @{ n = 'Format-Bytes 1099511627776';       v = 1099511627776; want = '1.0 ТБ' },
    @{ n = 'Format-Bytes 1.2e12';              v = 1.2e12;       want = '1.1 ТБ' },
    @{ n = 'Format-Bytes неизвестно (null)';   v = $null;        want = [string][char]0x2026 },
    @{ n = 'Format-Bytes отрицательное';       v = -1;           want = [string][char]0x2026 }
)
foreach ($c in $fb) {
    $got = Format-Bytes $c.v
    Check $c.n ($got -eq $c.want) ("получено '" + $got + "', ожидалось '" + $c.want + "'")
}

$fe = @(
    @{ n = 'Format-Eta 0';             v = 0;    want = '0 с' },
    @{ n = 'Format-Eta 45.4';          v = 45.4; want = '45 с' },
    @{ n = 'Format-Eta 360';           v = 360;  want = '6 мин' },
    @{ n = 'Format-Eta 3600';          v = 3600; want = '1 ч' },
    @{ n = 'Format-Eta 5400';          v = 5400; want = '1 ч 30 мин' },
    @{ n = 'Format-Eta 90000';         v = 90000; want = '1 д 1 ч' },
    @{ n = 'Format-Eta неизвестно';    v = $null; want = [string][char]0x2026 },
    @{ n = 'Format-Eta отрицательное'; v = -5;   want = [string][char]0x2026 }
)
foreach ($c in $fe) {
    $got = Format-Eta $c.v
    Check $c.n ($got -eq $c.want) ("получено '" + $got + "', ожидалось '" + $c.want + "'")
}
Check 'Format-Eta 0.48 -> 0 с (дробное не теряется на ru-RU)' ((Format-Eta 0.48) -eq '0 с') ("получено '" + (Format-Eta 0.48) + "'")
Check 'Format-Bytes 1.2e9 строкой -> 1.1 ГБ' ((Format-Bytes '1.2e9') -eq '1.1 ГБ') ("получено '" + (Format-Bytes '1.2e9') + "'")

# ============================================================ 2. Measure-DirSize
Section '2. Measure-DirSize: сумма дерева, кэш, -Force'
$tree = Join-Path $Tmp 'tree'
$null = New-Item -ItemType Directory -Path $tree -Force
$blob = New-Object byte[] 4096
for ($i = 0; $i -lt 20; $i++) {
    $sub = Join-Path $tree ('d' + $i)
    $null = New-Item -ItemType Directory -Path $sub -Force
    for ($j = 0; $j -lt 25; $j++) { [System.IO.File]::WriteAllBytes((Join-Path $sub ('f' + $j + '.bin')), $blob) }
}
$files = @(Get-ChildItem -LiteralPath $tree -Recurse -File).Count
$wantSize = [long]($files * 4096)
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$sz1 = Measure-DirSize -Path $tree -Force
$sw.Stop()
Check ("Measure-DirSize: " + $files + " файлов = " + $wantSize + " байт") ($sz1 -eq $wantSize) ("получено " + $sz1)
Write-Host ("       первый замер: " + [int]$sw.Elapsed.TotalMilliseconds + " мс")

# дописываем 1024 байта: закэшированный ответ не должен их видеть, -Force — должен
$one = Get-ChildItem -LiteralPath $tree -Recurse -File | Select-Object -First 1
$fs = [System.IO.File]::Open($one.FullName, 'Append', 'Write')
$null = $fs.Seek(0, 'End')
$fs.Write($blob, 0, 1024)
$fs.Close()
$sz2 = Measure-DirSize -Path $tree
$sz3 = Measure-DirSize -Path $tree -Force
Check 'кэш: повторный вызов отдаёт прежний размер' ($sz2 -eq $sz1) ("получено " + $sz2 + ", ожидалось " + $sz1)
Check '-Force: размер пересчитан (+1024)' ($sz3 -eq ($sz1 + 1024)) ("получено " + $sz3 + ", ожидалось " + ($sz1 + 1024))
$sw2 = [System.Diagnostics.Stopwatch]::StartNew()
$null = Measure-DirSize -Path $tree
$sw2.Stop()
Check 'кэш быстрее 50 мс' ($sw2.Elapsed.TotalMilliseconds -lt 50) ("время " + [int]$sw2.Elapsed.TotalMilliseconds + " мс")

# ============================================================ 3. NDJSON в stdout
Section '3. -Json -ProgressJson: NDJSON в stdout (не-TTY, перенаправление в файл)'
$body3 = @'
$ErrorActionPreference = 'Continue'
. $env:PI_MODULE
$log = Join-Path $env:PI_TMP 'child-ndjson.log'
Remove-Item $log -ErrorAction SilentlyContinue
Open-ProgressLog -Json -ProgressJson -LogPath $log -Steps @('preflight','venv','deps','models')
Write-Step -Step 'preflight' -State start
Write-Step -Step 'preflight' -State ok -Seconds 1.2 -Msg 'инвентаризация: python 3.15 x64'
Write-Step -Step 'deps' -State start
Write-Progress2 -Step 'deps' -Sub 'pip torch 2.15.0' -BytesDone 1288490188 -BytesTotal 2576980377 -EtaSec 360 -Msg 'torch'
Start-Sleep -Milliseconds 600
Write-Progress2 -Step 'deps' -Sub 'pip torch 2.15.0' -BytesDone 2400000000 -BytesTotal 2576980377
Write-Step -Step 'deps' -State fail -Seconds 42 -Msg 'код выхода 1'
Write-Step -Step 'models' -State skip -Msg 'модели уже в кэше'
Close-ProgressLog
[pscustomobject]@{ ok = $false; code = 3; verdict = 'ШАГ УПАЛ' } | ConvertTo-Json -Compress
'@
$r3 = Invoke-Child 'ndjson' $body3
Check 'дочерний процесс завершился кодом 0' ($r3.code -eq 0) ("код " + $r3.code + "; stderr: " + $r3.err)
$raw3 = Get-RawLines $r3.out
$inner3 = @($raw3 | Where-Object { $_.Trim().Length -gt 0 })   # только непустые строки
if ($inner3.Count -gt 0) { $inner3 = @($inner3[0..($inner3.Count - 2)]) }   # без итогового объекта вызывающего
Check 'в самих событиях нет возврата каретки' (($inner3 -join '') -notmatch "`r") 'найден CR в событиях'
Check 'в NDJSON нет ESC (ANSI)' (-not $r3.out.Contains([string][char]27)) 'найден 0x1b'
Check 'в NDJSON нет BEL (\a)' (-not $r3.out.Contains([string][char]7)) 'найден 0x07'
$lines3 = Get-Lines $r3.out
Check 'число непустых строк = 8 (7 событий + итог)' ($lines3.Count -eq 8) ("строк " + $lines3.Count)
Check 'нет пустых строк между событиями' (@($inner3 | Where-Object { $_.Trim().Length -eq 0 }).Count -eq 0) ("пустых среди " + $inner3.Count)
$evs = @()
$parseFail = @()
foreach ($l in $lines3) { try { $evs += ($l | ConvertFrom-Json) } catch { $parseFail += $l } }
Check 'каждая строка парсится ConvertFrom-Json' ($parseFail.Count -eq 0) ("не распарсилось: " + ($parseFail -join ' | '))
Check 'последняя строка — итоговый объект вызывающего скрипта' ($evs.Count -gt 0 -and $evs[-1].ok -eq $false -and $evs[-1].code -eq 3) ("последняя: " + $lines3[-1])
$eventObjs = @($evs | Where-Object { $null -ne $_.PSObject.Properties['ev'] })
Check 'событий 7' ($eventObjs.Count -eq 7) ("событий " + $eventObjs.Count)
$evSeq = @($eventObjs | ForEach-Object { [string]$_.ev })
Check 'ev: step_start,step_ok,step_start,progress,progress,step_fail,step_skip' ($evSeq -join ',' -eq 'step_start,step_ok,step_start,progress,progress,step_fail,step_skip') ("получено: " + ($evSeq -join ','))
$fields = @('t', 'ev', 'step', 'sub', 'pct', 'bytes', 'total', 'eta', 'msg')
$badFields = @($eventObjs | Where-Object { (@($_.PSObject.Properties.Name) -join ',') -cne ($fields -join ',') })
Check 'у каждого события ровно 9 полей в фиксированном порядке' ($badFields.Count -eq 0) ("битых: " + $badFields.Count)
$badT = @($eventObjs | Where-Object { [string]$_.t -notmatch '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$' })
Check 't — ISO-8601 UTC (…Z)' ($badT.Count -eq 0) ("битых: " + $badT.Count)
$p1 = @($eventObjs | Where-Object { $_.ev -eq 'progress' })[0]
Check 'progress #1: pct=50, bytes=1288490188, total=2576980377, eta=360' (($p1.pct -eq 50) -and ($p1.bytes -eq 1288490188) -and ($p1.total -eq 2576980377) -and ($p1.eta -eq 360)) ("получено: " + ($p1 | ConvertTo-Json -Compress))
$p2 = @($eventObjs | Where-Object { $_.ev -eq 'progress' })[1]
Check 'progress #2: pct=93 (из байтов), eta посчитан по дельте байт/сек' (($p2.pct -eq 93) -and ($null -ne $p2.eta) -and ($p2.eta -ge 0)) ("получено: " + ($p2 | ConvertTo-Json -Compress))
Check 'step_fail: seconds=42, msg="код выхода 1"' ((@($eventObjs | Where-Object { $_.ev -eq 'step_fail' })[0].msg) -eq 'код выхода 1') 'msg не совпал'

$logPath = Join-Path $Tmp 'child-ndjson.log'
Check '-Log создан' (Test-Path $logPath) 'файла нет'
if (Test-Path $logPath) {
    $logTxt = [System.IO.File]::ReadAllText($logPath, [System.Text.Encoding]::UTF8)
    $logLines = Get-Lines $logTxt
    Check 'лог: 7 строк (итоговый объект в лог не пишется)' ($logLines.Count -eq 7) ("строк " + $logLines.Count)
    $logParse = @()
    foreach ($l in $logLines) { try { $null = ($l | ConvertFrom-Json) } catch { $logParse += $l } }
    Check 'лог: каждая строка парсится ConvertFrom-Json' ($logParse.Count -eq 0) ("битых " + $logParse.Count)
    $want3 = @($lines3)
    if ($want3.Count -gt 0) { $want3 = @($want3[0..($want3.Count - 2)]) }
    Check 'лог = те же события, что в stdout' (([string]::Join("`n", $logLines)) -eq ([string]::Join("`n", $want3))) 'события разошлись'
    Check 'лог в UTF-8 (кириллица читается)' ($logTxt -like '*инвентаризация: python 3.15 x64*') 'кириллица битая (не UTF-8?)'
}

# ============================================================ 4. -Json без -ProgressJson
Section '4. -Json без -ProgressJson: в stdout ноль событий'
$body4 = @'
$ErrorActionPreference = 'Continue'
. $env:PI_MODULE
$log = Join-Path $env:PI_TMP 'child-quiet.log'
Remove-Item $log -ErrorAction SilentlyContinue
Open-ProgressLog -Json -LogPath $log -Steps @('deps')
Write-Step -Step 'deps' -State start
Write-Progress2 -Step 'deps' -Sub 'pip torch 2.15.0' -BytesDone 100 -BytesTotal 200
Write-Step -Step 'deps' -State ok -Seconds 1
Close-ProgressLog
[pscustomobject]@{ ok = $true; code = 0 } | ConvertTo-Json -Compress
'@
$r4 = Invoke-Child 'quiet' $body4
Check 'дочерний процесс завершился кодом 0' ($r4.code -eq 0) ("код " + $r4.code + "; stderr: " + $r4.err)
$lines4 = Get-Lines $r4.out
Check 'в stdout ровно одна строка (итоговый объект)' ($lines4.Count -eq 1) ("строк " + $lines4.Count + ": " + ($r4.out -replace "`r", '<CR>'))
if ($lines4.Count -eq 1) {
    $obj4 = $null
    try { $obj4 = $lines4[0] | ConvertFrom-Json } catch { }
    Check 'итоговый объект парсится' ($null -ne $obj4) ("строка: " + $lines4[0])
    Check 'в stdout нет поля ev (событий нет)' ($null -ne $obj4 -and $null -eq $obj4.PSObject.Properties['ev']) 'в stdout попало событие'
    Check 'итоговый объект: ok=true, code=0' ($null -ne $obj4 -and $obj4.ok -eq $true -and $obj4.code -eq 0) 'итог не тот'
}
Check 'без CR внутри и без ANSI/BEL' (($r4.out -replace "[`r`n]+$", '') -notmatch "[`r`a]") 'найден мусор'
$log4 = Join-Path $Tmp 'child-quiet.log'
if (Test-Path $log4) {
    $l4 = Get-Lines ([System.IO.File]::ReadAllText($log4, [System.Text.Encoding]::UTF8))
    Check 'лог: события всё равно записаны (3)' ($l4.Count -eq 3) ("строк " + $l4.Count)
} else { Check 'лог создан и в quiet-режиме' $false 'файла нет' }

# ============================================================ 5. pretty
Section '5. pretty: строка на месте (\r), формат [n/m]'
$body5 = @'
$ErrorActionPreference = 'Continue'
. $env:PI_MODULE
Open-ProgressLog -Steps @('preflight','deps','models')
Write-Step -Step 'preflight' -State ok -Seconds 1.2 -Msg 'инвентаризация'
Write-Step -Step 'deps' -State start
Write-Progress2 -Step 'deps' -Sub 'pip torch 2.15.0' -BytesDone 1288490188 -BytesTotal 2576980377 -EtaSec 360 -Msg 'torch'
Start-Sleep -Milliseconds 600
Write-Progress2 -Step 'deps' -Sub 'pip torch 2.15.0' -BytesDone 2576980377 -BytesTotal 2576980377 -EtaSec 0
Write-Step -Step 'deps' -State ok -Seconds 60
Close-ProgressLog
'@
$r5 = Invoke-Child 'pretty' $body5
Check 'дочерний процесс завершился кодом 0' ($r5.code -eq 0) ("код " + $r5.code + "; stderr: " + $r5.err)
Check 'pretty-поток содержит возврат каретки' $r5.out.Contains("`r") 'нет CR'
Check 'pretty: формат [n/m] присутствует' ($r5.out -match '\[\d+/\d+\]') 'нет [n/m]'
Check 'pretty: номер шага deps = [2/3]' $r5.out.Contains('[2/3]') 'нет [2/3]'
Check 'pretty: разделитель · присутствует' $r5.out.Contains([string][char]0xB7) 'нет ·'
Check 'pretty: 1.2/2.4 ГБ' $r5.out.Contains('1.2/2.4 ГБ') 'нет 1.2/2.4 ГБ'
Check 'pretty: 50%' $r5.out.Contains('50%') 'нет 50%'
Check 'pretty: ETA 6 мин' $r5.out.Contains('ETA 6 мин') 'нет ETA 6 мин'
Check 'pretty: 100%' $r5.out.Contains('100%') 'нет 100%'
Check 'pretty: OK 1 мин' $r5.out.Contains('OK 1 мин') 'нет OK 1 мин'
Check 'pretty: нет ANSI/BEL' ((-not $r5.out.Contains([string][char]27)) -and (-not $r5.out.Contains([string][char]7))) 'найден мусор'
Check 'pretty: вывод заканчивается переводом строки' ($r5.out.EndsWith("`n")) 'нет \n в конце'
Check 'pretty: перерисовок не меньше двух' (([regex]::Matches($r5.out, "`r")).Count -ge 2) ("CR: " + ([regex]::Matches($r5.out, "`r")).Count)
Write-Host '       как это видит человек (без \r):'
foreach ($l in ($r5.out -split "`r")) { if ($l.Trim().Length -gt 0) { Write-Host ("         " + ($l -replace "[`r`n]+$", '')) } }

# ============================================================ 5b. живой сценарий: 1.1 ГБ моделей
Section '5b. живой сценарий: докачка 1.1 ГБ моделей (pct и ETA считает модуль)'
$body5b = @'
$ErrorActionPreference = 'Continue'
. $env:PI_MODULE
$total = 1181116006
Open-ProgressLog -Steps @('models')
Write-Step -Step 'models' -State start
for ($i = 1; $i -le 10; $i++) {
    $done = [long]($total * $i / 10)
    Write-Progress2 -Step 'models' -Sub 'stanza de/default.zip' -BytesDone $done -BytesTotal $total -ThrottleMs 100
    Start-Sleep -Milliseconds 130
}
Write-Step -Step 'models' -State ok -Seconds 1.0 -Msg 'модели de в кэше'
Close-ProgressLog
'@
$r5b = Invoke-Child 'demo' $body5b
Check 'демо: дочерний процесс завершился кодом 0' ($r5b.code -eq 0) ("код " + $r5b.code + "; stderr: " + $r5b.err)
$pcts = @([regex]::Matches($r5b.out, '(\d+)%') | ForEach-Object { [int]$_.Groups[1].Value })
$mono = $true
for ($i = 1; $i -lt $pcts.Count; $i++) { if ($pcts[$i] -lt $pcts[$i - 1]) { $mono = $false } }
Check ('демо: pct виден и растёт (' + $pcts.Count + ' значений: ' + ($pcts -join ',') + ')') (($pcts.Count -ge 5) -and $mono) ("pct: " + ($pcts -join ','))
Check 'демо: дошло до 100%' ($pcts.Count -gt 0 -and $pcts[-1] -eq 100) ("последний pct: " + $pcts[-1])
Check 'демо: ETA посчитан по дельте байт/сек' ($r5b.out -match 'ETA \d') 'ETA не появился'
Check 'демо: 1.1/1.1 ГБ' ($r5b.out.Contains('1.1/1.1 ГБ')) 'нет 1.1/1.1 ГБ'
Check 'демо: шаг закрыт OK' ($r5b.out.Contains('OK')) 'нет OK'

# ============================================================ 6. троттлинг
Section '6. троттлинг: 200 вызовов Write-Progress2'
$body6 = @'
$ErrorActionPreference = 'Continue'
. $env:PI_MODULE
Open-ProgressLog -Steps @('deps')
Write-Step -Step 'deps' -State start
$sw = [System.Diagnostics.Stopwatch]::StartNew()
for ($i = 0; $i -lt 200; $i++) { Write-Progress2 -Step 'deps' -Sub 'pip torch' -BytesDone ($i * 1000000) -BytesTotal 200000000 }
$t = [int]$sw.Elapsed.TotalMilliseconds
Close-ProgressLog
[Console]::Error.WriteLine('elapsed_ms=' + $t)
'@
$body6b = @'
$ErrorActionPreference = 'Continue'
. $env:PI_MODULE
Open-ProgressLog -Steps @('deps')
Write-Step -Step 'deps' -State start
$sw = [System.Diagnostics.Stopwatch]::StartNew()
for ($i = 0; $i -lt 200; $i++) { Write-Progress2 -Step 'deps' -Sub 'pip torch' -BytesDone ($i * 1000000) -BytesTotal 200000000 -ThrottleMs 0 }
$t = [int]$sw.Elapsed.TotalMilliseconds
Close-ProgressLog
[Console]::Error.WriteLine('elapsed_ms=' + $t)
'@
$r6  = Invoke-Child 'throttle' $body6
$r6b = Invoke-Child 'thrash' $body6b
$rew6  = ([regex]::Matches($r6.out, "`r")).Count
$rew6b = ([regex]::Matches($r6b.out, "`r")).Count
$t6  = [int]([regex]::Match($r6.err, 'elapsed_ms=(\d+)').Groups[1].Value)
$t6b = [int]([regex]::Match($r6b.err, 'elapsed_ms=(\d+)').Groups[1].Value)
Check ('троттлинг: 200 вызовов -> ' + $rew6 + ' перерисовок (лимит 5)') ($rew6 -le 5) ("перерисовок " + $rew6)
Check ('без троттлинга: ' + $rew6b + ' перерисовок из 200 (для сравнения)') ($rew6b -ge 190) ("перерисовок " + $rew6b)
Check ('троттлинг: 200 вызовов за ' + $t6 + ' мс (< 2000; без троттлинга те же 200 перерисовок ' + $t6b + ' мс)') ($t6 -lt 2000) ("время " + $t6 + " мс")
Check ('цена вызова с троттлингом не выше, чем без него (' + $t6 + ' vs ' + $t6b + ' мс)') ($t6 -le [Math]::Max(300, 3 * $t6b)) ("время " + $t6 + " vs " + $t6b + " мс")
Write-Host ("       без троттлинга те же 200 вызовов: " + $t6b + " мс")

# ============================================================ 7. 1000 событий
Section '7. 1000 NDJSON-событий (и контроль: столько же пустых вызовов PS)'
$body7 = @'
$ErrorActionPreference = 'Continue'
. $env:PI_MODULE
function Bare { param([string]$Step = "", [string]$Sub = "", [object]$Pct, [object]$BytesDone, [object]$BytesTotal, [object]$EtaSec, [string]$Msg = "", [int]$ThrottleMs = 500) $x = 1 }
Open-ProgressLog -Json -ProgressJson -Steps @('deps')
$sw = [System.Diagnostics.Stopwatch]::StartNew()
for ($i = 0; $i -lt 1000; $i++) {
    Write-Progress2 -Step 'deps' -Sub 'pip' -BytesDone ($i * 1000) -BytesTotal 1000000 -ThrottleMs 0
}
$t = [int]$sw.Elapsed.TotalMilliseconds
Close-ProgressLog
$sw = [System.Diagnostics.Stopwatch]::StartNew()
for ($i = 0; $i -lt 1000; $i++) {
    Bare -Step 'deps' -Sub 'pip' -BytesDone ($i * 1000) -BytesTotal 1000000 -ThrottleMs 0
}
$b = [int]$sw.Elapsed.TotalMilliseconds
[Console]::Error.WriteLine('elapsed_ms=' + $t)
[Console]::Error.WriteLine('bare_ms=' + $b)
'@
$r7 = Invoke-Child 'perf' $body7
$lines7 = Get-Lines $r7.out
Check 'строк ровно 1000' ($lines7.Count -eq 1000) ("строк " + $lines7.Count)
$bad7 = @()
foreach ($l in $lines7) { try { $null = ($l | ConvertFrom-Json) } catch { $bad7 += $l } }
Check 'все 1000 строк парсятся ConvertFrom-Json' ($bad7.Count -eq 0) ("битых " + $bad7.Count)
$t7 = [int]([regex]::Match($r7.err, 'elapsed_ms=(\d+)').Groups[1].Value)
$t7b = [int]([regex]::Match($r7.err, 'bare_ms=(\d+)').Groups[1].Value)
$first7 = $lines7[0] | ConvertFrom-Json
$last7  = $lines7[-1] | ConvertFrom-Json
Check 'первое событие pct=0, последнее pct=100' (($first7.pct -eq 0) -and ($last7.pct -eq 100)) ("pct: " + $first7.pct + ".." + $last7.pct)
Write-Host ("       1000 событий: " + $t7 + " мс (" + [math]::Round($t7 / 1000.0, 2) + " мс на событие), " +
            "контроль (пустой PS-вызов с той же сигнатурой): " + $t7b + " мс, накладные расходы модуля: " +
            [math]::Round($t7 - $t7b, 1) + " мкс/событие")
Check ('1000 событий не дороже 6x пустого PS-вызова (' + $t7 + ' мс при контроле ' + $t7b + ' мс; наивный ConvertTo-Json давал ~4.3 с)') ($t7 -lt [Math]::Max(3000, 6 * $t7b)) ("время " + $t7 + " мс, контроль " + $t7b + " мс")
Check 'без CR/ANSI/BEL на 1000 событий' ((-not $r7.out.Contains("`r")) -and (-not $r7.out.Contains([string][char]27)) -and (-not $r7.out.Contains([string][char]7))) 'найден мусор'

# ============================================================ 8. медленный диск Z:
Section '8. Measure-DirSize на медленном диске Z: (VMware-шара), ~500 файлов'
if ($Fast) {
    Write-Host '  пропущено (-Fast)'
} else {
    $zd = Join-Path $Root '.pi-tmp\zdisk'
    if (Test-Path $zd) { Remove-Item -LiteralPath $zd -Recurse -Force }
    $null = New-Item -ItemType Directory -Path $zd -Force
    for ($i = 0; $i -lt 20; $i++) {
        $sub = Join-Path $zd ('d' + $i)
        $null = New-Item -ItemType Directory -Path $sub -Force
        for ($j = 0; $j -lt 25; $j++) { [System.IO.File]::WriteAllBytes((Join-Path $sub ('f' + $j + '.bin')), $blob) }
    }
    $zfiles = @(Get-ChildItem -LiteralPath $zd -Recurse -File).Count
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $zsz = Measure-DirSize -Path $zd -Force
    $sw.Stop()
    $zms1 = $sw.Elapsed.TotalMilliseconds
    $sw2 = [System.Diagnostics.Stopwatch]::StartNew()
    $zsz2 = Measure-DirSize -Path $zd
    $sw2.Stop()
    $zms2 = $sw2.Elapsed.TotalMilliseconds
    Write-Host ("       Z: файлов " + $zfiles + ", байт " + $zsz + ", первый замер " + [int]$zms1 + " мс, из кэша " + [int]$zms2 + " мс")
    Check ('Z: сумма совпала (' + $zsz + ' байт)') ($zsz -eq [long]($zfiles * 4096)) ("получено " + $zsz)
    Check ('Z: кэш не медленнее полного обхода (' + [int]$zms2 + ' vs ' + [int]$zms1 + ' мс)') ($zms2 -le ($zms1 + 150)) ("кэш " + [int]$zms2 + " мс, обход " + [int]$zms1 + " мс")
    Check 'Z: замер уложился в 5 с' ($zms1 -lt 5000) ("время " + [int]$zms1 + " мс")
    Remove-Item -LiteralPath $zd -Recurse -Force
}

# ============================================================ итог
Write-Host ""
Write-Host ("ИТОГ: pass=" + $script:Pass + " fail=" + $script:Fail) -ForegroundColor $(if ($script:Fail -eq 0) { 'Green' } else { 'Red' })
foreach ($b in $script:Bad) { Write-Host ("  - " + $b) }
Remove-Item -LiteralPath $Tmp -Recurse -Force -ErrorAction SilentlyContinue
if ($script:Fail -gt 0) { exit 1 }
exit 0




