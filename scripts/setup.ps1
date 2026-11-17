#Requires -Version 5.1
<#
    setup.ps1 - развернуть проект на машине: venv, зависимости, git-хук, проверка.

    Из корня проекта:
        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -UseLock    # точные пины (requirements.lock)
        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -SkipDeps   # без сети: только хуки и проверки
        powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -DryRun     # показать команды, ничего не делать

    Модели Stanza этим скриптом не качаются: см. scripts\unpack_models.py
    (ассет models-v1 в GitHub Releases) — затем повторите doctor.
#>
[CmdletBinding()]
param(
    [string]$VenvDir = "",
    [switch]$UseLock,
    [switch]$SkipDeps,
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

function Step($n, $text) { Write-Host ""; Write-Host "[$n] $text" -ForegroundColor Cyan }
function Fail($text) { Write-Host "ОШИБКА: $text" -ForegroundColor Red; exit 1 }
function Run($exe, [string[]]$argv, $hint) {
    Write-Host ("  > {0} {1}" -f $exe, ($argv -join " "))
    if ($DryRun) { return }
    & $exe @argv
    if ($LASTEXITCODE -ne 0) { Fail "$hint (код выхода $LASTEXITCODE)" }
}

Write-Host "проект : $Root"
Write-Host "venv   : $VenvDir"
Write-Host "пины   : $(Split-Path -Leaf $Reqs)"
if ($DryRun) { Write-Host "режим  : dry-run (ничего не меняется)" }

# ---------------------------------------------------------------- 1. Python
Step 1 "поиск Python 3.11"
$py = $null
foreach ($cand in @(@("py", "-3.11"), @("python3.11"), @("python"))) {
    try {
        $exe = $cand[0]
        $pre = @($cand | Select-Object -Skip 1)
        $out = & $exe @pre -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { $py = "$out".Trim(); break }
    } catch { }
}
if (-not $py) { Fail "Python не найден. Установите Python 3.11.x (python.org) и повторите." }

$ver = & $py -c "import sys; print('%d.%d.%d' % sys.version_info[:3])"
Write-Host "  найден: $py ($ver)"
if ($ver -notlike "3.11.*") {
    Write-Host "  ВНИМАНИЕ: проект проверен на 3.11.x; на $ver возможны отличия в цифрах." -ForegroundColor Yellow
}

# ---------------------------------------------------------------- 2. venv
Step 2 "виртуальное окружение"
$vp = Join-Path $VenvDir "Scripts\python.exe"
if (Test-Path $vp) {
    Write-Host "  уже есть: $vp"
} else {
    Run $py @("-m", "venv", $VenvDir) "не удалось создать venv"
}

# ---------------------------------------------------------------- 3. зависимости
Step 3 "зависимости"
if ($SkipDeps) {
    Write-Host "  пропущено (-SkipDeps)"
} else {
    if (-not (Test-Path $Reqs)) { Fail "нет файла $Reqs" }
    Run $vp @("-m", "pip", "install", "-q", "-U", "pip") "не удалось обновить pip"
    Run $vp @("-m", "pip", "install", "-q", "-r", $Reqs) "не удалось установить зависимости"
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
if (Test-Path $doctor) {
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
    Write-Host "готово. Дальше: python scripts\unpack_models.py --release models-v1 --check (модели)," -ForegroundColor Green
    Write-Host "затем python scripts\install_mcp.py (прописать сервер в клиенте)." -ForegroundColor Green
}
