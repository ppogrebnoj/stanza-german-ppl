#Requires -Version 5.1
<#
    inventory.ps1 — инвентаризация среды stanza-german-ppl (Этап −1; FR-13..FR-17, §Г плана,
    раздел «scripts/inventory.ps1» CONTRACT.md).

    ТОЛЬКО ЧТЕНИЕ: ничего не устанавливает, не правит реестр, не создаёт файлов (кроме явного -Log).
    Первым делом пересобирает PATH = Machine + User — иначе из-под шелла агента/CI (pi, bash)
    не видно WindowsApps-алиасов winget/python, и «нет в PATH» читается как «не установлено» (FR-15).

    Файл (код выхода = code):
        powershell -NoProfile -ExecutionPolicy Bypass -File scripts\inventory.ps1 [-Json] [-NoNetwork] [-RequiredOnly] [-Log <path>]

    Dot-source:
        $global:KI_LIB_ONLY = $true          # ОБЯЗАТЕЛЬНО перед dot-source (см. ниже)
        . .\scripts\inventory.ps1
        $inv = Get-Inventory -NoNetwork          # { code, elapsed, items[] }; ПЕЧАТАЕТ НИЧЕГО
        item  = { name, need, status, version, path, fix, note }
        need  = required | optional
        status= OK MISSING WRONG BASE_ONLY PARTIAL LOW UNKNOWN SLOW NOTE ADMIN USER set NOT_SET NOT_REQUIRED
        fix   = одна готовая команда (MISSING/WRONG/BASE_ONLY/LOW); для UNKNOWN — как проверить руками
        version/path — пустые ($null), если компонента нет: «OK по умолчанию» запрещено.
        Get-Inventory -Quiet → не печатает ничего (библиотечный режим all.ps1/CI), объект возвращает;
        без -Quiet печатает таблицу (или JSON при -Json). -Log пишется в обоих случаях.

    Коды: 0 — всё требуемое на месте; 2 — нужен человек (не хватает требуемого или не смогли проверить);
          4 — сломан запуск самой инвентаризации (не Windows).

    19 позиций, имена и состав — CONTRACT.md + §Г.3 плана.

    Скорость: без сети ≤ 3 с (сетевой блок отдельный: HEAD, 5 с/хост, отключается -NoNetwork).
    Чтобы уложиться, python/pip/venv проверяются ОДНИМ запуском python (importlib.util.find_spec +
    версия pip из pip/__init__.py) — это то же, что `python -m pip --version` / `python -m venv --help`,
    но без трёх загрузок процесса; версия git/gh — из ресурсов файла; место на диске — через
    System.IO.DriveInfo (Get-PSDrive на сетевом диске стоит ~1.3 с).

    ВНИМАНИЕ (dot-source): у файла НЕТ param-блока (иначе dot-source затирает одноимённые
    переменные вызывающего — $Json/$NoNetwork/$Log). Потребитель ставит ПЕРЕД dot-source:
        $global:KI_LIB_ONLY = $true
    тогда файл только определяет функции (Get-Inventory и служебные) и ничего не печатает.
    Файл также понимает ключи -Json/-NoNetwork/-RequiredOnly/-Log, разбирая $args.
    Пример безопасного вызова из all.ps1:
        $global:KI_LIB_ONLY = $true; . .\scripts\inventory.ps1
        $inv = Get-Inventory -NoNetwork -Quiet        # молчит, возвращает {code,elapsed,items}
#>

# В живой консоли оставляем её родную кодовую страницу; при перенаправлении stdout (CI, агент,
# `> file.json`) пишем UTF-8 — иначе кириллица в файле/у агента ломается.
try {
    if ([Console]::IsOutputRedirected) { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) }
} catch { }

# ВАЖНО (dot-source): у файла НЕТ param-блока — dot-source с param-блоком затирает
# одноимённые переменные вызывающего ($Json/$NoNetwork/$Log; проверено на PS 5.1).
# Ключи файла разбираются вручную из $args (см. Invoke-InventoryCli в конце файла).
$script:KI_InvItems = New-Object System.Collections.Generic.List[object]

# ------------------------------------------------------------------ служебное

function Out-InvLine {
    param([string]$Text)
    [Console]::Out.WriteLine([string]$Text)
}

function Add-InvItem {
    param(
        [string]$Name = "",
        [string]$Need = "required",
        [string]$Status = "UNKNOWN",
        [string]$Version = "",
        [string]$Path = "",
        [string]$Fix = "",
        [string]$Note = ""
    )
    $v = $null; if ($Version -and "$Version".Trim()) { $v = "$Version".Trim() }
    $p = $null; if ($Path -and "$Path".Trim()) { $p = "$Path".Trim() }
    $f = $null; if ($Fix -and "$Fix".Trim()) { $f = "$Fix".Trim() }
    $n = $null; if ($Note -and "$Note".Trim()) { $n = "$Note".Trim() }
    $script:KI_InvItems.Add([pscustomobject]@{
        name = $Name; need = $Need; status = $Status
        version = $v; path = $p; fix = $f; note = $n
    }) | Out-Null
}

# Свободное место: DriveInfo на порядок быстрее Get-PSDrive (0.01 с против 1.3 с на сетевом диске).
function Get-InvFreeGB {
    param([string]$Drive)
    try {
        $di = [System.IO.DriveInfo]::new($Drive)
        if (-not $di.IsReady) { return $null }
        return [math]::Round(($di.AvailableFreeSpace / 1GB), 1)
    } catch { return $null }
}

# Размер каталога быстрым перечислением; $null = не смогли/не успели в бюджет (тогда статус UNKNOWN).
function Get-InvDirSizeMB {
    param([string]$Path, [int]$BudgetMs = 1500)
    if (-not $Path) { return $null }
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $sum = [long]0
    try {
        $di = [System.IO.DirectoryInfo]::new($Path)
        foreach ($fi in $di.EnumerateFiles("*", [System.IO.SearchOption]::AllDirectories)) {
            $sum += $fi.Length
            if ($sw.ElapsedMilliseconds -gt $BudgetMs) { return $null }
        }
    } catch { return $null }
    return [math]::Round(($sum / 1MB), 0)
}

# Один зонд python.exe: версия + разрядность + pip (с версией) + venv + ensurepip.
# Возвращает $null (файла нет), либо хеш:
#   ok=$true  ver='3.15.2 x64' major=3 minor=15 path=... pipFound=$bool pip='26.2.2'|'' venv=$bool ensurepip=$bool
#   ok=$false store=$true         — ms-store алиас из WindowsApps (запускать нельзя, откроет Store)
#   ok=$false broken=$true        — файл есть, но не отвечает как python
function Get-InvPyProbe {
    param([string]$Exe)
    if (-not $Exe) { return $null }
    if ($Exe -like "*WindowsApps*") { return @{ ok = $false; store = $true; path = $Exe } }
    if (-not (Test-Path -LiteralPath $Exe)) { return $null }

    $probe = "import sys,struct,importlib.util as u;" +
             "print('%d.%d.%d %s' % (sys.version_info[0],sys.version_info[1],sys.version_info[2],'x64' if struct.calcsize('P')==8 else 'x86'));" +
             "s=u.find_spec('pip');print('pip=' + ((s.origin or 'none') if s else 'none'));" +
             "print('venv=' + ('yes' if u.find_spec('venv') else 'no'));" +
             "print('ensurepip=' + ('yes' if u.find_spec('ensurepip') else 'no'))"
    $out = @()
    try { $out = @(& $Exe -c $probe 2>$null) } catch { $out = @() }
    $ver = ""; $major = 0; $minor = 0
    $pipFound = $false; $pip = ""; $pipUnknown = $false; $venv = $false; $ep = $false; $venvUnknown = $false
    if ($out.Count -ge 4) {
        $ver = "$($out[0])".Trim()
        if ($ver -match "^(\d+)\.(\d+)\.(\d+)\s+(x64|x86)$") { $major = [int]$matches[1]; $minor = [int]$matches[2] }
        else { $ver = "" }
        $ps = "$($out[1])".Trim()
        if ($ps -match "^pip=(.+)$") {
            $pipOrigin = $matches[1].Trim()
            if ($pipOrigin -and $pipOrigin -ne "none") {
                $pipFound = $true
                try {
                    $pipTxt = [IO.File]::ReadAllText($pipOrigin)
                    if ($pipTxt -match '__version__\s*=\s*["'']([^"'']+)["'']') { $pip = $matches[1] }
                } catch { }
                if (-not $pip) {
                    # запас: имя каталога pip-<версия>.dist-info рядом с пакетом
                    $sp = Split-Path -Parent $pipOrigin
                    $di = @(Get-ChildItem -LiteralPath $sp -Filter "pip-*.dist-info" -Directory -ErrorAction SilentlyContinue)
                    if ($di.Count -gt 0 -and $di[0].Name -match "pip-(\d+(?:\.\d+)+)") { $pip = $matches[1] }
                }
            }
        }
        $venv = ("$($out[2])".Trim() -eq "venv=yes")
        $ep = ("$($out[3])".Trim() -eq "ensurepip=yes")
    }
    if (-not $ver) {
        # откат: тот же python, но без importlib (на случай битого site-packages)
        $out2 = @()
        try { $out2 = @(& $Exe -c "import sys,struct;print('%d.%d.%d %s' % (sys.version_info[0],sys.version_info[1],sys.version_info[2],'x64' if struct.calcsize('P')==8 else 'x86'))" 2>$null) } catch { $out2 = @() }
        $ver = ("$($out2 -join ' ')").Trim()
        if ($ver -match "^(\d+)\.(\d+)\.(\d+)\s+(x64|x86)$") { $major = [int]$matches[1]; $minor = [int]$matches[2] }
        else { return @{ ok = $false; broken = $true; path = $Exe } }
        $pipUnknown = $true; $venvUnknown = $true   # проверить не смогли — статус UNKNOWN, не OK
    }
    return @{
        ok = $true; ver = $ver; major = $major; minor = $minor; path = $Exe
        pipFound = $pipFound; pip = $pip; pipUnknown = $pipUnknown
        venv = $venv; venvUnknown = $venvUnknown; ensurepip = $ep
    }
}

# Токен не печатаем: только тип (github_pat_***), длина и область.
function Format-InvToken {
    param([string]$Value)
    if (-not $Value) { return $null }
    $len = $Value.Length
    if ($Value -like "github_pat_*") { return "github_pat_*** len=$len" }
    if ($Value -like "ghp_*") { return "ghp_*** len=$len" }
    return "*** len=$len"
}

function Format-InvText {
    param($Inv, [bool]$RequiredOnly = $false)
    $L = New-Object System.Collections.Generic.List[string]
    $items = @($Inv.items)
    $req = @($items | Where-Object { $_.need -eq "required" })
    $blocking = @($items | Where-Object { $_.need -eq "required" -and @("MISSING","WRONG","BASE_ONLY","LOW","PARTIAL","UNKNOWN") -contains $_.status })
    $L.Add("")
    $L.Add(("=" * 110))
    $L.Add("ИНВЕНТАРИЗАЦИЯ СРЕДЫ stanza-german-ppl" + $(if ($RequiredOnly) { " (только required)" } else { "" }))
    $L.Add(("=" * 110))
    $L.Add(("{0,-15} {1,-9} {2,-13} {3,-22} {4}" -f "ИМЯ", "НУЖНО", "СТАТУС", "ВЕРСИЯ", "ПУТЬ"))
    $L.Add(("-" * 110))
    foreach ($it in $items) {
        $L.Add(("{0,-15} {1,-9} {2,-13} {3,-22} {4}" -f $it.name, $it.need, $it.status, [string]$it.version, [string]$it.path))
        if ($it.note) { $L.Add("    note: " + $it.note) }
        if ($it.fix) { $L.Add("    fix:  " + $it.fix) }
    }
    $L.Add(("-" * 110))
    $bl = @($blocking | ForEach-Object { $_.name })
    $L.Add(("итого: {0} позиций (required {1}), блокирующих {2}: {3}" -f $items.Count, $req.Count, $bl.Count, ($bl -join ", ")))
    $L.Add(("время {0} с, code {1}" -f $Inv.elapsed, $Inv.code) + $(if ($Inv.code -eq 0) { " — всё требуемое на месте" } else { " — нужен человек (2) или сломан запуск (4); подсказки: fix под каждой позицией" }))
    return $L
}

# ------------------------------------------------------------------ инвентаризация

function Get-Inventory {
    [CmdletBinding()]
    param(
        [switch]$Json,
        [switch]$NoNetwork,
        [switch]$RequiredOnly,
        [switch]$Quiet,
        [string]$Log = ""
    )

    $ErrorActionPreference = "Continue"        # нативные команды (py/git/gh/pip) штатно пишут в stderr
    $ProgressPreference = "SilentlyContinue"   # в PS 5.1 Invoke-WebRequest иначе рисует прогресс-бар
    $Code_Ready = 0; $Code_Human = 2; $Code_Broken = 4
    $sw = [System.Diagnostics.Stopwatch]::StartNew()

    # --- FR-15: PATH = Machine + User. Первым делом, иначе из-под шелла агента/CI (pi, bash)
    #     не видно WindowsApps-алиасов winget/python, и «нет в PATH» = «не установлено».
    $mp = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $up = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = (@($mp, $up) | Where-Object { $_ }) -join ";"

    if (-not $script:KI_InvItems) { $script:KI_InvItems = New-Object System.Collections.Generic.List[object] }
    $script:KI_InvItems.Clear()

    $root = ""
    try { if ($PSScriptRoot) { $root = Split-Path -Parent $PSScriptRoot } } catch { }
    if (-not $root) { $root = (Get-Location).Path }

    $osOk = ($env:OS -eq "Windows_NT")
    if (-not $osOk) {
        Add-InvItem "shell" "required" "UNKNOWN" "" "" "инвентаризация нужна на Windows: сейчас OS=$env:OS" "запустить в PowerShell 5.1 на Windows"
    }

    if ($osOk) {

        # ---------------------------------------------------------------- шелл / права
        $psVer = $PSVersionTable.PSVersion.ToString()
        $psBits = "x86"; try { if ([Environment]::Is64BitProcess) { $psBits = "x64" } } catch { }
        $osName = ""
        $osBuild = 0; $osDisp = ""
        try {
            $cv = Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion" -ErrorAction SilentlyContinue
            # ProductName в реестре остаётся «Windows 10 …» даже на Windows 11 (замер 19.11:
            # машина Windows 11 IoT Enterprise LTSC, ядро 26100, а ProductName = «Windows 10 IoT …»).
            # Правильное деление 10/11 — по номеру сборки (CurrentBuildNumber ≥ 22000 → Windows 11).
            if ($cv) {
                $raw = "" + $cv.ProductName
                $b = 0; try { $b = [int]"$($cv.CurrentBuildNumber)" } catch { }
                $ub = "" + $cv.UBR
                if ($b -ge 22000) { $raw = $raw -replace "^Windows 10", "Windows 11" }
                $osBuild = $b
                $osDisp = ("" + $cv.DisplayVersion).Trim()
                $raw = ("$raw $($cv.EditionID)").Trim()
                if ($osDisp) { $raw += " $osDisp" }
                if ($ub) { $raw += " build $b.$ub" } elseif ($b) { $raw += " build $b" }
                $osName = $raw
            }
        } catch { }
        if (-not $osName) { $osName = [System.Environment]::OSVersion.VersionString }
        $cp = 0; try { $cp = [Console]::OutputEncoding.CodePage } catch { }
        Add-InvItem "shell" "required" "OK" ("PS $psVer $psBits") "" "" ("OS $osName (codepage $cp); для кириллицы в консоли: chcp 65001")

        $isAdmin = $false
        try {
            $wid = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
            $isAdmin = $wid.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        } catch { }
        if ($isAdmin) {
            Add-InvItem "rights" "required" "ADMIN" "ADMIN" "" "" "machine-wide установки (Git, Build Tools) пройдут без UAC"
        } else {
            Add-InvItem "rights" "required" "USER" "USER" "" "Build Tools / Git machine-wide требуют UAC; per-user установки (Python, winget, gh) — без админа" "процесс запущен без прав администратора"
        }

        # ---------------------------------------------------------------- python 3.15 x64
        # Порядок поиска (FR-15): py -0p -> реестр PythonCore (HKCU/HKLM/WOW6432Node) -> стандартные пути -> PATH.
        $first = New-Object System.Collections.Generic.List[string]
        $rest = New-Object System.Collections.Generic.List[string]
        $seen = New-Object System.Collections.Generic.List[string]
        $src = @{}
        function Add-PyCand {
            param([string]$Path, [bool]$Is315, [string]$Source)
            if (-not $Path) { return }
            if ($seen -contains $Path) { return }
            [void]$seen.Add($Path)
            $src[$Path] = $Source
            if ($Is315) { [void]$first.Add($Path) } else { [void]$rest.Add($Path) }
        }

        $pyLines = @()
        if (Get-Command py -ErrorAction SilentlyContinue) {
            try { $pyLines = @(& py -0p 2>$null) } catch { $pyLines = @() }
        }
        foreach ($line in $pyLines) {
            $m = [regex]::Match("$line", '([A-Za-z]:\\[^\r\n"]*\.exe)')
            if (-not $m.Success) { continue }
            Add-PyCand $m.Groups[1].Value.Trim() ("$line" -match '-V:\s*3\.15') "py -0p"
        }
        foreach ($h in @("HKCU:\Software\Python\PythonCore", "HKLM:\SOFTWARE\Python\PythonCore", "HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore")) {
            if (-not (Test-Path $h)) { continue }
            foreach ($k in @(Get-ChildItem $h -ErrorAction SilentlyContinue)) {
                $is315 = ("$($k.PSChildName)" -match "^3\.15")
                foreach ($sub in @(Get-ChildItem $k.PSPath -ErrorAction SilentlyContinue)) {
                    $ip = $null
                    try { $ip = (Get-ItemProperty -Path $sub.PSPath -Name "(default)" -ErrorAction SilentlyContinue)."(default)" } catch { }
                    if (-not $ip) { continue }
                    $ip = "$ip".Trim()
                    if ($ip -notmatch "\.exe$") { $ip = (Join-Path $ip "python.exe") }
                    Add-PyCand $ip $is315 "реестр PythonCore"
                }
            }
        }
        foreach ($p in @("$env:LOCALAPPDATA\Programs\Python\Python315\python.exe", "C:\Program Files\Python315\python.exe", "C:\Program Files\Python\Python315\python.exe")) {
            Add-PyCand $p $true "стандартный путь"
        }

        # PS 5.1: `@(List[object])` падает (ArgumentTypes mismatch) — разворачиваем в массив явно
        $candOrder = @()
        $candOrder += $first.ToArray()
        $candOrder += $rest.ToArray()

        $pyInfo = $null; $otherPy = $null; $storePy = $null; $brokenPy = $null; $probes = 0
        foreach ($p in $candOrder) {
            if ($probes -ge 6) { break }
            $probes++
            $info = Get-InvPyProbe $p
            if ($null -eq $info) { continue }
            if ($info.ok) {
                if ($info.major -eq 3 -and $info.minor -eq 15 -and $info.ver -like "*x64") { $pyInfo = $info; break }
                if (-not $otherPy) { $otherPy = $info }
            } elseif ($info.store) { if (-not $storePy) { $storePy = $info } }
            else { if (-not $brokenPy) { $brokenPy = $info } }
        }

        if ($pyInfo) {
            Add-InvItem "python" "required" "OK" $pyInfo.ver $pyInfo.path "" ("найдено: " + $src[$pyInfo.path] + "; разрядность x64, ветка 3.15")
        } else {
            $pathPy = ""
            try { $pathPy = [string](Get-Command python -ErrorAction SilentlyContinue).Source } catch { }
            if (-not $pathPy) {
                $waPy = "$env:LOCALAPPDATA\Microsoft\WindowsApps\python.exe"
                if (Test-Path -LiteralPath $waPy) { $pathPy = $waPy }
            }
            $pathInfo = $null
            if ($pathPy) { $pathInfo = Get-InvPyProbe $pathPy }
            if ($otherPy) {
                Add-InvItem "python" "required" "WRONG" $otherPy.ver $otherPy.path "winget install -e --id Python.Python.3.15  |  прямой установщик (per-user, без админа): https://www.python.org/ftp/python/3.15.2/python-3.15.2-amd64.exe /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0" "нужен Python 3.15 x64, а найдено $($otherPy.ver): $($otherPy.path)"
            } elseif ($storePy -or ($pathInfo -and $pathInfo.store)) {
                $sp = ""; if ($storePy) { $sp = $storePy.path } else { $sp = $pathPy }
                Add-InvItem "python" "required" "WRONG" "" $sp "winget install -e --id Python.Python.3.15  |  прямой установщик: https://www.python.org/ftp/python/3.15.2/python-3.15.2-amd64.exe /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0" "в PATH только ms-store алиас ($sp) — он открывает Microsoft Store, а не python; настоящий Python не установлен"
            } elseif ($pathInfo -and $pathInfo.ok) {
                Add-InvItem "python" "required" "WRONG" $pathInfo.ver $pathInfo.path "winget install -e --id Python.Python.3.15" "нужен 3.15 x64, а в PATH: $($pathInfo.ver)"
            } elseif ($brokenPy) {
                Add-InvItem "python" "required" "UNKNOWN" "" $brokenPy.path "проверить руками: & '$($brokenPy.path)' -c `"import sys;print(sys.version)`"" "python.exe есть, но не отвечает на -c (файл повреждён или это не python)"
            } else {
                Add-InvItem "python" "required" "MISSING" "" "" "winget install -e --id Python.Python.3.15  |  прямой установщик (per-user, без админа): https://www.python.org/ftp/python/3.15.2/python-3.15.2-amd64.exe /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0" "не найдено нигде: py -0p; реестр PythonCore (HKCU/HKLM/WOW6432Node); стандартные пути Python315; python в PATH"
            }
        }

        # ---------------------------------------------------------------- pip / venv
        $pyExe = ""; if ($pyInfo) { $pyExe = $pyInfo.path }
        $pipStatus = "MISSING"; $pipVer = ""; $pipNote = ""
        if ($pyExe) {
            if ($pyInfo.pipFound) { $pipStatus = "OK"; $pipVer = $pyInfo.pip }
            elseif ($pyInfo.pipUnknown) { $pipStatus = "UNKNOWN"; $pipNote = "не смогли проверить pip этим зондом" }
            elseif ($pyInfo.ensurepip) { $pipNote = "python 3.15 есть, но пакет pip не импортируется (ensurepip доступен)" }
            else { $pipNote = "python 3.15 есть, но ни pip, ни ensurepip не найдены — установка python без pip" }
        } else {
            $pipNote = "python не найден — pip проверить нельзя; сначала python 3.15"
        }
        $pipFix = "python -m ensurepip --upgrade"
        if ($pipStatus -eq "UNKNOWN") { $pipFix = "проверить руками: python -m pip --version" }
        Add-InvItem "pip" "required" $pipStatus $pipVer $(if ($pipStatus -eq "OK") { $pyExe } else { "" }) $(if ($pipStatus -eq "OK") { $null } else { $pipFix }) $pipNote

        $venvStatus = "MISSING"; $venvNote = ""
        if ($pyExe) {
            if ($pyInfo.venv) { $venvStatus = "OK" }
            elseif ($pyInfo.venvUnknown) { $venvStatus = "UNKNOWN"; $venvNote = "не смогли проверить venv этим зондом" }
            else { $venvNote = "модуль venv не найден в стандартных путях python (venv нет или битая установка)" }
        } else {
            $venvNote = "python не найден — venv проверить нельзя; сначала python 3.15"
        }
        $venvFix = "python -m ensurepip --upgrade"
        if ($venvStatus -eq "UNKNOWN") { $venvFix = "проверить руками: python -m venv --help" }
        Add-InvItem "venv" "required" $venvStatus "" $(if ($venvStatus -eq "OK") { $pyExe } else { "" }) $(if ($venvStatus -eq "OK") { $null } else { $venvFix }) $venvNote

        # ---------------------------------------------------------------- git
        $gitExe = ""
        try { $gitExe = [string](Get-Command git -ErrorAction SilentlyContinue).Source } catch { }
        if (-not $gitExe) {
            foreach ($p in @("$env:ProgramFiles\Git\bin\git.exe", "${env:ProgramFiles(x86)}\Git\bin\git.exe", "$env:LOCALAPPDATA\Programs\Git\bin\git.exe")) {
                if (Test-Path -LiteralPath $p) { $gitExe = $p; break }
            }
        }
        $gitVer = ""
        if ($gitExe) {
            # версия из ресурсов файла — без запуска процесса (git --version на медленных машинах 0.5-1 с)
            try {
                $gvi = (Get-Item -LiteralPath $gitExe -ErrorAction SilentlyContinue).VersionInfo
                if ($gvi -and "$($gvi.ProductVersion)" -match "^\d+\.\d+\.\d+") { $gitVer = "$($gvi.ProductVersion)" }
            } catch { }
            if (-not $gitVer) {
                try {
                    $gv = ((& $gitExe --version 2>$null) -join " ").Trim()
                    if ($gv -match "(\d+\.\d+\.\d+[\w\.\-]*)") { $gitVer = $matches[1] }
                } catch { }
            }
        }
        $gitFix = "winget install -e --id Git.Git  |  прямой установщик: https://github.com/git-for-windows/git/releases/download/v2.56.1.windows.1/Git-2.56.1-64-bit.exe /VERYSILENT /NORESTART"
        if ($gitExe -and $gitVer) {
            Add-InvItem "git" "required" "OK" $gitVer $gitExe "" ""
        } elseif ($gitExe) {
            Add-InvItem "git" "required" "UNKNOWN" "" $gitExe "проверить руками: & '$gitExe' --version" "git.exe найден, но версию получить не удалось"
        } else {
            Add-InvItem "git" "required" "MISSING" "" "" $gitFix "не найден: Get-Command git, %ProgramFiles%\Git, %LOCALAPPDATA%\Programs\Git"
        }

        # ---------------------------------------------------------------- gh (нужен только для push)
        $ghExe = ""
        try { $ghExe = [string](Get-Command gh -ErrorAction SilentlyContinue).Source } catch { }
        if (-not $ghExe) {
            foreach ($p in @("$env:ProgramFiles\GitHub CLI\gh.exe", "${env:ProgramFiles(x86)}\GitHub CLI\gh.exe", "$env:LOCALAPPDATA\Programs\GitHub CLI\gh.exe")) {
                if (Test-Path -LiteralPath $p) { $ghExe = $p; break }
            }
        }
        $ghVer = ""
        if ($ghExe) {
            try {
                $hvi = (Get-Item -LiteralPath $ghExe -ErrorAction SilentlyContinue).VersionInfo
                if ($hvi -and "$($hvi.ProductVersion)" -match "^\d+\.\d+\.\d+") { $ghVer = "$($hvi.ProductVersion)" }
            } catch { }
            if (-not $ghVer) {
                try {
                    $g1 = ((& $ghExe --version 2>$null) | Select-Object -First 1)
                    if ("$g1" -match "(\d+\.\d+\.\d+)") { $ghVer = $matches[1] }
                } catch { }
            }
        }
        if ($ghExe -and $ghVer) {
            Add-InvItem "gh" "optional" "OK" $ghVer $ghExe "" "нужен только для push в GitHub; для установки и работы MCP не нужен"
        } elseif ($ghExe) {
            Add-InvItem "gh" "optional" "UNKNOWN" "" $ghExe "проверить руками: & '$ghExe' --version" "gh.exe найден, но версию получить не удалось"
        } else {
            Add-InvItem "gh" "optional" "MISSING" "" "" "winget install -e --id GitHub.cli" "не найден; нужен только для push (gh auth login), установка проекта работает без него"
        }

        # ---------------------------------------------------------------- GH_TOKEN / GITHUB_TOKEN
        $tok = $null
        foreach ($n in @("GH_TOKEN", "GITHUB_TOKEN")) {
            if ($tok) { break }
            foreach ($sc in @("Process", "User", "Machine")) {
                $v = [Environment]::GetEnvironmentVariable($n, $sc)
                if ($v) { $tok = @{ name = $n; scope = $sc; value = "$v" }; break }
            }
        }
        if ($tok) {
            Add-InvItem "GH_TOKEN" "optional" "set" (Format-InvToken $tok.value) ("$($tok.scope) env: $($tok.name)") "" "токен задан ($($tok.scope):$($tok.name)); значение не печатается"
        } else {
            Add-InvItem "GH_TOKEN" "optional" "NOT_SET" "" "User env" "[Environment]::SetEnvironmentVariable('GH_TOKEN','<github_pat_...>','User') — потом открыть новый терминал; токен в логи/файлы не писать" "ни GH_TOKEN, ни GITHUB_TOKEN (Process/User/Machine); нужен только для push"
        }

        # ---------------------------------------------------------------- winget (App Installer)
        $wingetExe = ""
        try { $wingetExe = [string](Get-Command winget -ErrorAction SilentlyContinue).Source } catch { }
        if (-not $wingetExe) {
            $wa = "$env:LOCALAPPDATA\Microsoft\WindowsApps\winget.exe"
            if (Test-Path -LiteralPath $wa) { $wingetExe = $wa }
        }
        $wingetVer = ""
        if ($wingetExe) {
            # быстрый путь: версия из имени пакета в WindowsApps (без запуска winget — он стартует 1-3 с)
            $pkgDirs = @()
            try { $pkgDirs = @(Get-ChildItem (Join-Path $env:ProgramFiles "WindowsApps") -Filter "Microsoft.DesktopAppInstaller_*_x64__*" -Directory -ErrorAction SilentlyContinue) } catch { }
            foreach ($d in $pkgDirs) {
                if ($d.Name -match "DesktopAppInstaller_(\d+\.\d+\.\d+\.\d+)_x64") {
                    $parts = $matches[1].Split(".")
                    $wingetVer = "v" + $parts[0] + "." + $parts[1] + "." + $parts[2]
                    break
                }
            }
            if (-not $wingetVer) {
                $appx = @()
                try { $appx = @(Get-AppxPackage *DesktopAppInstaller* -ErrorAction SilentlyContinue) } catch { }
                if ($appx.Count -gt 0) { $wingetVer = "v" + "$($appx[0].Version)" }
            }
            if (-not $wingetVer) {
                try { $wingetVer = ((& $wingetExe --version 2>$null) -join " ").Trim() } catch { }
            }
        }
        $wingetNote = ""; $wingetStatus = "MISSING"
        if ($wingetExe -and $wingetVer) {
            $wingetStatus = "OK"
        } elseif (-not $wingetExe) {
            $appx = @()
            try { $appx = @(Get-AppxPackage *DesktopAppInstaller* -ErrorAction SilentlyContinue) } catch { }
            if ($appx.Count -gt 0) {
                $wingetStatus = "UNKNOWN"
                $wingetNote = "пакет $($appx[0].Name) $($appx[0].Version) установлен, но winget.exe не найден/не запускается"
            } else {
                $wingetNote = "ни winget.exe (в PATH и WindowsApps), ни пакета *DesktopAppInstaller*"
            }
        } else {
            $wingetStatus = "UNKNOWN"
            $wingetNote = "winget.exe найден, но версию получить не удалось"
        }
        $wingetFix = $null
        if ($wingetStatus -ne "OK") {
            $wingetFix = 'Add-AppxPackage -Path "$env:TEMP\Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle"  (скачать: https://github.com/microsoft/winget-release/releases/latest; нужен VCLibs из того же релиза)'
        }
        Add-InvItem "winget" "optional" $wingetStatus $wingetVer $wingetExe $wingetFix $wingetNote

        # ---------------------------------------------------------------- MSVC VCTools
        $vswhere = "C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
        $msvcStatus = "MISSING"; $msvcVer = ""; $msvcPath = ""; $msvcNote = ""
        if (Test-Path -LiteralPath $vswhere) {
            try {
                $vsVc = "$(& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath 2>$null | Select-Object -First 1)".Trim()
                if ($vsVc) {
                    $msvcStatus = "OK"; $msvcPath = $vsVc
                    $msvcVer = "$(& $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationVersion 2>$null | Select-Object -First 1)".Trim()
                    $msvcNote = "vswhere подтвердил компонент VC.Tools.x86.x64"
                }
            } catch { $msvcNote = "vswhere упал: $($_.Exception.Message)" }
        }
        # Компилятор ищем и без vswhere: ...\Microsoft Visual Studio\<*>\<*>\VC\Tools\MSVC\<версия>\bin\Host*\*\cl.exe
        # Test-Path с маской сначала (0.06 с), и только при попадании — медленный перебор каталогов (0.47 с).
        $toolsets = @()
        if ($msvcStatus -ne "OK") {
            foreach ($rootDir in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
                if (-not $rootDir) { continue }
                $vsRoot = (Join-Path $rootDir "Microsoft Visual Studio")
                if (-not (Test-Path -LiteralPath $vsRoot)) { continue }
                $msvcGlob = (Join-Path $vsRoot "*\*\VC\Tools\MSVC")
                if (-not (Test-Path -Path $msvcGlob)) { continue }
                $dirs = @()
                try { $dirs = @(Get-ChildItem -Path $msvcGlob -Directory -ErrorAction SilentlyContinue) } catch { }
                foreach ($d in $dirs) {
                    $cl64 = Join-Path $d.FullName "bin\Hostx64\x64\cl.exe"
                    $cl86 = Join-Path $d.FullName "bin\Hostx86\x86\cl.exe"
                    if ((Test-Path -LiteralPath $cl64) -or (Test-Path -LiteralPath $cl86)) { $toolsets += $d }
                }
            }
        }
        if ($msvcStatus -ne "OK" -and $toolsets.Count -gt 0) {
            $msvcStatus = "OK"; $msvcVer = $toolsets[0].Name; $msvcPath = $toolsets[0].FullName
            $msvcNote = "vswhere компонент не подтвердил, но компилятор cl.exe есть: $msvcPath"
        }
        if ($msvcStatus -eq "MISSING") {
            $anyVs = ""
            if (Test-Path -LiteralPath $vswhere) {
                try { $anyVs = "$(& $vswhere -latest -products * -property installationPath 2>$null | Select-Object -First 1)".Trim() } catch { }
            }
            if ($anyVs) {
                $msvcStatus = "BASE_ONLY"; $msvcPath = $anyVs
                $msvcNote = "есть '$anyVs', но без компонента VC.Tools.x86.x64 (base Build Tools без компилятора)"
            } else {
                $vsDirs = @()
                foreach ($rootDir in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
                    if (-not $rootDir) { continue }
                    $vsRoot = (Join-Path $rootDir "Microsoft Visual Studio")
                    if (-not (Test-Path -LiteralPath $vsRoot)) { continue }
                    try { $vsDirs += @(Get-ChildItem -Path (Join-Path $vsRoot "*\*") -Directory -ErrorAction SilentlyContinue) } catch { }
                }
                if ($vsDirs.Count -gt 0) {
                    $msvcStatus = "BASE_ONLY"; $msvcPath = $vsDirs[0].FullName
                    $msvcNote = "есть каталог установки Visual Studio ($($vsDirs[0].FullName)) без VC\Tools\MSVC — компилятора нет"
                } elseif (Test-Path -LiteralPath $vswhere) {
                    $msvcNote = "vswhere есть, но ни одной установки VS/Build Tools; VC\Tools\MSVC не найден"
                } else {
                    $msvcNote = "vswhere.exe не найден и VC\Tools\MSVC нет — ни VS, ни Build Tools не установлены"
                }
            }
        }
        $msvcFix = "winget install -e --id Microsoft.VisualStudio.BuildTools  ;  & 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vs_installer.exe' modify --channelId VisualStudio.18.Release --productId Microsoft.VisualStudio.Product.BuildTools --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --passive --norestart  (без --wait; затем проверить VC\Tools\MSVC\* или повторить -Inventory)"
        if ($msvcStatus -eq "UNKNOWN") { $msvcFix = "проверить руками: & 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vs_installer.exe' → Modify → «Разработка на C++»" }
        Add-InvItem "msvc_vctools" "required" $msvcStatus $msvcVer $msvcPath $(if ($msvcStatus -eq "OK") { $null } else { $msvcFix }) $msvcNote

        # ---------------------------------------------------------------- свободное место
        $cleanFix = 'python -m pip cache purge; Remove-Item -Recurse -Force "$env:USERPROFILE\.cache\huggingface","$env:LOCALAPPDATA\StanfordNLP" -ErrorAction SilentlyContinue'
        foreach ($d in @("C", "Z")) {
            $free = Get-InvFreeGB $d
            if ($null -eq $free) {
                if ($d -eq "Z") {
                    Add-InvItem "freespace_Z" "required" "NOT_REQUIRED" "" "" "" "диск Z: не смонтирован — позиция не требуется"
                } else {
                    Add-InvItem "freespace_C" "required" "UNKNOWN" "" "" "проверить руками: «Этот компьютер» → диск C: → свободно ≥ 12 ГБ" "Get-PSDrive C не вернул свободное место"
                }
                continue
            }
            $st = "OK"; if ($free -lt 12) { $st = "LOW" }
            Add-InvItem ("freespace_" + $d) "required" $st ("$free GB") ("$d`:\") $(if ($st -eq "LOW") { $cleanFix } else { "" }) "норма ≥ 12 ГБ: venv+torch ~4, модели ~1.6, Build Tools 3–4, кэш"
        }

        # ---------------------------------------------------------------- диск проекта (UNC/сеть = медленно)
        # DriveInfo.DriveType вместо Get-PSDrive: 0.03 с против 0.33 с на сетевом диске.
        $drv = $null
        try { if ($root.Length -ge 2) { $drv = [System.IO.DriveInfo]::new($root.Substring(0, 2)) } } catch { }
        $isNet = $false
        try { if ($drv -and $drv.DriveType -eq [System.IO.DriveType]::Network) { $isNet = $true } } catch { }
        if (($root -like "\\*") -or $isNet) {
            $why = "UNC-путь"
            if ($drv) { $why = "сетевой диск $($drv.Name)" }
            Add-InvItem "project_disk" "optional" "SLOW" "" $root "перенести проект на локальный диск (например C:\KI_WORK): сеть/UNC в 4–7 раз медленнее" "проект на $why — распаковка моделей и pip будут в 4–7 раз дольше"
        } else {
            Add-InvItem "project_disk" "optional" "OK" "" $root "" "локальный диск — быстрый IO"
        }

        # ---------------------------------------------------------------- сеть (отдельный блок, 5 с/хост)
        $hosts = @("github.com", "raw.githubusercontent.com", "objects.githubusercontent.com", "pypi.org", "huggingface.co", "aka.ms", "www.python.org")
        if ($NoNetwork) {
            Add-InvItem "network" "required" "NOTE" "" "" "" ("сетевой блок пропущен (-NoNetwork); как проверить руками: Invoke-WebRequest -Method Head -TimeoutSec 5 https://pypi.org — хосты: " + ($hosts -join ", "))
        } else {
            $lines = @(); $ok = 0
            foreach ($h in $hosts) {
                $code = 0
                try {
                    $r = Invoke-WebRequest -Uri ("https://" + $h + "/") -Method Head -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
                    $code = [int]$r.StatusCode
                } catch {
                    try { if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode } } catch { $code = 0 }
                }
                if ($code -gt 0) { $ok++; $lines += "$h $code" } else { $lines += "$h FAIL" }
            }
            $netStatus = "MISSING"; if ($ok -eq $hosts.Count) { $netStatus = "OK" } elseif ($ok -gt 0) { $netStatus = "PARTIAL" }
            Add-InvItem "network" "required" $netStatus ("$ok/$($hosts.Count) OK") "" "TLS-reset 10054 — повторить шаг; модели офлайн: -Zip <архив> или resources.json в кэш" ($lines -join " | ")
        }

        # ---------------------------------------------------------------- MCP-клиент
        $mcpPaths = @(
            "$env:USERPROFILE\.pi\agent\mcp.json",
            "$env:USERPROFILE\.lmstudio\mcp.json",
            "$env:APPDATA\Claude\claude_desktop_config.json",
            "$env:USERPROFILE\.cursor\mcp.json",
            "$env:APPDATA\Code\User\mcp.json"
        )
        $found = @(); foreach ($p in $mcpPaths) { if (Test-Path -LiteralPath $p) { $found += $p } }
        if ($found.Count -gt 0) {
            Add-InvItem "mcp_client" "optional" "OK" "" ($found -join "; ") "" "конфиг найден; запись stanza-german скрипт не пишет — только подсказка"
        } else {
            Add-InvItem "mcp_client" "optional" "MISSING" "" "" "создать/дополнить mcp.json клиента (образец: MCP-stanza-german\mcp.json.example) и перезапустить клиент — конфиг скрипт не пишет" ("ни одного клиентского mcp.json; проверены: " + ($mcpPaths -join "; "))
        }

        # ---------------------------------------------------------------- venv проекта
        $venvPy = ""
        if ($root) { $venvPy = (Join-Path $root ".venv\Scripts\python.exe") }
        $pvStatus = "MISSING"; $pvVer = ""; $pvPath = ""; $pvNote = "venv проекта не создан"
        if ($venvPy -and (Test-Path -LiteralPath $venvPy)) {
            $vi = Get-InvPyProbe $venvPy
            if ($vi -and $vi.ok) {
                $pvVer = $vi.ver; $pvPath = $venvPy
                if ($vi.major -eq 3 -and $vi.minor -eq 15) { $pvStatus = "OK"; $pvNote = "" } else { $pvStatus = "WRONG"; $pvNote = "venv проекта должен быть на Python 3.15, а он $($vi.ver)" }
            } elseif ($vi -and $vi.store) {
                $pvStatus = "WRONG"; $pvPath = $venvPy; $pvNote = ".venv\Scripts\python.exe указывает на ms-store алиас — venv сломан, пересоздать"
            } else {
                $pvStatus = "UNKNOWN"; $pvPath = $venvPy; $pvNote = "не смогли запустить $venvPy; проверить руками: & '$venvPy' -V"
            }
        }
        Add-InvItem "project_venv" "required" $pvStatus $pvVer $pvPath "all.ps1 -Steps venv,deps" $pvNote

        # ---------------------------------------------------------------- кэши моделей / pip
        $stanPath = "$env:LOCALAPPDATA\StanfordNLP"
        $stanMB = Get-InvDirSizeMB $stanPath
        if ($null -eq $stanMB) {
            if (Test-Path -LiteralPath $stanPath) {
                Add-InvItem "stanza_cache" "optional" "UNKNOWN" "" $stanPath "проверить руками: правый клик по $stanPath → Свойства (размер)" "размер не измерен: обход каталога не уложился в 1.5 с"
            } else {
                Add-InvItem "stanza_cache" "optional" "MISSING" "" "" "all.ps1 -Steps models  |  офлайн: -Zip stanza-models-de-*.zip" ("каталога нет ($stanPath) — stanza скачает модели при первом запуске (~1.6 ГБ)")
            }
        } else {
            $st = "MISSING"; if ($stanMB -ge 800) { $st = "OK" } elseif ($stanMB -gt 0) { $st = "PARTIAL" }
            Add-InvItem "stanza_cache" "optional" $st ("$stanMB MB") $stanPath "all.ps1 -Steps models  |  офлайн: -Zip stanza-models-de-*.zip" "норма ~1.6 ГБ (de, tokenize/mwt/pos/lemma/dep)"
        }

        $hfPath = "$env:USERPROFILE\.cache\huggingface"
        $hfMB = Get-InvDirSizeMB $hfPath
        if ($null -eq $hfMB) {
            if (Test-Path -LiteralPath $hfPath) {
                Add-InvItem "hf_cache" "optional" "UNKNOWN" "" $hfPath "проверить руками: правый клик по $hfPath → Свойства (размер)" "размер не измерен: обход каталога не уложился в 1.5 с"
            } else {
                Add-InvItem "hf_cache" "optional" "MISSING" "" "" "all.ps1 -Steps models" ("каталога нет ($hfPath) — huggingface-кэш пуст")
            }
        } else {
            $st = "MISSING"; if ($hfMB -ge 300) { $st = "OK" } elseif ($hfMB -gt 0) { $st = "PARTIAL" }
            Add-InvItem "hf_cache" "optional" $st ("$hfMB MB") $hfPath "all.ps1 -Steps models" "норма ≥ 300 МБ (torch и колёса из HF)"
        }

        $pipPath = "$env:LOCALAPPDATA\pip\Cache"
        $pipMB = Get-InvDirSizeMB $pipPath
        if ($null -eq $pipMB) {
            Add-InvItem "pip_cache" "optional" "NOTE" "" $pipPath "" "python -m pip cache dir — размер не измерен; кэш pip не обязателен"
        } else {
            Add-InvItem "pip_cache" "optional" "NOTE" ("$pipMB MB") $pipPath "" "кэш колёс (torch и др.); чистится python -m pip cache purge"
        }
    }

    # ------------------------------------------------------------------ итог
    $blocking = @($script:KI_InvItems | Where-Object { $_.need -eq "required" -and @("MISSING","WRONG","BASE_ONLY","LOW","PARTIAL","UNKNOWN") -contains $_.status })
    $code = $Code_Ready
    if ($blocking.Count -gt 0) { $code = $Code_Human }
    if ($script:KI_InvItems.Count -eq 0) { $code = $Code_Broken }

    $shown = @($script:KI_InvItems.ToArray())
    if ($RequiredOnly) { $shown = @($script:KI_InvItems | Where-Object { $_.need -eq "required" }) }

    $elapsed = [math]::Round($sw.Elapsed.TotalSeconds, 1)
    $itemArr = @($shown | ForEach-Object {
        [pscustomobject]@{ name = $_.name; need = $_.need; status = $_.status; version = $_.version; path = $_.path; fix = $_.fix; note = $_.note }
    })
    $obj = [pscustomobject]@{ code = $code; elapsed = $elapsed; items = $itemArr }

    $text = @(Format-InvText $obj $RequiredOnly)
    if ($Log) {
        try { [IO.File]::AppendAllText($Log, (($text -join "`r`n") + "`r`n"), [System.Text.UTF8Encoding]::new($false)) } catch { }
    }
    # Печать: таблица (или JSON при -Json). -Quiet — не печатать НИЧЕГО (библиотечный режим:
    # all.ps1/CI), объект {code,elapsed,items} возвращается всегда. -Log пишется и в -Quiet.
    if (-not $Quiet) {
        if ($Json) { Out-InvLine ($obj | ConvertTo-Json -Depth 5) }
        else { foreach ($l in $text) { Out-InvLine $l } }
    }
    return $obj
}

# ------------------------------------------------------------------ точка входа файла

function Write-InvUsage {
    [Console]::Out.WriteLine("inventory.ps1 — инвентаризация среды stanza-german-ppl (только чтение)")
    [Console]::Out.WriteLine("  powershell -NoProfile -ExecutionPolicy Bypass -File scripts\inventory.ps1 [-Json] [-NoNetwork] [-RequiredOnly] [-Log <path>]")
    [Console]::Out.WriteLine("  dot-source: . .\scripts\inventory.ps1  →  Get-Inventory [-Json] [-NoNetwork] [-RequiredOnly] [-Log <path>]")
    [Console]::Out.WriteLine("  коды: 0 — всё требуемое на месте; 2 — нужен человек; 4 — сломан запуск")
}

# Ключи файла разбираются вручную из $args: у модуля НЕТ param-блока (иначе dot-source
# затирает одноимённые переменные вызывающего: $Json/$NoNetwork/$Log).
function Invoke-InventoryCli {
    param([string[]]$ArgList)

    $asJson = $false; $asNoNetwork = $false; $asRequiredOnly = $false; $asLog = ""
    for ($i = 0; $i -lt $ArgList.Count; $i++) {
        $a = "$($ArgList[$i])"
        if ($a -eq "-Json") { $asJson = $true }
        elseif ($a -eq "-NoNetwork") { $asNoNetwork = $true }
        elseif ($a -eq "-RequiredOnly") { $asRequiredOnly = $true }
        elseif ($a -eq "-Log") {
            $i++
            if ($i -ge $ArgList.Count) { [Console]::Error.WriteLine("inventory.ps1: -Log требует путь"); exit 4 }
            $asLog = "$($ArgList[$i])"
        }
        elseif ($a -eq "-?" -or $a -eq "-Help" -or $a -eq "--help") { Write-InvUsage; exit 0 }
        else { [Console]::Error.WriteLine("inventory.ps1: неизвестный ключ '$a'"); Write-InvUsage; exit 4 }
    }

    # -Quiet: модуль не печатает, рендерит только CLI — ровно один вывод на прогон
    $inv = Get-Inventory -Quiet -NoNetwork:$asNoNetwork -RequiredOnly:$asRequiredOnly -Log:$asLog
    if ($asJson) {
        Out-InvLine ($inv | ConvertTo-Json -Depth 5)
    } else {
        foreach ($l in @(Format-InvText $inv $asRequiredOnly)) { Out-InvLine $l }
    }
    exit $inv.code
}

# Сентинел: потребитель (all.ps1) ставит $global:KI_LIB_ONLY = $true перед dot-source —
# тогда файл только определяет функции и НЕ печатает таблицу (и не делает exit).
# Дополнительно: $MyInvocation.InvocationName -eq '.' — обычный dot-source в PS 5.1.
if ((-not $global:KI_LIB_ONLY) -and $MyInvocation.InvocationName -ne ".") {
    Invoke-InventoryCli @($args)
}





