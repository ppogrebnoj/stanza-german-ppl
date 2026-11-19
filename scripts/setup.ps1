#Requires -Version 5.1
<#
    setup.ps1 - развернуть проект на машине: venv, зависимости, git-хук, проверка.

    Из корня проекта:
        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -UseLock    # точные пины (requirements.lock)
        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -SkipDeps   # без сети: только хуки и проверки
        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -SkipDoctor # без финальной проверки (её делает all.ps1)
        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -DryRun     # показать команды, ничего не делать
        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Python "C:\...\Python315\python.exe"
        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -ProgressFile C:\temp\p.ndjson   # NDJSON-события прогресса (их читает all.ps1)
        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Retries 4                        # попыток pip на сетевых прогонах

    Поддерживается только Python 3.15 x64 (эталон проекта: torch 2.15.0 / numpy 2.5.5).
    Версия проверяется ДО создания venv; если 3.15 нет — печатается команда winget.

    Модели Stanza этим скриптом не качаются: их тянет сам Stanza (stanza.download('de'),
    официальный источник Stanford). Офлайн-архив распаковывает scripts\unpack_models.py --zip.
    После моделей повторите doctor.
#>
[CmdletBinding()]
param(
    [string]$VenvDir = "",
    [string]$Python = "",      # явный путь к python.exe (если нужную версию не нашли автоматически)
    [switch]$UseLock,
    [switch]$SkipDeps,
    [switch]$SkipDoctor,
    [int]$Retries = 3,
    [string]$ProgressFile = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
# Вывод: в консоли — как принято в системе (cp866 и т.п.), при перенаправлении (лог, CI) — UTF-8
try {
    if ([Console]::IsOutputRedirected) {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $OutputEncoding = [System.Text.Encoding]::UTF8
    }
} catch { }
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $VenvDir) { $VenvDir = Join-Path $Root ".venv" }
$Reqs = if ($UseLock) { Join-Path $Root "requirements.lock" } else { Join-Path $Root "requirements.txt" }

function Step($n, $text) { Write-Host ""; Write-Host "[$n] $text" -ForegroundColor Cyan; Prog @{ ev = "step_start"; step = "$n"; sub = $text } }
function Fail($text) { Write-Host "ОШИБКА: $text" -ForegroundColor Red; Prog @{ ev = "step_fail"; step = "setup"; msg = $text }; exit 1 }

# NDJSON-события прогресса: их читает all.ps1 (Write-Progress2) и печатает живую строку.
# Формат — одна компактная JSON-строка: {t, ev, step, sub, pct, bytes, total, eta, msg}
$script:ProgLast = [datetime]::MinValue
function Prog($o) {
    if (-not $ProgressFile) { return }
    try {
        $now = Get-Date
        if ($o.ev -eq "progress") {
            if (($now - $script:ProgLast).TotalMilliseconds -lt 300) { return }
            $script:ProgLast = $now
        }
        $o.t = $now.ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
        [IO.File]::AppendAllText($ProgressFile, ($o | ConvertTo-Json -Compress -Depth 4) + "`n", (New-Object System.Text.UTF8Encoding $false))
    } catch { }
}
function Convert-Size($num, $unit) {
    $n = 0.0
    try { $n = [double]("$num" -replace ',', '.') } catch { return 0 }
    switch ($unit) { "bytes" { return $n } "KB" { return $n * 1KB } "MB" { return $n * 1MB } "GB" { return $n * 1GB } default { return 0 } }
}

function Run($exe, [string[]]$argv, $hint) {
    Write-Host ("  > {0} {1}" -f $exe, ($argv -join " "))
    if ($DryRun) { return }
    & $exe @argv
    if ($LASTEXITCODE -ne 0) { Fail "$hint (код выхода $LASTEXITCODE)" }
}

# pip с подшагами и ретраями (FR-3/FR-5): вывод читается построчно — «Collecting X»,
# «Downloading f.whl (1.2 MB)», «Building wheel for X», «Installing collected packages:» — и по ним
# идут события прогресса. -q не ставим: с ним подшагов не видно, а установка torch занимает минуты
# полной немотой. Пины при повторах не меняются: та же команда, та же requirements.txt.
function Run-Pip([string[]]$pipArgs, [string]$id, $hint) {
    $attempt = 0
    $bytes = 0
    $collected = @{}
    while ($true) {
        $attempt++
        Write-Host ("  > python -m pip {0} (попытка {1}/{2})" -f ($pipArgs -join " "), $attempt, $Retries)
        Prog @{ ev = "progress"; step = "deps"; sub = ("pip попытка $attempt/$Retries"); bytes = $bytes }
        if ($DryRun) { return }
        $prevEA = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & $vp @pipArgs --progress-bar off 2>&1 | ForEach-Object {
            $l = "$_"
            Write-Host "  | $l"
            if ($l -match '^Collecting ([A-Za-z0-9_.\-]+)') {
                $collected[$matches[1].ToLower()] = $true
                # requirements.txt — это 5 пинов, а Collecting строк десятки (зависимии): знаменатель
                # имеет смысл только пока счётчик в его пределах, иначе «pip: X [7/5]» выглядит обманом
                $lbl = $(if ($collected.Count -le $reqCount) { ("pip: " + $matches[1] + " [" + $collected.Count + "/" + $reqCount + "]") } else { ("pip: " + $matches[1] + " (собрано " + $collected.Count + " пакетов, пинов " + $reqCount + ")") })
                $pctv = [math]::Min(95, [math]::Round(100 * $collected.Count / [math]::Max(1, $reqCount), 1))
                Prog @{ ev = "progress"; step = "deps"; sub = $lbl; pct = $pctv; bytes = $bytes }
            } elseif ($l -match '^Downloading \S+ \(([\d\.,]+) (bytes|KB|MB|GB)\)') {
                $bytes += Convert-Size $matches[1] $matches[2]
                Prog @{ ev = "progress"; step = "deps"; sub = ("качаю: " + (($l -split ' ')[1] -split '/')[(-1)]); bytes = $bytes }
            } elseif ($l -match '^Building wheel for ([A-Za-z0-9_.\-]+)') {
                Prog @{ ev = "progress"; step = "deps"; sub = ("сборка из sdist: " + $matches[1] + " (нужен MSVC VCTools)"); bytes = $bytes }
            } elseif ($l -match '^Installing collected packages:') {
                Prog @{ ev = "progress"; step = "deps"; sub = "установка колёс в .venv"; bytes = $bytes; pct = 95 }
            }
        }
        $rc = $LASTEXITCODE
        $ErrorActionPreference = $prevEA
        if ($rc -eq 0) { Prog @{ ev = "step_ok"; step = $id; pct = 100; bytes = $bytes }; return }
        Prog @{ ev = "step_fail"; step = $id; msg = ("pip rc=$rc, попытка $attempt/$Retries") }
        if ($attempt -ge $Retries) { Fail ("$hint (код выхода $rc за $attempt попыток; причины: сеть/прокси, пин-конфликт, нет MSVC VCTools — см. -Inventory)") }
        Write-Host "  повтор через 15 с (пины не меняем)" -ForegroundColor Yellow
        Start-Sleep -Seconds 15
    }
}

Write-Host "проект : $Root"
Write-Host "venv   : $VenvDir"
Write-Host "пины   : $(Split-Path -Leaf $Reqs)"
if ($DryRun) { Write-Host "режим  : dry-run (ничего не меняется)" }

# ---------------------------------------------------------------- 1. Python
Step 1 "поиск Python 3.15"
# Поддерживается только 3.15: под неё есть колёса torch 2.15.0 / numpy 2.5.5,
# и на ней сняты эталонные цифры F1 (0.777 / 0.686).
$WANT = "3.15"
$cands = @{}
$seen  = @()

function Get-PyVer($exe) {
    try {
        $v = & $exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) { return "$v".Trim() }
    } catch { }
    return $null
}

if ($Python) {
    if (-not (Test-Path $Python)) { Fail "нет файла -Python $Python" }
    $v = Get-PyVer $Python
    if ($v) { $cands[$v] = (Resolve-Path $Python).Path }
} else {
    # все версии через py launcher: " -V:3.15 *        C:\...\python.exe"
    try {
        foreach ($line in (& py -0p 2>$null)) {
            $pVer = $null; $pPath = $null
            if ($line -match '-V:(\d+)\.(\d+)') { $pVer = "$($Matches[1]).$($Matches[2])" }
            if ($line -match 'python\.exe') { $pPath = ($line -split '\s+')[-1].Trim() }
            if ($pVer -and $pPath) { $seen += $pVer; if (Test-Path $pPath) { $cands[$pVer] = $pPath } }
        }
    } catch { }
    # python из PATH
    try {
        $out = & python -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) {
            $p = "$out".Trim(); $v = Get-PyVer $p
            if ($v) { $seen += $v; if (-not $cands.ContainsKey($v)) { $cands[$v] = $p } }
        }
    } catch { }
}

if (-not $cands.ContainsKey($WANT)) {
    $have = if ($seen.Count) { ($seen | Sort-Object -Unique) -join ', ' } else { 'не найдено ни одного' }
    Fail ("нужен Python $WANT x64. Найдено: $have.`n" +
          "  Поставьте, текущие версии это не затронет:`n" +
          "    winget install --id Python.Python.3.15 -e --accept-package-agreements`n" +
          "  без winget (нет Магазина) — прямой ссылкой:`n" +
          "    curl.exe -L -o %TEMP%\py315.exe https://www.python.org/ftp/python/3.15.2/python-3.15.2-amd64.exe`n" +
          "    %TEMP%\py315.exe /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0`n" +
          "  версии 3.12/3.13 не подходят (колёса torch cp315, эталонные цифры на 3.15)`n" +
          "  затем запустите этот скрипт снова.")
}

$py = $cands[$WANT]
$ver = & $py -c "import sys; print('%d.%d.%d' % sys.version_info[:3])"
Write-Host "  выбран: $py ($ver)"
Write-Host "  пины: requirements.txt (torch 2.15.0 / numpy 2.5.5)"

# ---------------------------------------------------------------- 2. venv
Step 2 "виртуальное окружение"
$vp = Join-Path $VenvDir "Scripts\python.exe"
if (Test-Path $vp) {
    Write-Host "  уже есть: $vp"
    Prog @{ ev = "step_skip"; step = "venv"; sub = "venv уже есть" }
} else {
    Run $py @("-m", "venv", $VenvDir) "не удалось создать venv"
    Prog @{ ev = "step_ok"; step = "venv"; sub = $VenvDir }
}

# ---------------------------------------------------------------- 3. зависимости
Step 3 "зависимости"
if ($SkipDeps) {
    Write-Host "  пропущено (-SkipDeps)"
} else {
    if (-not (Test-Path $Reqs)) { Fail "нет файла $Reqs" }
    $reqCount = @(Get-Content $Reqs | Where-Object { $_ -match '^\s*[A-Za-z]' }).Count
    Run-Pip @("-m", "pip", "install", "--retries", "5", "--timeout", "60", "-U", "pip") "deps-pip" "не удалось обновить pip"
    Run-Pip @("-m", "pip", "install", "--retries", "5", "--timeout", "60", "-r", $Reqs) "deps" "не удалось установить зависимости"
}

# ---------------------------------------------------------------- 4. git-хук
Step 4 "git-хук pre-commit"
$hookSrc = Join-Path $Root "правило\git-hooks\pre-commit"
$gitDir = Join-Path $Root ".git"
if (-not (Test-Path $gitDir)) {
    Write-Host "  не git-репозиторий — пропущено"
} elseif (-not (Test-Path $hookSrc)) {
    Write-Host "  нет $hookSrc — пропущено" -ForegroundColor Yellow
} else {
    $hookDst = Join-Path $gitDir "hooks\pre-commit"
    if ($DryRun) {
        Write-Host "  будет скопировано (LF): $hookSrc -> $hookDst"
    } else {
        $text = [IO.File]::ReadAllText($hookSrc) -replace "`r`n", "`n"
        [IO.File]::WriteAllText($hookDst, $text, (New-Object System.Text.UTF8Encoding $false))
        Write-Host "  установлен (LF): $hookDst"
    }
}

# ---------------------------------------------------------------- 5. проверка
Step 5 "проверка окружения (doctor)"
$doctor = Join-Path $Root "scripts\doctor.py"
if ($SkipDoctor) {
    # all.ps1 вызывает setup.ps1 как подшаг и сам делает doctor финальным шагом: на медленных
    # дисках (сетевые шары) импорт torch внутри doctor стоит минуты, двойная проверка дороговата
    Write-Host "  пропущено (-SkipDoctor): финальную проверку делает all.ps1"
    Prog @{ ev = "step_skip"; step = "doctor"; sub = "-SkipDoctor" }
} elseif (Test-Path $doctor) {
    $pyDoctor = $py
    if (Test-Path $vp) {
        $venvOk = $false
        try {
            $null = & $vp -c "import stanza" 2>&1
            $venvOk = ($LASTEXITCODE -eq 0)
        } catch {
            $venvOk = $false
        }
        if ($venvOk) {
            $pyDoctor = $vp
        } else {
            Write-Host "  в venv нет зависимостей (-SkipDeps?) — проверяю системным Python" -ForegroundColor Yellow
        }
    }
    $env:PYTHONUTF8 = "1"
    Run $pyDoctor @($doctor, "--soft-models") "doctor нашёл блокеры (FAIL)"
} else {
    Write-Host "  нет scripts\doctor.py — пропущено" -ForegroundColor Yellow
}

Write-Host ""
if ($DryRun) {
    Write-Host "dry-run завершён: команды выше будут выполнены без -DryRun." -ForegroundColor Green
} else {
    Write-Host 'готово. Дальше: модели — .venv\Scripts\python.exe -c "import stanza; stanza.download(''de'')" (или unpack_models.py --zip <офлайн-архив>),' -ForegroundColor Green
    Write-Host "конфиг MCP-клиента кладёт человек: образец MCP-stanza-german\mcp.json.example (УСТАНОВКА.md §1.3)." -ForegroundColor Green
}
