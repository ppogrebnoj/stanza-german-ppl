#Requires -Version 5.1
<#
    all.ps1 — установка проекта ОДНОЙ командой: инвентаризация среды + префлайт + venv +
    зависимости + модели + проверка MCP-клиента + doctor + итоговый отчёт. Работает
    неинтерактивно (никогда не спрашивает без -Yes), поэтому годится и для человека, и для агента.

        powershell -NoProfile -ExecutionPolicy Bypass -File scripts\all.ps1
        (то же самое короче: .\install.ps1)

        -CheckOnly     ничего не менять: инвентаризация + префлайт + что готово + doctor (soft)
        -DryRun        напечатать команды, которые будут выполнены
        -Json          машинный вывод (итоговый объект) вместо человеческого
        -ProgressJson  к -Json: потоковые NDJSON-события прогресса ДО итогового объекта
        -Inventory     напечатать инвентаризацию среды и продолжить (префлайт её делает сам)
        -InventoryOnly только инвентаризация: «чего не хватает → одна команда на каждое»
        -Steps         список шагов: venv,deps,models,mcp,doctor
        -Venv          ставить зависимости в .venv (ОПЦИЯ). По умолчанию — глобально в системный
                       Python 3.15 (doctor.py: «нет .venv — работа идёт на системном Python
                       (допустимо)»). Если .venv уже есть, шаг venv так и так его подхватит
                       (чтобы не ставить torch дважды) — см. -CheckOnly.
        -Zip           архив моделей локально (офлайн); по умолчанию ищем stanza-models-de-*.zip в корне
        -Python        явный путь к python.exe 3.15 (если py-лаунчер его не нашёл)
        -MinFreeGB     сколько ГБ просить на диске (по умолчанию 12: venv+torch, модели, Build Tools, кэш)
        -McpConfig     конфиг MCP-клиента; по умолчанию автопоиск (pi, LM Studio, Claude, Cursor, VS Code)
        -McpKey        секция конфига (по умолчанию mcpServers)
        -Log           путь лога (по умолчанию install.log в корне проекта)
        -InstallPython / -InstallGit / -InstallBuildTools   доустановка система софта (ВЫКЛЮЧЕНО по
                       умолчанию; требует -Yes в машино-режиме и подтверждения Y/n в человеческом)
        -Yes           подтвердить автоустановку и другие необратимые действия
        -Help          эта справка

    Инвентаризация среды (§Г плана, FR-13..FR-17): перед ЛЮБЫМ прогоном скрипт сам смотрит,
    что на машине ЕСТЬ НА САМОМ ДЕЛЕ (python, git, winget, MSVC, место, сеть, права, кэши), и
    для каждого MISSING/WRONG печатает готовую команду. Статусы: OK / MISSING / WRONG /
    BASE_ONLY / PARTIAL / LOW / UNKNOWN. «Нет в PATH» ≠ «не установлено»: PATH сбрасывается до
    Machine+User, дальше py-лаунчер, реестр, стандартные пути, vswhere, Get-AppxPackage.
    Ничего из доков и памяти сессии не является фактом — только замер.

    Порядок моделей: локальный архив stanza-models-de-*.zip рядом с .sha256 (офлайн, быстро) ->
    иначе официальная загрузка Stanford: stanza.download() тянет список ресурсов со
    raw.githubusercontent.com (stanza-resources) и файлы с huggingface.co (stanfordnlp/stanza-de).
    Сетевой шаг идёт с ретраями (по умолчанию 4 попытки, пауза 15 с): на этой машине
    raw.githubusercontent.com регулярно рвёт TLS (ConnectionResetError 10054). Своих архивов
    моделей в репозитории нет и не будет.

    Конфиг MCP-клиента создаёт человек: скрипт печатает готовый фрагмент с путями этой машины
    и проверяет, есть ли запись в конфиге; если её нет — код 5 (всё стоит, нужно ОДНО действие
    человека). Сам файл конфига установщик НЕ пишет никогда, даже по флагу.

    gh и токены — это доступ на ЗАПИСЬ репозитория (push), к установке отношения не имеют.
    Если токен задан (GH_TOKEN/GITHUB_TOKEN), gh сам его использует: лишним
    `gh auth login --with-token` скрипт его не дёргает. Печать токена исключена (github_pat_***).

    Коды выхода (контракт, см. УСТАНОВКА.md):
        0  ГОТОВО
        2  НУЖЕН ЧЕЛОВЕК: нет Python 3.15 x64 / MSVC / места / сети; в конфиге MCP нет записи (check-only)
        3  ШАГ УПАЛ: pip, распаковка/загрузка моделей, doctor (FAIL) — лечится повтором того же шага
        4  СЛОМАН ЗАПУСК: нет файлов скриптов, чужие ключи, не Windows
        5  ГОТОВО, НУЖНО ОДНО ДЕЙСТВИЕ ЧЕЛОВЕКА: положить запись в mcp.json + перезапустить клиент

    Лог: install.log в корне проекта (токены маскируются). Отчёт: install-report.txt / .json
    (шаг → секунды → факт, объёмы, свободное место до/после) — тоже в корне, в .gitignore.
#>
[CmdletBinding()]
param(
    [string]$Steps = "venv,deps,models,mcp,doctor",
    [string]$Zip = "",
    [string]$Python = "",
    [long]$MinFreeGB = 12,
    [string]$McpConfig = "",
    [string]$McpKey = "mcpServers",
    [int]$Retries = 4,
    [string]$Log = "",
    [string]$ProgressFile = "",     # внутренний: сюда пишет дочерний setup.ps1
    [switch]$Inventory,
    [switch]$InventoryOnly,
    [switch]$CheckOnly,
    [switch]$DryRun,
    [switch]$Json,
    [switch]$ProgressJson,
    [switch]$Yes,
    [switch]$InstallPython,
    [switch]$InstallGit,
    [switch]$InstallBuildTools,
    [switch]$Venv,
    [switch]$Help
)

$ErrorActionPreference = "Continue"   # не Stop: нативные команды (pip, gh, python) пишут в stderr
                                       # штатные предупреждения, и PowerShell превращает их в
                                       # NativeCommandError и обрывает шаг. Решение — только $LASTEXITCODE.
$Code_Ready, $Code_Human, $Code_Step, $Code_Broken, $Code_ReadyHuman = 0, 2, 3, 4, 5

# Глобально (в системный Python) — поведение по умолчанию; venv — опция (см. -Venv в справке).
# Если .venv уже создан (раньше ставили в него), используем его — иначе получилось бы две копии
# torch по 2.4 ГБ. Явный -Venv — создать/использовать venv; явного «-force global» нет:
# удалить .venv и запустить снова — самый понятный способ вернуться к глобальной установке.
$UseVenv = [bool]$Venv

try {
    # дети (doctor/setup/unpack) печатают UTF-8 — читать их тоже надо по-UTF-8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }
$env:PYTHONUTF8 = "1"

# FR-15: шелл pi/CI наследует PATH без %LOCALAPPDATA%\Microsoft\WindowsApps, и «нет в PATH»
# превращается в «не установлено». Сбрасываем PATH до Machine+User — так видны winget/python-алиасы.
try {
    $mp = [Environment]::GetEnvironmentVariable('Path', 'Machine')
    $up = [Environment]::GetEnvironmentVariable('Path', 'User')
    $env:Path = (@($mp, $up) | Where-Object { $_ }) -join ';'
} catch { }

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Log) { $Log = Join-Path $Root "install.log" }
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
$NetHosts = @("https://pypi.org", "https://api.github.com")
$StartedAt = Get-Date

# модули прогресса и инвентаризации (Этапы −1 и 1); без них запуск считается сломанным.
# progress.ps1 — чистая библиотека (param-блока нет): dot-source напрямую, её $script: состояние
# живёт в области all.ps1. inventory.ps1 — файл с param-блоком: при обычном dot-source он
# затирает $Json/$Log вызывающего (так работает dot-source в PS 5.1) и сам печатает таблицу
# (guard по $MyInvocation.InvocationName в PS 5.1 не срабатывает). Поэтому грузим его в
# изолированной области и переносим только функции; точка входа файла гасится сентинелом.
$global:KI_LIB_ONLY = $true

function Import-ModuleFunctionsGlobal([string]$path) {
    $before = @{}
    foreach ($n in (Get-ChildItem function:).Name) { $before[$n] = $true }
    $q = $path -replace "'", "''"
    $body = ". '$q'`nforeach (`$n in (Get-ChildItem function:).Name) { if (-not `$before.ContainsKey(`$n)) { `$d = (Get-Item ('function:' + `$n)).Definition; if (`$d) { Set-Item -Path ('function:global:' + `$n) -Value `$d } } }"
    & ([ScriptBlock]::Create($body))
}

$ModNeeded = @("inventory.ps1", "progress.ps1")
foreach ($m in $ModNeeded) {
    $mpath = Join-Path $PSScriptRoot $m
    if (-not (Test-Path $mpath)) {
        Write-Host ("СЛОМАН ЗАПУСК: нет scripts\{0} — обновите репозиторий" -f $m) -ForegroundColor Red
        exit $Code_Broken
    }
    if ($m -eq "inventory.ps1") { Import-ModuleFunctionsGlobal $mpath } else { . $mpath }
}
foreach ($fn in @("Get-Inventory", "Open-ProgressLog", "Write-Step", "Write-Progress2", "Close-ProgressLog", "Measure-DirSize", "Format-Bytes", "Format-Eta")) {
    if (-not (Test-Path "function:$fn")) {
        Write-Host ("СЛОМАН ЗАПУСК: модули не поднялись, нет функции {0}" -f $fn) -ForegroundColor Red
        exit $Code_Broken
    }
}

$logLines = New-Object System.Collections.Generic.List[string]
$plan = New-Object System.Collections.Generic.List[object]
$done = New-Object System.Collections.Generic.List[object]
$humanActions = New-Object System.Collections.Generic.List[object]
$freeGB = -1
$inv = $null
$invBlocking = 0
$py = $null
$gh = $null
$paths = $null
$depsOk = $false
$mcpSnippet = ""
$verdict = ""

function Get-FreeGB($path) {
    try {
        $d = New-Object System.IO.DriveInfo(($path.Substring(0, 1) + ":\").ToUpper())
        return [math]::Round($d.AvailableFreeSpace / 1GB, 1)
    } catch { return -1 }
}
function Get-DirMB($path) {
    if (-not (Test-Path $path)) { return 0 }
    $sum = 0
    try { $sum = (Get-ChildItem $path -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum } catch { }
    return [math]::Round($sum / 1MB, 0)
}

function Say($text, $color) { if (-not $Json) { if ($color) { Write-Host $text -ForegroundColor $color } else { Write-Host $text } } }
function Log($text) {
    # токен не должен попасть в лог ни при каких условиях
    $safe = [regex]::Replace("$text", '(gh_pat_|github_pat_)[A-Za-z0-9_]+', '$1***')
    $logLines.Add((Get-Date).ToString("HH:mm:ss") + " " + $safe)
}
function Add-Human($what, $how) {
    $humanActions.Add([ordered]@{ what = $what; how = $how }) | Out-Null
    Say ("  ЧЕЛОВЕК: {0}" -f $what) Yellow
    foreach ($l in ($how -split "`n")) { Say ("    " + $l) Yellow }
}
function Add-Step($id, $status, $sec, $detail, $hint) {
    $done.Add([ordered]@{ id = $id; status = $status; seconds = $sec; detail = "$detail"; hint = "$hint" }) | Out-Null
    Say ("  [{0,-4}] {1,-7} {2}" -f $status, $id, $detail)
    $st = @{ "OK" = "ok"; "SKIP" = "skip"; "FAIL" = "fail"; "BLOCK" = "fail"; "NOTE" = "note"; "plan" = "plan" }[$status]
    if (-not $st) { $st = "note" }
    try { Write-Step -Step $id -State $st -Seconds $sec -Msg ("$detail $hint".Trim()) } catch { }
}

# ------------------------------------------------------------------ окружение

function Find-Py315([string]$explicit) {
    if ($explicit) {
        if (-not (Test-Path $explicit)) { return $null }
        $v = & (Resolve-Path $explicit) -c "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null
        if ("$v".Trim() -eq "3.15") { return (Resolve-Path $explicit).Path }
        return $null
    }
    try {
        foreach ($line in (& py -0p 2>$null)) {
            if ($line -match '-V:3\.15' -and $line -match 'python\.exe') {
                $p = ($line -split '\s+')[-1].Trim()
                if (Test-Path $p) { return $p }
            }
        }
    } catch { }
    try {
        $p = (& python -c "import sys;print(sys.executable)" 2>$null)
        $p = "$p".Trim()
        if ($p -and (Test-Path $p)) {
            $v = & $p -c "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null
            if ("$v".Trim() -eq "3.15") { return $p }
        }
    } catch { }
    # стандартные пути установщика (per-user и machine) — py-лаунчер их не всегда видит сразу
    foreach ($p in @((Join-Path $env:LOCALAPPDATA "Programs\Python\Python315\python.exe"),
                     "C:\Program Files\Python315\python.exe",
                     "C:\Program Files\Python\Python315\python.exe")) {
        if (Test-Path $p) {
            $v = & $p -c "import sys;print('%d.%d'%sys.version_info[:2])" 2>$null
            if ("$v".Trim() -eq "3.15") { return (Resolve-Path $p).Path }
        }
    }
    return $null
}

function Get-EnvToken() {
    foreach ($n in @("GH_TOKEN", "GITHUB_TOKEN")) {
        foreach ($sc in @("Process", "User")) {
            $v = [Environment]::GetEnvironmentVariable($n, $sc)
            if ($v) { return @{ Name = $n; Scope = $sc; Value = "$v" } }
        }
    }
    return $null
}

function Test-Gh($py) {
    # Этап 4: при заданном токене gh использует его сам; вызывать `gh auth login --with-token`
    # вслепую — получать rc=1 «value of GH_TOKEN is being used for authentication» и печатать
    # ложную NOTE при живом gh. Поэтому: сначала auth status, токен только показываем.
    $ghCmd = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $ghCmd) { return @{ ok = $false; why = "no-gh" } }
    & gh auth status *> $null
    if ($LASTEXITCODE -eq 0) {
        $t = Get-EnvToken
        $src = $(if ($t) { "токен $($t.Name) ($($t.Scope))" } else { "keyring" })
        return @{ ok = $true; why = "gh авторизован ($src)" }
    }
    $t = Get-EnvToken
    if (-not $t) { return @{ ok = $false; why = "no-token" } }
    return @{ ok = $false; why = ("gh auth status не прошёл, токен {0} ({1}) len={2} — для push: gh auth login (УСТАНОВКА.md §1.2)" -f $t.Name, $t.Scope, $t.Value.Length) }
}

function Test-Net() {
    $bad = @()
    foreach ($u in $NetHosts) {
        try { $null = Invoke-WebRequest -Uri $u -Method Head -TimeoutSec 6 -UseBasicParsing } catch { $bad += $u }
    }
    return $bad
}

function Probe-Paths($py) {
    $code = @"
import sys, json
sys.path.insert(0, r'$Root\scripts')
import _paths as P
m = P.model_dir()
print(json.dumps({'cache': str(P.stanza_cache_dir()), 'model': str(m),
                  'depparse': (m / 'depparse').exists(), 'reqs': str(P.REQS)}))
"@
    $o = & $py -c $code 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $o) { return $null }
    try { return ("$o" | ConvertFrom-Json) } catch { return $null }
}

function Test-Deps($py) {
    # проверяем ИМЕННО тот интерпретатор, который будет использован:
    # в режиме venv — venv-питон (и venv должен существовать),
    # по умолчанию (глобально) — системный Python 3.15.
    if (-not $py) { return $false }
    if ($UseVenv -and -not (Test-Path $VenvPy)) { return $false }
    & $py -c "import stanza, torch, mcp, pyphen" *> $null
    return ($LASTEXITCODE -eq 0)
}

function Get-PyUse {
    # единственный источник правды «какой python работает»: venv-питон при -Venv,
    # иначе системный. Все шаги (deps, models, mcp-snippet, doctor) берут его.
    if ($UseVenv -and (Test-Path $VenvPy)) { return $VenvPy }
    return $py
}

function Find-McpConfig() {
    # Этап 4: клиенту может быть pi, LM Studio, Claude, Cursor, VS Code — ищем по наличию файла,
    # потом по существующей папке; если ничего нет — LM Studio (историческое поведение).
    $files = @((Join-Path $env:USERPROFILE ".pi\agent\mcp.json"),
               (Join-Path $env:USERPROFILE ".lmstudio\mcp.json"),
               (Join-Path $env:APPDATA "Claude\claude_desktop_config.json"),
               (Join-Path $env:USERPROFILE ".cursor\mcp.json"),
               (Join-Path $env:APPDATA "Code\User\mcp.json"))
    foreach ($p in $files) { if (Test-Path $p) { return $p } }
    foreach ($p in $files) { $d = Split-Path $p -Parent; if (Test-Path $d) { return $p } }
    return (Join-Path $env:USERPROFILE ".lmstudio\mcp.json")
}

function Show-Inventory($inv) {
    if (-not $inv) { return }
    Say ""
    Say "инвентаризация среды (только замер; доки и память сессии — не факт)" Cyan
    Say ("{0,-16} {1,-9} {2,-10} {3,-26} {4}" -f 'КОМПОНЕНТ', 'НУЖЕН', 'СТАТУС', 'ВЕРСИЯ', 'ГДЕ')
    foreach ($it in $inv.items) {
        Say ("{0,-16} {1,-9} {2,-10} {3,-26} {4}" -f $it.name, $it.need, $it.status, [string]$it.version, [string]$it.path)
        if ($it.fix) { Say ("      fix: {0}" -f $it.fix) }
        if ($it.note) { Say ("      note: {0}" -f $it.note) }
    }
    Say ("  позиций {0}, блокирующих {1}, время {2} с" -f @($inv.items).Count, $invBlocking, $inv.elapsed)
}

# инвентаризация вызывается ОДНОЙ обёрткой: если модуль умеет -Quiet (ничего не печатает) —
# работаем в процессе; если нет — снимаем инвентаризацию дочерним процессом с -Json, иначе
# таблица модуля попадёт в stdout и сломает и -Json, и -ProgressJson (проверено замером)
$script:invQuiet = $false
try { $script:invQuiet = [bool]((Get-Command Get-Inventory).Parameters.Keys -contains 'Quiet') } catch { }
function Invoke-Inventory([bool]$withNet) {
    if ($script:invQuiet) {
        if ($withNet) { return Get-Inventory -Quiet } else { return Get-Inventory -NoNetwork -Quiet }
    }
    $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'inventory.ps1'), '-Json')
    if (-not $withNet) { $a += '-NoNetwork' }
    $o = & powershell @a 2>&1
    try { return ("$($o | Out-String)" | ConvertFrom-Json) } catch { return $null }
}

function Get-InvItem($name) {
    if (-not $inv) { return $null }
    return ($inv.items | Where-Object { $_.name -eq $name } | Select-Object -First 1)
}

# ------------------------------------------------------------------ автоустановка (-Install* -Yes)

function Confirm-AutoInstall($what) {
    if ($DryRun -or $CheckOnly) { return $false }
    if ($Yes) { return $true }
    if ($Json) { return $false }     # в машино-режиме без -Yes ничего не ставим
    Write-Host ("поставить {0}? Это изменит систему. [y/N] " -f $what) -ForegroundColor Yellow
    $ans = Read-Host
    return ($ans -match '^(y|Y|д|Д|да|Да)')
}

function Run-Winget([string]$id, [string]$extra) {
    $a = @("install", "-e", "--id", $id, "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity")
    if ($extra) { $a += ($extra -split ' ') }
    for ($i = 1; $i -le 3; $i++) {
        Write-Host ("  > winget install -e --id {0} (попытка {1})" -f $id, $i)
        & winget @a *> $null
        $rc = $LASTEXITCODE
        Log("winget install $id попытка $i rc=$rc")
        if ($rc -eq 0) { return 0 }
        Start-Sleep -Seconds 10
    }
    return $rc
}

function Invoke-CurlTo([string]$url, [string]$dest) {
    & curl.exe -L --retry 3 --retry-delay 5 -o $dest $url *> $null
    return $LASTEXITCODE
}

function Invoke-AutoInstall([string]$what) {
    # все автоустановки — только по явному флагу и подтверждению; каждое действие в лог
    if ($DryRun) {
        Add-Step "auto_$what" "plan" 0 ("будет доустановлено: $what") ""
        return
    }
    if (-not (Confirm-AutoInstall $what)) {
        Add-Step "auto_$what" "BLOCK" 0 "автоустановка $what не подтверждена (нужен -Yes или ответ y)" "поставьте вручную командой из инвентаризации"
        return
    }
    $hasWinget = [bool](Get-Command winget -ErrorAction SilentlyContinue)
    Log("автоустановка: $what (winget=$hasWinget)")
    switch ($what) {
        "python" {
            if ($hasWinget) { $rc = Run-Winget "Python.Python.3.15" "" }
            else {
                $f = Join-Path $env:TEMP "py315.exe"
                $rc = Invoke-CurlTo "https://www.python.org/ftp/python/3.15.2/python-3.15.2-amd64.exe" $f
                if ($rc -eq 0) {
                    $p = Start-Process -FilePath $f -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0" -Wait -PassThru -NoNewWindow
                    $rc = $p.ExitCode
                }
            }
        }
        "git" {
            if ($hasWinget) { $rc = Run-Winget "Git.Git" "" }
            else {
                $f = Join-Path $env:TEMP "git.exe"
                $rc = Invoke-CurlTo "https://github.com/git-for-windows/git/releases/download/v2.56.1.windows.1/Git-2.56.1-64-bit.exe" $f
                if ($rc -eq 0) {
                    $p = Start-Process -FilePath $f -ArgumentList "/VERYSILENT /NORESTART" -Wait -PassThru -NoNewWindow
                    $rc = $p.ExitCode
                }
            }
        }
        "buildtools" {
            # base-пакетwinget даёт только MSBuild: компилятор добавляют отдельным шагом (см. план §А.4.1)
            $bt = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vs_buildtools.exe"
            if (-not (Test-Path $bt)) {
                $bt = Join-Path $env:TEMP "vs_buildtools.exe"
                $rc = Invoke-CurlTo "https://aka.ms/vs/18/stable/vs_buildtools.exe" $bt
                if ($rc -ne 0) { Add-Step "auto_buildtools" "FAIL" 0 "не скачался vs_buildtools.exe" "проверьте доступ к aka.ms; команда в инвентаризации"; return }
            }
            $p = Start-Process -FilePath $bt -ArgumentList "--quiet --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended" -Wait -PassThru -NoNewWindow
            $rc = $p.ExitCode
            $vi = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vs_installer.exe"
            if ($rc -ne 0 -and (Test-Path $vi)) {
                $p2 = Start-Process -FilePath $vi -ArgumentList "modify --channelId VisualStudio.18.Release --productId Microsoft.VisualStudio.Product.BuildTools --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --passive --norestart" -Wait -PassThru -NoNewWindow
                $rc = $p2.ExitCode     # у vs_installer.exe нет --wait: ждём процессом
            }
            $deadline = (Get-Date).AddMinutes(45)
            while ((Get-Date) -lt $deadline -and -not (Get-ChildItem "C:\Program Files (x86)\Microsoft Visual Studio\*\*\VC\Tools\MSVC" -Directory -ErrorAction SilentlyContinue)) {
                Write-Progress2 -Step "auto_buildtools" -Sub "ждём VC\Tools\MSVC" -Msg "install rc=$rc" -ThrottleMs 5000
                Start-Sleep -Seconds 10
            }
        }
    }
    try {
        $mp = [Environment]::GetEnvironmentVariable('Path', 'Machine')
        $up = [Environment]::GetEnvironmentVariable('Path', 'User')
        $env:Path = (@($mp, $up) | Where-Object { $_ }) -join ';'
    } catch { }
    if ($rc -eq 0) { Add-Step "auto_$what" "OK" 0 "доустановлено: $what (переснимаем инвентаризацию)" "" }
    else { Add-Step "auto_$what" "FAIL" $rc "winget/установщик вернул $rc" "поставьте вручную: команда из инвентаризации" }
}

# ------------------------------------------------------------------ потоковые дети

function New-TailState([string]$path) {
    return @{ path = $path; pos = 0; partial = ""; enc = (New-Object System.Text.UTF8Encoding $false) }
}
function Read-Appended($state) {
    # дочитывает новые байты растущего файла (PS 5.1, без FileShare-трюков с StreamReader)
    $out = @()
    if (-not (Test-Path $state.path)) { return $out }
    try {
        $fs = [IO.File]::Open($state.path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
        try {
            $len = $fs.Length - $state.pos
            if ($len -le 0) { return $out }
            $fs.Seek($state.pos, [IO.SeekOrigin]::Begin) | Out-Null
            $buf = New-Object byte[] ([int]$len)
            [void]$fs.Read($buf, 0, [int]$len)
            $state.pos += $len
            $text = $state.enc.GetString($buf)
            $all = $state.partial + $text
            $parts = $all -split "`r`n|`n"
            $state.partial = $parts[$parts.Count - 1]
            for ($i = 0; $i -lt $parts.Count - 1; $i++) { $out += $parts[$i] }
        } finally { $fs.Dispose() }
    } catch { }
    return $out
}

function Start-KiChild([string]$innerCmd, [string]$rcF) {
    # PS 5.1: у Start-Process -PassThru свойство ExitCode часто $null (без EnableRaisingEvents),
    # и молча «код выхода » превращает успех в код 3. Поэтому ребёнка запускаем через cmd-обёртку,
    # которая пишет ERRORLEVEL в файл (delayed expansion: !ERRORLEVEL! после команды).
    $w = Join-Path $env:TEMP ("ki-cmd-" + [guid]::NewGuid().ToString("N") + ".cmd")
    [IO.File]::WriteAllLines($w, @('@echo off', $innerCmd, ('echo !ERRORLEVEL!> "{0}"' -f $rcF)), (New-Object System.Text.ASCIIEncoding))
    $plan.Add($innerCmd) | Out-Null
    return Start-Process -FilePath "$env:SystemRoot\System32\cmd.exe" -ArgumentList ('/v:on /c "' + $w + '"') -NoNewWindow -PassThru
}

function Get-KiRc([string]$rcF) {
    for ($i = 0; $i -lt 40; $i++) {
        if (Test-Path $rcF) {
            $t = ""
            try { $t = ([IO.File]::ReadAllText($rcF)).Trim() } catch { }
            if ($t -match '^\d+$') { return [int]$t }
        }
        Start-Sleep -Milliseconds 250
    }
    return 1
}

function New-PyFile([string]$code) {
    # код python — в файл (UTF-8), а не в командную строку: кириллица и кавычки через cmd ломаются
    $f = Join-Path $env:TEMP ("ki-py-" + [guid]::NewGuid().ToString("N") + ".py")
    [IO.File]::WriteAllText($f, $code, (New-Object System.Text.UTF8Encoding $false))
    return $f
}

function Run-Cmd($exe, [string[]]$argv, $id, $hint, $execute) {
    $plan.Add("$exe " + ($argv -join " ")) | Out-Null
    if (-not $execute) {
        Say ("  (plan) {0} {1}" -f (Split-Path -Leaf $exe), ($argv -join " "))
        Add-Step $id "plan" 0 "будет выполнено: $($argv -join ' ')" $hint
        return 0
    }
    Say ("  > {0} {1}" -f (Split-Path -Leaf $exe), ($argv -join " "))
    $t0 = Get-Date
    Write-Step -Step $id -State "start" -Msg ($argv -join " ")
    # stderr нативной команды — не авария: pip печатает в него «WARNING: Retrying …» на временных
    # обрывах, и с EAP=Stop это превращалось в NativeCommandError и рвало шаг. Решает код выхода.
    $prevEA = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $lines = @(& $exe @argv 2>&1 | ForEach-Object { "$_" })
    $rc = $LASTEXITCODE
    $ErrorActionPreference = $prevEA
    try { [IO.File]::AppendAllText($Log, (($lines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding $false)) } catch { }
    if (-not $Json) { foreach ($l in $lines) { Write-Host "  | $l" } }
    $sec = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
    if ($rc -ne 0) { Add-Step $id "FAIL" $sec "код выхода $rc" $hint }
    else { Add-Step $id "OK" $sec "" $hint }
    return $rc
}

function Run-CmdRetry($exe, [string[]]$argv, $id, $hint, $tries) {
    # FR-5: сетевые шаги падают на первой же дырке (pip, TLS-reset); попытки с паузой, между
    # ними — событие прогресса, чтобы «немота» не выглядела зависанием
    $rc = 1
    for ($i = 1; $i -le [math]::Max(1, $tries); $i++) {
        if ($i -gt 1) {
            Write-Progress2 -Step $id -Sub ("повтор {0}/{1}" -f $i, $tries) -Msg "пауза 15 с после rc=$rc"
            Start-Sleep -Seconds 15
        }
        $rc = Run-Cmd $exe $argv ("{0}" -f $id) $hint $true
        if ($rc -eq 0) { return 0 }
        Log("$id попытка $i rc=$rc")
    }
    return $rc
}

function Run-SetupWithProgress([string[]]$setupArgs, $id, $hint) {
    # setup.ps1 пишет NDJSON-события в $ProgressFile; здесь — хвост файлов + живой прогресс venv
    $pf = if ($ProgressFile) { $ProgressFile } else { Join-Path $env:TEMP ("ki-setup-progress-" + [guid]::NewGuid().ToString("N") + ".ndjson") }
    $outF = Join-Path $env:TEMP ("ki-setup-out-" + [guid]::NewGuid().ToString("N") + ".log")
    $errF = Join-Path $env:TEMP ("ki-setup-err-" + [guid]::NewGuid().ToString("N") + ".log")
    foreach ($f in @($pf, $outF, $errF)) { try { [IO.File]::WriteAllText($f, "") } catch { } }
    $argsLine = ('-NoProfile -ExecutionPolicy Bypass -File "{0}" {1} -ProgressFile "{2}"' -f (Join-Path $PSScriptRoot "setup.ps1"), ($setupArgs -join " "), $pf)
    $rcF = Join-Path $env:TEMP ("ki-setup-rc-" + [guid]::NewGuid().ToString("N") + ".txt")
    $plan.Add("powershell $argsLine") | Out-Null
    Say ("  > setup.ps1 {0}" -f ($setupArgs -join " "))
    $t0 = Get-Date
    Write-Step -Step $id -State "start" -Msg ($setupArgs -join " ")
    $inner = ('powershell -NoProfile -ExecutionPolicy Bypass -File "{0}" {1} -ProgressFile "{2}" > "{3}" 2> "{4}"' -f (Join-Path $PSScriptRoot "setup.ps1"), ($setupArgs -join " "), $pf, $outF, $errF)
    $p = Start-KiChild $inner $rcF
    $tOut = New-TailState $outF; $tErr = New-TailState $errF; $tPf = New-TailState $pf
    # что показывать как «растёт»: в режиме venv — .venv; по умолчанию (глобально) — site-packages
    # системного Python, иначе прогресс стоял бы на нуле. Если не вышло определить — .venv (как было).
    $growDir = Join-Path $Root ".venv"
    $growLabel = "размер .venv (эталон 874 МБ)"
    $growTotal = 874 * 1MB
    if (-not $UseVenv) {
        $sp = ""
        try { $sp = (& $py -c "import site;print(site.getsitepackages()[0])" 2>$null | Select-Object -First 1) } catch { }
        if ($sp -and (Test-Path $sp)) { $growDir = "" + $sp; $growLabel = "site-packages (глобально)" }
    }
    while (-not $p.HasExited) {
        foreach ($l in (Read-Appended $tPf)) {
            if (-not $l.Trim()) { continue }
            try {
                $e = $l | ConvertFrom-Json
                $sub = [string]$e.sub; if (-not $sub) { $sub = [string]$e.step }
                $bd = -1.0; $bt = -1.0; $pc = -1.0; $et = -1.0
                if ($null -ne $e.bytes) { $bd = [double]$e.bytes }
                if ($null -ne $e.total -and [double]$e.total -gt 0) { $bt = [double]$e.total }
                if ($null -ne $e.pct) { $pc = [double]$e.pct }
                if ($null -ne $e.eta) { $et = [double]$e.eta }
                if ("$($e.ev)" -like 'step_*') { Write-Progress2 -Step $id -Sub ("setup {0}: {1}" -f $e.ev, $sub) -Pct $pc -BytesDone $bd -BytesTotal $bt -Msg ([string]$e.msg) -ThrottleMs 1000 }
                else { Write-Progress2 -Step $id -Sub $sub -Pct $pc -BytesDone $bd -BytesTotal $bt -EtaSec $et -Msg ([string]$e.msg) }
            } catch { Log("setup progress line не распарсилась: $l") }
        }
        foreach ($l in (Read-Appended $tOut)) { try { [IO.File]::AppendAllText($Log, $l + "`n", (New-Object System.Text.UTF8Encoding $false)) } catch { }; if (-not $Json) { Write-Host "  | $l" } }
        foreach ($l in (Read-Appended $tErr)) { try { [IO.File]::AppendAllText($Log, $l + "`n", (New-Object System.Text.UTF8Encoding $false)) } catch { } }
        # Measure-DirSize отдаёт БАЙТЫ (кэш 2 с) — их и передаём в Write-Progress2
        $grownBytes = Measure-DirSize -Path $growDir -MinIntervalSec 2
        Write-Progress2 -Step $id -Sub $growLabel -BytesDone ([double]$grownBytes) -BytesTotal ([double]$growTotal) -Msg $growLabel
        Start-Sleep -Milliseconds 800
    }
    foreach ($l in (Read-Appended $tPf)) {
        try {
            $e = $l | ConvertFrom-Json
            $sub = [string]$e.sub; if (-not $sub) { $sub = [string]$e.step }
            $bd = -1.0; $bt = -1.0; $pc = -1.0; $et = -1.0
            if ($null -ne $e.bytes) { $bd = [double]$e.bytes }
            if ($null -ne $e.total -and [double]$e.total -gt 0) { $bt = [double]$e.total }
            if ($null -ne $e.pct) { $pc = [double]$e.pct }
            if ($null -ne $e.eta) { $et = [double]$e.eta }
            Write-Progress2 -Step $id -Sub ("setup {0}: {1}" -f $e.ev, $sub) -Pct $pc -BytesDone $bd -BytesTotal $bt -EtaSec $et -Msg ([string]$e.msg)
        } catch { }
    }
    foreach ($l in (Read-Appended $tOut)) { try { [IO.File]::AppendAllText($Log, $l + "`n", (New-Object System.Text.UTF8Encoding $false)) } catch { }; if (-not $Json) { Write-Host "  | $l" } }
    foreach ($l in (Read-Appended $tErr)) { try { [IO.File]::AppendAllText($Log, $l + "`n", (New-Object System.Text.UTF8Encoding $false)) } catch { } }
    $rc = Get-KiRc $rcF
    $sec = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
    if ($rc -ne 0) { Add-Step $id "FAIL" $sec "код выхода $rc" $hint }
    else { Add-Step $id "OK" $sec "" $hint }
    return $rc
}

function Invoke-ModelsStep($id, $hint) {
    # загрузка моделей с ретраями и живым прогрессом по размеру кэшей (STANZA + HF)
    $code = "import stanza; stanza.download('de', verbose=False); print('модели de скачаны')"
    $stanzaCache = Join-Path $env:LOCALAPPDATA "StanfordNLP"
    $hfCache = Join-Path $env:USERPROFILE ".cache\huggingface"
    $totalEst = 1.62GB   # эталон прогона: 1.09 ГБ Stanza + 0.53 ГБ HF-кэш
    for ($i = 1; $i -le [math]::Max(1, $Retries); $i++) {
        if ($i -gt 1) {
            Write-Progress2 -Step $id -Sub ("повтор {0}/{1}" -f $i, $Retries) -Msg "пауза 15 с (TLS-reset raw.githubusercontent.com)"
            Start-Sleep -Seconds 15
        }
        $t0 = Get-Date
        Write-Progress2 -Step $id -Sub ("stanza.download('de') попытка {0}" -f $i) -BytesTotal $totalEst -Msg "модели de: stanza-resources + huggingface.co"
        $outF = Join-Path $env:TEMP ("ki-models-out-" + [guid]::NewGuid().ToString("N") + ".log")
        $errF = Join-Path $env:TEMP ("ki-models-err-" + [guid]::NewGuid().ToString("N") + ".log")
        $rcF = Join-Path $env:TEMP ("ki-models-rc-" + [guid]::NewGuid().ToString("N") + ".txt")
        $pyFile = New-PyFile "import stanza`nstanza.download('de', verbose=False)`nprint('MODELS_DOWNLOADED')`n"
        $pyFor = Get-PyUse
        $inner = ('"{0}" "{1}" > "{2}" 2> "{3}"' -f $pyFor, $pyFile, $outF, $errF)
        $p = Start-KiChild $inner $rcF
        $tOut = New-TailState $outF; $tErr = New-TailState $errF
        while (-not $p.HasExited) {
            $b1 = 0; $b2 = 0
            $b1 = Measure-DirSize -Path $stanzaCache -MinIntervalSec 2
            try { $b2 = Measure-DirSize -Path $hfCache -MinIntervalSec 2 } catch { }
            $bytes = $b1 + $b2
            Write-Progress2 -Step $id -Sub ("качаем: StanfordNLP + HF-кэш") -BytesDone $bytes -BytesTotal $totalEst -Msg ("попытка {0}" -f $i)
            foreach ($l in (Read-Appended $tOut)) { try { [IO.File]::AppendAllText($Log, $l + "`n", (New-Object System.Text.UTF8Encoding $false)) } catch { }; if (-not $Json) { Write-Host "  | $l" } }
            foreach ($l in (Read-Appended $tErr)) { try { [IO.File]::AppendAllText($Log, $l + "`n", (New-Object System.Text.UTF8Encoding $false)) } catch { }; if (-not $Json) { Write-Host "  | $l" } }
            Start-Sleep -Seconds 2
        }
        foreach ($l in (Read-Appended $tOut)) { try { [IO.File]::AppendAllText($Log, $l + "`n", (New-Object System.Text.UTF8Encoding $false)) } catch { } }
        foreach ($l in (Read-Appended $tErr)) { try { [IO.File]::AppendAllText($Log, $l + "`n", (New-Object System.Text.UTF8Encoding $false)) } catch { } }
        $rc = Get-KiRc $rcF
        $sec = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
        if ($rc -eq 0) { Add-Step $id "OK" $sec "stanza.download('de') с попытки $i" ""; return 0 }
        Log("$id попытка $i rc=$rc")
        Add-Step $id "FAIL" $sec ("попытка {0}/{1}: rc={2}" -f $i, $Retries, $rc) $hint
    }
    return 1
}

Say "all.ps1: $Root" Cyan
Say ("режим : " + $(if ($InventoryOnly) { "инвентаризация среды" } elseif ($CheckOnly) { "check-only (ничего не меняю)" } elseif ($DryRun) { "dry-run" } else { "установка" }))
Open-ProgressLog -Json:$Json -ProgressJson:$ProgressJson -LogPath $Log -Steps @($Steps -Split ',')
if ($Help) { Get-Help $MyInvocation.MyCommand.Path -Detailed | Out-String -Width 110 | ForEach-Object { Say $_ }; Close-ProgressLog; exit $Code_Ready }

$want = @($Steps -Split ',' | ForEach-Object { $_.Trim().ToLower() })
$known = @("venv", "deps", "models", "mcp", "doctor")
$willRun = (-not $CheckOnly) -and (-not $DryRun) -and (-not $InventoryOnly)
$needDeps = ($want -contains "deps") -and -not (Test-Deps (Get-PyUse))
$needModels = ($want -contains "models")
$netNeeded = $willRun -and (($want -contains "deps") -or ($want -contains "models"))

# ------------------------------------------------------------------ 0. инвентаризация + префлайт

$t0 = Get-Date
$blockers = @()
$badSteps = @($want | Where-Object { $_ -notin $known })
if ($badSteps) {
    Add-Step "preflight" "FAIL" 0 ("неизвестный шаг: " + ($badSteps -join ", ") + "; известно: " + ($known -join ", ")) "код 4: поправьте -Steps"
    if ($Json) { [pscustomobject]@{ ok = $false; code = $Code_Broken; verdict = "СЛОМАН ЗАПУСК"; steps = @([pscustomobject]@{ id = "preflight"; status = "FAIL"; seconds = 0; detail = "неизвестный шаг: $($badSteps -join ', ')"; hint = "поправьте -Steps" }) } | ConvertTo-Json -Depth 6 }
    Close-ProgressLog
    exit $Code_Broken
}
if ($Zip -and -not (Test-Path $Zip)) {
    Add-Step "preflight" "FAIL" 0 "нет файла -Zip $Zip" "код 4: укажите существующий архив моделей"
    if ($Json) { [pscustomobject]@{ ok = $false; code = $Code_Broken; verdict = "СЛОМАН ЗАПУСК"; steps = @([pscustomobject]@{ id = "preflight"; status = "FAIL"; seconds = 0; detail = "нет файла -Zip $Zip"; hint = "укажите существующий архив" }) } | ConvertTo-Json -Depth 6 }
    Close-ProgressLog
    exit $Code_Broken
}

# FR-17: префлайт ЛЮБОГО прогона начинается с замера среды; статус только из замера
$inv = Invoke-Inventory $netNeeded
$invBlocking = @($inv.items | Where-Object { $_.need -eq 'required' -and @('OK', 'NOTE', 'ADMIN', 'USER', 'set', 'NOT_REQUIRED', 'SLOW') -notcontains $_.status }).Count
if ($invQuiet -and ($Inventory -or $InventoryOnly -or -not $Json)) { Show-Inventory $inv }

if ($InventoryOnly) {
    $code = $(if ($invBlocking -gt 0) { $Code_Human } else { $Code_Ready })
    Say ""
    Say ("итог: " + $(if ($code -eq 0) { "среда полная" } else { "чего-то не хватает (см. fix выше)" }) + " (код $code)") $(if ($code -eq 0) { "Green" } else { "Red" })
    if ($Json) { [pscustomobject]@{ ok = ($code -eq 0); code = $code; verdict = "ИНВЕНТАРИЗАЦИЯ"; root = $Root; elapsed = $inv.elapsed; blocking = $invBlocking; items = @($inv.items) } | ConvertTo-Json -Depth 6 }
    Close-ProgressLog
    exit $code
}

# флаги автоустановки: доустановить и переснять инвентаризацию (только по явному флагу + подтверждению)
foreach ($flag in @(@{ on = $InstallPython; name = "python"; item = "python" },
                   @{ on = $InstallGit; name = "git"; item = "git" },
                   @{ on = $InstallBuildTools; name = "buildtools"; item = "msvc_vctools" })) {
    if (-not $flag.on) { continue }
    $it = Get-InvItem $flag.item
    if ($it -and $it.status -eq 'OK') { Add-Step "auto_$($flag.name)" "SKIP" 0 "$($flag.item) уже есть: $($it.version)" ""; continue }
    Invoke-AutoInstall $flag.name
    $inv = Invoke-Inventory $netNeeded
    $invBlocking = @($inv.items | Where-Object { $_.need -eq 'required' -and @('OK', 'NOTE', 'ADMIN', 'USER', 'set', 'NOT_REQUIRED', 'SLOW') -notcontains $_.status }).Count
    if ($invQuiet -and -not $Json) { Show-Inventory $inv }
}

foreach ($f in @("scripts\setup.ps1", "scripts\inventory.ps1", "scripts\progress.ps1", "scripts\unpack_models.py", "scripts\doctor.py",
                 "requirements.txt", "MCP-stanza-german\server.py", "MCP-stanza-german\mcp.json.example")) {
    if (-not (Test-Path (Join-Path $Root $f))) { Add-Step "preflight" "FAIL" 0 "нет $f" "клон неполный — обновите репозиторий" }
}
if ($env:OS -notlike "Windows*") { $blockers += "all.ps1 рассчитан на Windows (PowerShell 5.1+)" }

# правила «что блокирует, что только предупреждает» (FIX-поля — из инвентаризации)
$itPy = Get-InvItem "python"
$py = Find-Py315 $Python
if (-not $py) {
    $fix = $(if ($itPy -and $itPy.fix) { $itPy.fix } else { "winget install -e --id Python.Python.3.15; без winget — https://www.python.org/ftp/python/3.15.2/python-3.15.2-amd64.exe /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0" })
    $blockers += ("нет Python 3.15 x64 (статус замера: " + $(if ($itPy) { $itPy.status } else { "UNKNOWN" }) + "). Поставить: " + $fix + " | не даунгрейдить до 3.12/3.13/3.14; можно -InstallPython -Yes")
}
$itGit = Get-InvItem "git"
if ($itGit -and $itGit.status -eq 'MISSING') {
    if ($InventoryOnly) { $blockers += ("нет git. Поставить: " + $itGit.fix) }
    else { Add-Step "preflight" "NOTE" 0 "git не найден (для установки не нужен; нужен для клона, git-хука и push)" ("поставить: " + $itGit.fix + " | можно -InstallGit -Yes") }
}
$itMsvc = Get-InvItem "msvc_vctools"
if ($needDeps -and $itMsvc -and $itMsvc.status -ne 'OK') {
    $blockers += ("для шага deps нужен компилятор (pyyaml 6.0.3 собирается из sdist, cp315-колёс нет), статус MSVC: " + $itMsvc.status + ". Поставить: " + $itMsvc.fix + " | можно -InstallBuildTools -Yes")
} elseif ($itMsvc -and $itMsvc.status -ne 'OK') {
    Add-Step "preflight" "NOTE" 0 ("MSVC VCTools: " + $itMsvc.status + " (нужен только для сборки pyyaml из sdist на шаге deps)") $itMsvc.fix
}
$itShell = Get-InvItem "shell"
if ($itShell -and $itShell.status -ne 'OK') { Add-Step "preflight" "NOTE" 0 ("шелл/кодировка: " + $itShell.note) "нужен PowerShell 5.1 x64; для кириллицы chcp 65001" }
$itDisk = Get-InvItem "project_disk"
if ($itDisk -and $itDisk.status -eq 'SLOW') { Add-Step "preflight" "NOTE" 0 "проект на сетевой/VMware-шаре: установка и MCP-вызовы в 4–7 раз дольше" $itDisk.fix }
$itRights = Get-InvItem "rights"
if ($itRights -and $itRights.status -eq 'USER') { Add-Step "preflight" "NOTE" 0 "обычный пользователь: Build Tools и machine-wide установки требуют UAC (per-user Python/Git — нет)" $itRights.fix }

$freeGB = Get-FreeGB $Root
if ($freeGB -ge 0 -and $freeGB -lt $MinFreeGB) { $blockers += "на диске $freeGB ГБ, просим >= $MinFreeGB ГБ (venv+torch ~4, модели ~1.6, Build Tools 3–4, кэш)" }

$depsOk = Test-Deps (Get-PyUse)
if ($py) { $paths = Probe-Paths $py }
$gh = Test-Gh $py
if (-not $gh.ok) { Add-Step "preflight" "NOTE" 0 ("gh: $($gh.why) — для установки не нужен (репозиторий публичный)") "для push: gh auth login + gh auth setup-git (УСТАНОВКА.md §1.2)" }
if ($netNeeded) {
    $bad = Test-Net
    if ($bad) { $blockers += ("нет доступа к " + ($bad -join ", ") + " (порт 443, прокси: HTTPS_PROXY)") }
}

$itWinget = Get-InvItem "winget"
if ($itWinget -and $itWinget.status -eq 'MISSING') { Add-Step "preflight" "NOTE" 0 "winget нет (Магазин отсутствует) — проект ставится прямыми ссылками, flags -Install* используют их" $itWinget.fix }

if ($blockers.Count) {
    foreach ($b in $blockers) { Add-Step "preflight" "BLOCK" 0 $b "нужен человек: команда fix из инвентаризации" }
    $code = $Code_Human
} elseif ($done | Where-Object { $_.status -eq "FAIL" }) {
    $code = $Code_Broken
} else {
    $det = "python $py; диск $freeGB ГБ; gh: $($gh.why); пакеты: " + $(if ($depsOk) { "есть (" + $(if ($UseVenv) { ".venv" } else { "глобально" }) + ")" } else { "нет" }) + "; инвентаризация: блокирующих $invBlocking"
    if ($paths) { $det += "; модели: " + $(if ($paths.depparse) { "есть" } else { "нет" }) }
    Add-Step "preflight" "OK" ([math]::Round(((Get-Date) - $t0).TotalSeconds, 1)) $det ""
    $code = 0
}

# ------------------------------------------------------------------ шаги

if ($code -eq 0) {
    # 1+2. интерпретатор/venv и зависимости — силами setup.ps1 (свою логику не дублируем)
    if ($want -contains "venv" -or $want -contains "deps") {
        $sa = @()
        if ($Python) { $sa += @("-Python", "`"$Python`"") }
        if ($DryRun) { $sa += "-DryRun" }
        # doctor внутри setup.ps1 — лишняя тяжёлая работа на медленном диске (import torch с Z: —
        # минуты); финальный doctor делает all.ps1 своим шагом
        $sa += "-SkipDoctor"
        if ($UseVenv) { $sa += "-Venv" }   # без этого setup.ps1 ставит глобально (дефолт)
        if ($want -notcontains "deps" -or (Test-Deps (Get-PyUse))) { $sa += "-SkipDeps"; Add-Step "deps" "SKIP" 0 "пакеты уже стоят" "" }
        if ($DryRun -or $CheckOnly) {
            $plan.Add("powershell -File scripts\setup.ps1 " + ($sa -join " ")) | Out-Null
            Add-Step "setup" "plan" 0 "будет выполнено setup.ps1 $($sa -join ' ')" ""
        } else {
            $rc = Run-SetupWithProgress $sa "setup" "setup.ps1 упал: pip/сеть/нужен MSVC; повторите ту же команду (шаги идемпотентны, готовые дают SKIP)"
            if ($rc -ne 0) { $code = $Code_Step }
        }
    }

    # 3. модели: локальный архив -> официальная загрузка Stanford (stanza.download) с ретраями
    if ($code -eq 0 -and $want -contains "models") {
        $pyFor = Get-PyUse
        # FIX: $paths снимается префлайтом системным python, а scripts\_paths.py требует stanza —
        # до шага deps он null, и `haveModels` по незнанию считался $true → ложный «models SKIP»
        # (именно так в прогоне 18.11 и вышло). После deps снимаем пути ещё раз — тем же python.
        if (-not $paths -and $pyFor) { $paths = Probe-Paths $pyFor }
        $haveModels = $false
        if ($paths) { $haveModels = [bool]$paths.depparse }
        if ($haveModels -and -not $Zip) {
            Add-Step "models" "SKIP" 0 "модели de уже в кэше ($($paths.model))" ""
        } else {
            $local = if ($Zip) { $Zip } else { (Get-ChildItem (Join-Path $Root "stanza-models-de-*.zip") -ErrorAction SilentlyContinue | Select-Object -First 1).FullName }
            if ($local -and (Test-Path $local)) {
                $rc = Run-Cmd $pyFor @((Join-Path $Root "scripts\unpack_models.py"), "--zip", $local, "--check") "models" "распаковка не вышла на 52/52: проверьте .sha256 рядом с архивом" $willRun
            } elseif (-not $willRun) {
                $rc = 0
                Add-Step "models" "plan" 0 "локального архива нет — модели качает stanza.download (huggingface.co + stanza-resources)" ""
            } elseif (Test-Deps $pyFor) {
                $rc = Invoke-ModelsStep "models" "stanza.download не отдаёт модели: нужен raw.githubusercontent.com + huggingface.co; при 10054 повторите, или положите resources_1.15.0.json в кэш, или -Zip <архив>"
                if ($rc -ne 0 -and $code -eq 0) { $code = $Code_Step }
            } else {
                $rc = 1
                Add-Step "models" "BLOCK" 0 "нет локального архива моделей, а пакеты (stanza) ещё не установлены" "сначала шаг deps, затем модели: stanza.download('de') или unpack_models.py --zip <архив>"
            }
        }
    }

    # 4. конфиг MCP-клиента: его создаёт человек — мы печатаем готовый фрагмент и проверяем запись
    if ($code -eq 0 -and $want -contains "mcp") {
        $pyFor = Get-PyUse
        $cfgPath = if ($McpConfig) { $McpConfig } else { Find-McpConfig }
        $entry = [ordered]@{
            command = $pyFor
            args    = @((Join-Path $Root "MCP-stanza-german\server.py"))
            env     = [ordered]@{ RULE_ROOT = (Join-Path $Root "правило"); PYTHONUTF8 = "1" }
        }
        $mcpSnippet = [ordered]@{ mcpServers = [ordered]@{ "stanza-german" = $entry } } | ConvertTo-Json -Depth 5
        $found = $false; $srv = $null
        if (Test-Path $cfgPath) {
            try {
                $servers = (Get-Content -Raw -Encoding UTF8 $cfgPath | ConvertFrom-Json).$McpKey
                $srv = $servers.'stanza-german'
                $found = $null -ne $srv
            } catch { $found = $false }
        }
        Say "MCP-конфиг: $cfgPath (создаёт человек; установщик этот файл НЕ пишет; образец — MCP-stanza-german\mcp.json.example)"
        Say "вставь в секцию `"$McpKey`":"
        foreach ($l in ($mcpSnippet -split "`n")) { Say ("  " + $l) }
        $venvExists = Test-Path $VenvPy
        if (-not $UseVenv -and -not $venvExists) {
            # глобальный режим (по умолчанию): это нормально, а не «установка не сделана»
            Add-Step "mcp" "OK" 0 "snippet напечатан для глобального Python ($pyFor)" ""
        } elseif (-not $UseVenv -and $venvExists) {
            Add-Step "mcp" "NOTE" 0 "есть готовый .venv, но режим глобальный: command = $pyFor (глобальный python)" "чтобы сервер работал в .venv, запустите с -Venv (тогда command будет $VenvPy)"
        }
        if ($found) {
            # запись есть — но клиент её не запустит, если enabled:false или command — python без пакетов
            $on = $true
            if ($srv.PSObject.Properties['enabled'] -and $srv.enabled -is [bool]) { $on = $srv.enabled }
            $cmd = [string]$srv.command
            if (-not $on) {
                Add-Step "mcp" "BLOCK" 0 "в $cfgPath запись stanza-german есть, но enabled: false" "поставь ""enabled"": true (или убери поле) и перезапусти клиент — иначе сервер не стартует"
                Add-Human "MCP: запись отключена" ("поставь `"enabled`: true в $cfgPath и перезапусти клиент")
                $code = $Code_Human
            } elseif ($cmd -and -not (Test-Path $cmd)) {
                # команда в конфиге не существует. Это BLOCK только если зависимости уже стоят
                # (тогда клиент точно не стартует и виноват конфиг). Пока зависимости не
                # установлены — это NOTE: сначала установка, потом command.
                if (Test-Deps $pyFor) {
                    Add-Step "mcp" "BLOCK" 0 "command в конфиге не найден: $cmd" "правь command на $pyFor и перезапусти клиент"
                    Add-Human "MCP: command в конфиге несуществующий" ("command = $pyFor в $cfgPath, затем перезапуск клиента")
                    $code = $Code_Human
                } else {
                    Add-Step "mcp" "NOTE" 0 "command в конфиге = $cmd, на этой машине его нет" "зависимости ещё не стоят: после установки поставь command = $pyFor и перезапусти клиент"
                    Add-Step "mcp" "OK" 0 "запись stanza-german есть в $cfgPath" ""
                }
            } elseif ($cmd -and ($cmd -ne $pyFor)) {
                Add-Step "mcp" "NOTE" 0 "command в конфиге = $cmd (ожидался $pyFor)" "в этом python пакетов mcp/stanza может не быть: поставь command = $pyFor"
                Add-Step "mcp" "OK" 0 "запись stanza-german есть в $cfgPath" ""
            } else {
                Add-Step "mcp" "OK" 0 "запись stanza-german есть в $cfgPath (command $cmd)" ""
            }
        } else {
            Add-Step "mcp" "BLOCK" 0 "в $cfgPath записи stanza-german нет" "вставь напечатанный фрагмент (образец MCP-stanza-german\mcp.json.example) и перезапусти клиент"
            if ($willRun) {
                Add-Human "осталось ОДНО действие человека: MCP-конфиг" ("1) положи запись stanza-german в $cfgPath (фрагмент выше)`n2) перезапусти MCP-клиент`n3) проверь: $pyFor scripts\mcp_probe.py")
                if ($code -eq 0) { $code = $Code_ReadyHuman }
            } else {
                Add-Human "MCP: нет записи stanza-german" ("после установки положи фрагмент в $cfgPath и перезапусти клиент")
                if ($code -eq 0) { $code = $Code_Human }
            }
        }
    }

    # 5. doctor — финальная проверка (тяжёлую приёмку с F1 не запускаем: см. УСТАНОВКА.md).
    # Идёт и при коде 5: «осталось одно действие человека» не отменяет проверку окружения —
    # иначе установщик на чистом состоянии (mcp-конфига же нет) никогда не показал бы doctor.
    if (($code -eq 0 -or $code -eq $Code_ReadyHuman) -and $want -contains "doctor") {
        $pyFor = Get-PyUse
        $a = @((Join-Path $Root "scripts\doctor.py"))
        if ($CheckOnly) { $a += "--soft-models" }
        $rc = Run-Cmd $pyFor $a "doctor" "doctor нашёл FAIL: список и лечение — УСТАНОВКА.md (окружение: setup.ps1, модели: unpack_models.py)" (-not $DryRun)
        # подсказка «нашёл FAIL» печатается только когда шаг действительно упал: при code 5
        # doctor = OK, а фраза в строке шага путала бы («OK 1 мин · doctor нашёл FAIL»).
        # $done — это List[OrderedDictionary]: в PS 5.1 у него нет свойства hint — только ключ.
        if ($rc -eq 0 -and $done.Count -gt 0) { $done[$done.Count - 1]["hint"] = "окружение в порядке (doctor: 18 позиций — окружение, модели, данные, git)" }
        if ($rc -ne 0 -and $code -eq 0) { $code = $Code_Step }
    }
}

# ------------------------------------------------------------------ итог + отчёт

$verdict = @{ 0 = "ГОТОВО"; 2 = "НУЖЕН ЧЕЛОВЕК"; 3 = "ШАГ УПАЛ"; 4 = "СЛОМАН ЗАПУСК"; 5 = "ГОТОВО, НУЖНО ОДНО ДЕЙСТВИЕ ЧЕЛОВЕКА" }[$code]
$lastStep = ($done | Where-Object { $_.status -eq "FAIL" -or $_.status -eq "BLOCK" } | Select-Object -First 1)
Say ""
if ($code -eq $Code_ReadyHuman) {
    Say "ГОТОВО: установка завершена. Осталось ОДНО действие человека:" Yellow
    foreach ($a in $humanActions) { Say ("  • {0}" -f $a.what) Yellow; foreach ($l in ($a.how -split "`n")) { Say ("      " + $l) Yellow } }
}
Say ("итог: $verdict (код $code)" + $(if ($lastStep) { " — " + $lastStep.id + ": " + $lastStep.detail + "; " + $lastStep.hint } else { "" })) $(if ($code -eq 0 -or $code -eq 5) { "Green" } else { "Red" })
if (-not $CheckOnly -and -not $DryRun -and ($code -eq 0 -or $code -eq 5)) {
    Say "приёмка (F1 0.777 / 0.686, 52/45) отдельными командами — см. таблицу приёмки в УСТАНОВКА.md"
}
Say ("лог: $Log")

$totalSec = [math]::Round(((Get-Date) - $StartedAt).TotalSeconds, 1)
$freeAfter = Get-FreeGB $Root
$stanzaMB = Get-DirMB (Join-Path $env:LOCALAPPDATA "StanfordNLP")
$hfMB = Get-DirMB (Join-Path $env:USERPROFILE ".cache\huggingface")
$venvMB = Get-DirMB (Join-Path $Root ".venv")
$stepArr = @($done | ForEach-Object { [pscustomobject]@{ id = $_.id; status = $_.status; seconds = $_.seconds; detail = $_.detail; hint = $_.hint } })
# PS 5.1: ConvertTo-Json падает («Argument types do not match») на массиве OrderedDictionary —
# человеческие действия разворачиваем в pscustomobject
$humanArr = @($humanActions | ForEach-Object { [pscustomobject]@{ what = $_.what; how = $_.how } })
$report = [ordered]@{
    started = $StartedAt.ToString("yyyy-MM-dd HH:mm:ss"); finished = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    total_sec = $totalSec; code = $code; verdict = $verdict; root = $Root
    mode = $(if ($InventoryOnly) { "inventory" } elseif ($CheckOnly) { "check-only" } elseif ($DryRun) { "dry-run" } else { "install" })
    python = $py; free_gb_before = $freeGB; free_gb_after = $freeAfter
    install_mode = $(if ($UseVenv) { "venv" } else { "global" })
    venv_mb = $venvMB; stanza_cache_mb = $stanzaMB; hf_cache_mb = $hfMB
    inventory_blocking = $invBlocking; human_actions = $humanArr; steps = $stepArr
}
try {
    [IO.File]::WriteAllText((Join-Path $Root "install-report.json"), ($report | ConvertTo-Json -Depth 6), (New-Object System.Text.UTF8Encoding $false))
    $txt = New-Object System.Collections.Generic.List[string]
    $txt.Add("install-report: $Root  $($report.started) → $($report.finished)  всего $totalSec с  код $code  $verdict")
    $txt.Add(("{0,-12} {1,-7} {2,7} {3}" -f 'ШАГ', 'СТУС', 'СЕК', 'ДЕТАЛЬ'))
    foreach ($s in $stepArr) { $txt.Add(("{0,-12} {1,-7} {2,7} {3}" -f $s.id, $s.status, $s.seconds, ($s.detail + " " + $s.hint).Trim())) }
    $txt.Add(("место: до {0} ГБ → после {1} ГБ | {2} | StanfordNLP {3} МБ | HF-кэш {4} МБ" -f $freeGB, $freeAfter, $(if ($UseVenv) { ".venv " + $venvMB + " МБ" } else { "глобально в " + $py }), $stanzaMB, $hfMB))
    if ($humanActions.Count) { $txt.Add("действие человека:"); foreach ($a in $humanActions) { $txt.Add("  - " + $a.what + ": " + ($a.how -replace "`n", " / ")) } }
    [IO.File]::WriteAllText((Join-Path $Root "install-report.txt"), ($txt -join "`r`n"), (New-Object System.Text.UTF8Encoding $false))
    Say ("отчёт: install-report.txt / install-report.json")
} catch { Say "отчёт не записан (нет прав на запись в корне проекта)" }
Say ("готово за {0} мин (код {1})" -f [math]::Round($totalSec / 60, 1), $code)

if ($Json) {
    # PS 5.1 ломается на ConvertTo-Json у List[object] из OrderedDictionary — разворачиваем в pscustomobject
    [pscustomobject]@{
        ok = ($code -eq 0 -or $code -eq 5); code = $code; verdict = $verdict; root = $Root
        mode = $report.mode
        python = $py; freeGB = $freeGB; gh = $(if ($gh) { $gh.why }); mcp_snippet = $mcpSnippet
        install_mode = $(if ($UseVenv) { "venv" } else { "global" })
        total_sec = $totalSec; venv_mb = $venvMB; stanza_cache_mb = $stanzaMB; hf_cache_mb = $hfMB
        inventory_blocking = $invBlocking; human_actions = $humanArr
        steps = $stepArr; plan = [string[]]($plan | ForEach-Object { "$_" })
        inventory = @($inv.items)
    } | ConvertTo-Json -Depth 6
}
try { [IO.File]::AppendAllText($Log, (($logLines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding $false)) } catch { }
Close-ProgressLog
exit $code
