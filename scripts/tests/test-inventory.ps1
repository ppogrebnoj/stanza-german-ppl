#Requires -Version 5.1
<#
    test-inventory.ps1 — приёмка scripts/inventory.ps1 (Этап −1, §Г.5 плана).

        powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\test-inventory.ps1

    Что проверяет:
      1. dot-source определяет Get-Inventory; ответ {code,elapsed,items};
      2. структура: 19 фиксированных имён, need/status из списка контракта, 7 полей у каждой позиции;
      3. никаких ложных OK: у OK есть версия или путь; у MISSING пустые version/path;
         у MISSING/WRONG/BASE_ONLY/LOW/PARTIAL/UNKNOWN есть fix; fix — одна строка;
      4. code = 0/2/4 и согласован с позициями (2, если есть блокирующая required);
      5. FR-15: запуск с урезанным PATH ('C:\Windows\System32;C:\Windows') даёт те же статусы;
      6. -Json: вывод парсится ConvertFrom-Json, items.Count = 19, код процесса = code;
      7. -RequiredOnly: только required, code не меняется;
      8. -NoNetwork: сеть = NOTE с текстом «как проверить руками»;
      9. GH_TOKEN не утекает в вывод (маскируется github_pat_***, печатается только длина);
     10. -Log: файл создаётся и содержит таблицу;
     10б. dot-source (сценарий all.ps1): с сентинелом $global:KI_LIB_ONLY=$true файл молчит,
          а Get-Inventory -Quiet печатает РОВНО ОДНУ строку (код), без таблицы и JSON;
     10б2. -Quiet не ломает -Log (лог пишется, stdout чистый);
     10в. dot-source НЕ затирает переменные вызывающего ($Json/$NoNetwork/$Log);
     10г. -File -Json — ровно один JSON (без таблицы);
     11. независимый оракул по файлам (git/python/winget/MSVC): чего нет на диске — не может быть OK;
     12. повторный вызов даёт тот же результат (в скрипте не остаётся состояния);
     13. скорость: elapsed ≤ 8 с (жёсткая граница, ловит регресс в десятки секунд), > 3 с — предупреждение
         (медленная машина/загрузка: на этой VM даже старт powershell.exe ~5 с).

    Коды: 0 — все проверки прошли; 1 — есть FAIL.
#>
[CmdletBinding()]
param(
    [string]$InventoryPath = ""
)

$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch { }

if (-not $InventoryPath) {
    $InventoryPath = (Join-Path $PSScriptRoot "..\inventory.ps1")
}
$InventoryPath = [System.IO.Path]::GetFullPath($InventoryPath)

$script:Pass = 0
$script:Fail = 0
$script:Failed = New-Object System.Collections.Generic.List[string]

function Write-Ok([string]$Name, [string]$Detail) {
    $script:Pass++
    if ($Detail) { Write-Output ("PASS  {0}  —  {1}" -f $Name, $Detail) }
    else { Write-Output ("PASS  " + $Name) }
}
function Write-Bad([string]$Name, [string]$Detail) {
    $script:Fail++
    [void]$script:Failed.Add($Name)
    if ($Detail) { Write-Output ("FAIL  {0}  —  {1}" -f $Name, $Detail) }
    else { Write-Output ("FAIL  " + $Name) }
}
function Check([string]$Name, [bool]$Ok, [string]$Detail) {
    if ($Ok) { Write-Ok $Name $Detail } else { Write-Bad $Name $Detail }
}

$expectedNames = @(
    "shell", "rights", "python", "pip", "venv", "git", "gh", "GH_TOKEN", "winget", "msvc_vctools",
    "freespace_C", "freespace_Z", "project_disk", "network", "mcp_client", "project_venv",
    "stanza_cache", "hf_cache", "pip_cache"
)
$allowedStatus = @(
    "OK", "MISSING", "WRONG", "BASE_ONLY", "PARTIAL", "LOW", "UNKNOWN", "SLOW", "NOTE",
    "ADMIN", "USER", "set", "NOT_SET", "NOT_REQUIRED"
)
$blockingStatus = @("MISSING", "WRONG", "BASE_ONLY", "LOW", "PARTIAL", "UNKNOWN")

Write-Output "=== test-inventory: приёмка scripts/inventory.ps1 ==="
Write-Output ("инвентарь: " + $InventoryPath)
if (-not (Test-Path -LiteralPath $InventoryPath)) {
    Write-Bad "файл inventory.ps1 существует" $InventoryPath
    Write-Output ""
    Write-Output ("ИТОГО: PASS {0}, FAIL {1}" -f $script:Pass, $script:Fail)
    exit 1
}
Write-Ok "файл inventory.ps1 существует" $InventoryPath

# ------------------------------------------------------------------ dot-source

. $InventoryPath
$cmdFound = $null -ne (Get-Command Get-Inventory -ErrorAction SilentlyContinue)
Check "dot-source определяет Get-Inventory" $cmdFound ""

# Объект берём из отдельного процесса: dot-source + Get-Inventory -Json (в stdout только JSON).
function Invoke-InventoryJson {
    param([string[]]$CallArgs, [string]$Prefix = "")
    $argText = ""
    if ($CallArgs.Count -gt 0) { $argText = " " + ($CallArgs -join " ") }
    # -Json печатает JSON в stdout и возвращает объект: | Out-Null убирает табличный дубль
    $cmd = '$global:KI_LIB_ONLY = $true; . ' + "'" + $InventoryPath + "'" + '; Get-Inventory' + $argText + " -Json | Out-Null"
    $out = & powershell -NoProfile -ExecutionPolicy Bypass -Command $cmd
    $text = (@($out) -join "`n")
    $obj = $null
    try { $obj = ($text | ConvertFrom-Json) } catch { }
    return @{ obj = $obj; text = $text; rc = $LASTEXITCODE }
}

function Invoke-InventoryFile {
    param([string[]]$ChildArgs, [string]$Prefix = "")
    if ($Prefix) {
        $argText = ""
        if ($ChildArgs.Count -gt 0) { $argText = " " + ($ChildArgs -join " ") }
        # префикс нужен для FR-15 (урезанный PATH): выходим с кодом самого скрипта
        $cmd = $Prefix + " & '" + $InventoryPath + "'" + $argText + "; exit `$LASTEXITCODE"
        $out = & powershell -NoProfile -ExecutionPolicy Bypass -Command $cmd
    } else {
        $out = & powershell -NoProfile -ExecutionPolicy Bypass -File $InventoryPath $ChildArgs
    }
    return @{ text = (@($out) -join "`n"); rc = $LASTEXITCODE }
}

$run = Invoke-InventoryJson @("-NoNetwork")
Check "Get-Inventory -Json: вывод парсится ConvertFrom-Json" ($null -ne $run.obj) ("rc={0}" -f $run.rc)
if ($null -eq $run.obj) {
    Write-Output ""
    Write-Output ("ИТОГО: PASS {0}, FAIL {1} — провалились: {2}" -f $script:Pass, $script:Fail, ($script:Failed -join ", "))
    exit 1
}

$inv = $run.obj
$items = @($inv.items)

Check "ответ {code,elapsed,items}" (($null -ne $inv.code) -and ($null -ne $inv.elapsed) -and ($null -ne $inv.items)) ("code={0} elapsed={1} items={2}" -f $inv.code, $inv.elapsed, $items.Count)
Check "состав = 19 фиксированных позиций" ($items.Count -eq 19) ("получено {0}" -f $items.Count)

$names = @($items | ForEach-Object { $_.name })
$namesOk = ($names.Count -eq $expectedNames.Count)
if ($namesOk) { for ($i = 0; $i -lt $expectedNames.Count; $i++) { if ($names[$i] -ne $expectedNames[$i]) { $namesOk = $false } } }
Check "имена и порядок совпадают с контрактом" $namesOk ($names -join ", ")

$needOk = $true
foreach ($it in $items) { if (@("required", "optional") -notcontains $it.need) { $needOk = $false } }
Check "need только required|optional" $needOk ""

$statusOk = $true; $badStatus = @()
foreach ($it in $items) { if (@($allowedStatus) -notcontains $it.status) { $statusOk = $false; $badStatus += ($it.name + "=" + $it.status) } }
Check "статусы только из списка контракта" $statusOk ($badStatus -join ", ")

$fieldsOk = $true
foreach ($it in $items) {
    foreach ($f in @("name", "need", "status", "version", "path", "fix", "note")) {
        if (-not ($it.PSObject.Properties.Name -contains $f)) { $fieldsOk = $false }
    }
}
Check "у каждой позиции 7 полей (name..note)" $fieldsOk ""

# --- никаких ложных OK / пустых fix

$falseOk = @()
foreach ($it in $items) {
    if ($it.status -eq "OK" -and -not $it.version -and -not $it.path) { $falseOk += $it.name }
}
Check "нет ложных OK (у OK есть версия или путь)" ($falseOk.Count -eq 0) ($falseOk -join ", ")

$missingFilled = @()
foreach ($it in $items) {
    if ($it.status -eq "MISSING" -and ($it.version -or $it.path)) { $missingFilled += $it.name }
}
Check "у MISSING version и path пустые" ($missingFilled.Count -eq 0) ($missingFilled -join ", ")

$noFix = @()
foreach ($it in $items) {
    if (@($blockingStatus) -contains $it.status -and -not $it.fix) { $noFix += $it.name }
}
Check "у MISSING/WRONG/BASE_ONLY/LOW/PARTIAL/UNKNOWN есть fix" ($noFix.Count -eq 0) ($noFix -join ", ")

$multiFix = @()
foreach ($it in $items) { if ($it.fix -and "$($it.fix)" -match "[\r\n]") { $multiFix += $it.name } }
Check "fix — одна строка (одна команда)" ($multiFix.Count -eq 0) ($multiFix -join ", ")

$okWithFix = @()
foreach ($it in $items) {
    # подсказка на OK допустима: кэш есть, но «all.ps1 -Steps models» докупиит отсутствующие модели —
    # это не блокер; блокирующие позиции проверяются выше (у MISSING/WRONG/… fix обязан быть)
    if ($it.status -eq "OK" -and $it.fix -and @("stanza_cache", "hf_cache", "pip_cache", "project_venv") -notcontains $it.name) { $okWithFix += $it.name }
}
Check "у OK нет fix (подсказки кэшей — не блокер)" ($okWithFix.Count -eq 0) ($okWithFix -join ", ")

# --- code

Check "code из {0,2,4}" (@(0, 2, 4) -contains $inv.code) ("code={0}" -f $inv.code)
$blocking = @($items | Where-Object { $_.need -eq "required" -and @($blockingStatus) -contains $_.status })
$codeOk = $false
if ($blocking.Count -gt 0) { $codeOk = ($inv.code -eq 2) } else { $codeOk = ($inv.code -eq 0) }
Check "code согласован с блокирующими required" $codeOk ("блокирующих {0}: {1}" -f $blocking.Count, (@($blocking | ForEach-Object { $_.name }) -join ", "))

Check "скорость без сети: elapsed ≤ 8 с" ($inv.elapsed -le 8) ("elapsed={0} с" -f $inv.elapsed)
if ($inv.elapsed -gt 3) {
    Write-Output ("WARN  скорость: {0} с > 3 с (медленная машина или фоновая установка)" -f $inv.elapsed)
}

# --- повторный вызов (в скрипте не должно оставаться состояния)

$run2 = Invoke-InventoryJson @("-NoNetwork")
$same = $false
if ($null -ne $run2.obj) {
    $a = @(@($inv.items) | ForEach-Object { $_.name + "=" + $_.status })
    $b = @(@($run2.obj.items) | ForEach-Object { $_.name + "=" + $_.status })
    $same = (($a -join "|") -eq ($b -join "|"))
}
Check "повторный вызов даёт тот же результат" $same ""

# --- -RequiredOnly

$runReq = Invoke-InventoryJson @("-NoNetwork", "-RequiredOnly")
$reqItems = @()
if ($runReq.obj) { $reqItems = @($runReq.obj.items) }
$onlyReq = $true
foreach ($it in $reqItems) { if ($it.need -ne "required") { $onlyReq = $false } }
$reqCount = @($items | Where-Object { $_.need -eq "required" }).Count
Check "-RequiredOnly: только required" ($onlyReq -and $reqItems.Count -eq $reqCount) ("{0} из {1}" -f $reqItems.Count, $items.Count)
Check "-RequiredOnly не меняет code" ($runReq.obj -and $runReq.obj.code -eq $inv.code) ("code={0}" -f $runReq.obj.code)

# --- сеть

$net = @($items | Where-Object { $_.name -eq "network" })[0]
Check "-NoNetwork: сеть = NOTE с инструкцией" (($net.status -eq "NOTE") -and ("$($net.note)" -match "как проверить руками")) ("status={0}" -f $net.status)

# --- токен не утекает

$leak = $false
$tok = $env:GH_TOKEN
if (-not $tok) { $tok = [Environment]::GetEnvironmentVariable("GH_TOKEN", "User") }
if (-not $tok) { $tok = [Environment]::GetEnvironmentVariable("GH_TOKEN", "Machine") }
if ($tok) {
    $allText = @($items | ForEach-Object { "$($_.version) $($_.path) $($_.fix) $($_.note)" }) -join " "
    if ($allText -like ("*" + $tok + "*")) { $leak = $true }
    $tokItem = @($items | Where-Object { $_.name -eq "GH_TOKEN" })[0]
    Check "GH_TOKEN: статус set, значение не печатается" (($tokItem.status -eq "set") -and ("$($tokItem.version)" -like "github_pat_***") -and (-not $leak)) ("version={0}" -f $tokItem.version)
} else {
    $tokStatus = "" + (@($items | Where-Object { $_.name -eq "GH_TOKEN" })[0]).status
    Check "GH_TOKEN: токена нет — статус NOT_SET" ($tokStatus -eq "NOT_SET") "токен в окружении не задан"
}

# ------------------------------------------------------------------ независимый оракул (по файлам)

$gitOnDisk = (Test-Path -LiteralPath "C:\Program Files\Git\bin\git.exe") -or (Test-Path -LiteralPath "${env:ProgramFiles(x86)}\Git\bin\git.exe")
$gitItem = @($items | Where-Object { $_.name -eq "git" })[0]
if ($gitOnDisk) {
    Check "git есть на диске → статус не MISSING" ($gitItem.status -ne "MISSING") ("status={0} version={1}" -f $gitItem.status, $gitItem.version)
} else {
    Check "git нет на диске → статус MISSING" ($gitItem.status -eq "MISSING") ("status={0}" -f $gitItem.status)
}

$wingetOnDisk = Test-Path -LiteralPath "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe"
$wingetItem = @($items | Where-Object { $_.name -eq "winget" })[0]
if ($wingetOnDisk) {
    Check "winget есть на диске → статус не MISSING" ($wingetItem.status -ne "MISSING") ("status={0} version={1}" -f $wingetItem.status, $wingetItem.version)
} else {
    Check "winget нет на диске → статус не OK" ($wingetItem.status -ne "OK") ("status={0}" -f $wingetItem.status)
}

$pyOnDisk = (Test-Path -LiteralPath "$env:LOCALAPPDATA\Programs\Python\Python315\python.exe") -or (Test-Path -LiteralPath "C:\Program Files\Python315\python.exe")
$pyItem = @($items | Where-Object { $_.name -eq "python" })[0]
if ($pyOnDisk) {
    Check "python 3.15 есть на диске → статус не MISSING" ($pyItem.status -ne "MISSING") ("status={0} version={1}" -f $pyItem.status, $pyItem.version)
} else {
    Check "python 3.15 нет на диске → статус MISSING/WRONG" (@("MISSING", "WRONG") -contains $pyItem.status) ("status={0}" -f $pyItem.status)
}

$clOnDisk = $false
foreach ($r in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
    if (-not $r) { continue }
    if (Test-Path -Path (Join-Path $r "Microsoft Visual Studio\*\*\VC\Tools\MSVC\*\bin\Host*\*\cl.exe")) { $clOnDisk = $true }
}
$vsWhereOnDisk = Test-Path -LiteralPath "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
$msvcItem = @($items | Where-Object { $_.name -eq "msvc_vctools" })[0]
if ($clOnDisk) {
    Check "cl.exe есть на диске → msvc_vctools не MISSING" ($msvcItem.status -ne "MISSING") ("status={0} version={1}" -f $msvcItem.status, $msvcItem.version)
} else {
    Check "cl.exe нет на диске → msvc_vctools не OK" ($msvcItem.status -ne "OK") ("status={0} (vswhere: {1})" -f $msvcItem.status, $vsWhereOnDisk)
}

# ------------------------------------------------------------------ файл: -Json / FR-15 / -Log

$jsonRun = Invoke-InventoryFile @("-Json", "-NoNetwork")
$parsed = $null
try { $parsed = ($jsonRun.text | ConvertFrom-Json) } catch { }
Check "-Json: вывод парсится ConvertFrom-Json" ($null -ne $parsed) ("rc={0}" -f $jsonRun.rc)
Check "-Json: ровно один JSON, без таблицы" ((("$($jsonRun.text)").TrimStart().StartsWith("{")) -and ("$($jsonRun.text)" -notmatch "ИНВЕНТАРИЗАЦИЯ")) ("первый символ '{', таблицы нет")
if ($parsed) {
    Check "-Json: items.Count = 19" (@($parsed.items).Count -eq 19) ("{0}" -f @($parsed.items).Count)
    Check "-Json: code совпадает с dot-source" ($parsed.code -eq $inv.code) ("file code={0}, dot-source code={1}" -f $parsed.code, $inv.code)
    Check "-Json: есть elapsed" ($null -ne $parsed.elapsed) ("elapsed={0}" -f $parsed.elapsed)
    Check "-Json: код выхода процесса = code" ($jsonRun.rc -eq $parsed.code) ("rc={0}" -f $jsonRun.rc)
    $jsonOk = $true
    foreach ($it in $parsed.items) {
        foreach ($f in @("name", "need", "status", "version", "path", "fix", "note")) {
            if (-not ($it.PSObject.Properties.Name -contains $f)) { $jsonOk = $false }
        }
    }
    Check "-Json: у всех позиций 7 полей" $jsonOk ""
}

# FR-15: тот же результат из шелла с урезанным PATH
$restricted = (& powershell -NoProfile -Command "`$env:Path='C:\Windows\System32;C:\Windows'; `$env:Path") -join ""
Check "FR-15: урезанный PATH действительно урезан" ($restricted -eq "C:\Windows\System32;C:\Windows") ("PATH='" + $restricted + "'")

$normalRun = Invoke-InventoryFile @("-Json", "-NoNetwork")
$limitedRun = Invoke-InventoryFile @("-Json", "-NoNetwork") "`$env:Path='C:\Windows\System32;C:\Windows';"
$normalParsed = $null; $limitedParsed = $null
try { $normalParsed = ($normalRun.text | ConvertFrom-Json) } catch { }
try { $limitedParsed = ($limitedRun.text | ConvertFrom-Json) } catch { }
Check "FR-15: запуск с урезанным PATH парсится" ($null -ne $limitedParsed) ("rc={0}" -f $limitedRun.rc)
if ($normalParsed -and $limitedParsed) {
    $a2 = @($normalParsed.items | ForEach-Object { $_.name + "=" + $_.status })
    $b2 = @($limitedParsed.items | ForEach-Object { $_.name + "=" + $_.status })
    Check "FR-15: статусы совпадают с обычным PATH" (($a2 -join "|") -eq ($b2 -join "|")) ("{0} позиций" -f $b2.Count)
    Check "FR-15: code совпадает" ($normalParsed.code -eq $limitedParsed.code) ("code={0}" -f $limitedParsed.code)
}

# -Log
$logPath = Join-Path $env:TEMP ("inv-test-" + [guid]::NewGuid().ToString("N") + ".log")
$logRun = Invoke-InventoryFile @("-NoNetwork", "-Log", $logPath)
$logOk = (Test-Path -LiteralPath $logPath)
$logText = ""
if ($logOk) { $logText = [IO.File]::ReadAllText($logPath) }
Check "-Log: файл создан" $logOk $logPath
Check "-Log: в файле есть таблица и итог" (($logText -match "ИНВЕНТАРИЗАЦИЯ") -and ($logText -match "code")) ("{0} байт" -f $logText.Length)
if ($logOk) { Remove-Item -LiteralPath $logPath -Force -ErrorAction SilentlyContinue }

# ------------------------------------------------------------------ dot-source (сценарий all.ps1)

# Потребитель ставит сентинел, потом dot-source: в stdout должна быть РОВНО ОДНА строка
# результата, без таблицы (регрессия: таблица печаталась при dot-source).
$invQ = "'" + $InventoryPath + "'"

# A) сентинел + Get-Inventory -Quiet: ровно одна строка "2" (ни таблицы, ни JSON)
$dsCmd = '$global:KI_LIB_ONLY = $true; . ' + $invQ + '; (Get-Inventory -NoNetwork -Quiet).code'
$dsOut = @(& powershell -NoProfile -ExecutionPolicy Bypass -Command $dsCmd)
Check "dot-source + -Quiet: ровно одна строка" ($dsOut.Count -eq 1) ("строк: {0}: {1}" -f $dsOut.Count, ($dsOut -join " / "))
Check "dot-source + -Quiet: печатает только код" ((($dsOut -join "") -eq "$($inv.code)") -and (-not ("$($dsOut -join ' ')" -match "ИНВЕНТАРИЗАЦИЯ"))) ("вывод: {0}" -f ($dsOut -join " / "))

# B) то же без сентинела (guard InvocationName) — тоже одна строка
$dsCmdB = '. ' + $invQ + '; (Get-Inventory -NoNetwork -Quiet).code'
$dsOutB = @(& powershell -NoProfile -ExecutionPolicy Bypass -Command $dsCmdB)
Check "dot-source без сентинела + -Quiet: одна строка" ((($dsOutB -join "") -eq "$($inv.code)") -and ($dsOutB.Count -eq 1)) ("вывод: {0}" -f ($dsOutB -join " / "))

# C) -Quiet не ломает -Log: в stdout ничего, файл лога создан и непустой
$quietLog = Join-Path $env:TEMP ("inv-quiet-" + [guid]::NewGuid().ToString("N") + ".log")
$oldEnv = $env:KI_TEST_LOG
$env:KI_TEST_LOG = $quietLog
$dsCmdC = '$global:KI_LIB_ONLY = $true; . ' + $invQ + '; $null = Get-Inventory -NoNetwork -Quiet -Log $env:KI_TEST_LOG; Write-Output ''DONE'''
$dsOutC = @(& powershell -NoProfile -ExecutionPolicy Bypass -Command $dsCmdC)
$env:KI_TEST_LOG = $oldEnv
$quietLogOk = (Test-Path -LiteralPath $quietLog)
$quietLogText = ""
if ($quietLogOk) { $quietLogText = [IO.File]::ReadAllText($quietLog) }
Check "-Quiet + -Log: в stdout ничего лишнего" (($dsOutC -join "") -eq "DONE") ("вывод: {0}" -f ($dsOutC -join " / "))
Check "-Quiet + -Log: лог записан" (($quietLogOk) -and ($quietLogText -match "ИНВЕНТАРИЗАЦИЯ") -and ($quietLogText.Length -gt 100)) ("{0} байт" -f $quietLogText.Length)
if ($quietLogOk) { Remove-Item -LiteralPath $quietLog -Force -ErrorAction SilentlyContinue }

# D) -Quiet возвращает объект с 19 позициями
$dsCmdD = '$global:KI_LIB_ONLY = $true; . ' + $invQ + '; $i = Get-Inventory -NoNetwork -Quiet; Write-Output (''items='' + @($i.items).Count + '' code='' + $i.code)'
$dsOutD = @(& powershell -NoProfile -ExecutionPolicy Bypass -Command $dsCmdD)
$dsExpected = "items=19 code=" + $inv.code
Check "dot-source + -Quiet: items=19 code=N" ((($dsOutD -join "`n") -eq $dsExpected) -and ($dsOutD.Count -eq 1)) ("вывод: {0}" -f ($dsOutD -join " / "))

# dot-source НЕ должен затирать переменные вызывающего
# значения переменных вызывающего до и после dot-source должны совпасть
$varCmd = '$Json=$true; $NoNetwork=$true; $Log=''C:\caller.log''; $RequiredOnly=$false; $global:KI_LIB_ONLY=$true; . ' + "'" + $InventoryPath + "'" + '; Write-Output $Json; Write-Output $NoNetwork; Write-Output $Log; Write-Output $RequiredOnly'
$varOut = @(& powershell -NoProfile -ExecutionPolicy Bypass -Command $varCmd)
Check "dot-source не затирает переменные вызывающего" ((($varOut -join "|") -eq "True|True|C:\caller.log|False")) ("{0}" -f ($varOut -join " / "))

# ------------------------------------------------------------------ итог

Write-Output ""
Write-Output "--- статусы на этой машине ---"
foreach ($it in $items) {
    Write-Output ("  {0,-15} {1,-9} {2,-13} {3}" -f $it.name, $it.need, $it.status, [string]$it.version)
}
Write-Output ""
if ($script:Fail -eq 0) {
    Write-Output ("ИТОГО: PASS {0}, FAIL 0 — все проверки пройдены (код 0)" -f $script:Pass)
    exit 0
}
Write-Output ("ИТОГО: PASS {0}, FAIL {1} — провалились: {2}" -f $script:Pass, $script:Fail, ($script:Failed -join ", "))
exit 1







