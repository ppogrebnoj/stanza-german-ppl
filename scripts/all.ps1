#Requires -Version 5.1
<#
    all.ps1 — установка проекта ОДНОЙ командой: префлайт + venv + зависимости + модели
    + прописка MCP-клиента + doctor. Работает неинтерактивно (никогда не спрашивает),
    поэтому годится и для человека, и для агента.

        powershell -NoProfile -ExecutionPolicy Bypass -File scripts\all.ps1

        -CheckOnly   ничего не менять: префлайт + что уже готово + doctor
        -DryRun      напечатать команды, которые будут выполнены
        -Json        машинный вывод (шаги, коды, подсказки) вместо человеческого
        -Steps       список шагов: venv,deps,models,mcp,doctor
        -Zip         архив моделей локально (офлайн); по умолчанию ищем stanza-models-de-*.zip в корне
        -Python      явный путь к python.exe 3.15 (если py-лаунчер его не нашёл)
        -MinFreeGB   сколько ГБ просить на диске (по умолчанию 7)

    Порядок моделей: локальный архив stanza-models-de-*.zip рядом с .sha256 (офлайн, быстро) ->
    иначе официальная загрузка Stanford: stanza.download() тянет список ресурсов со
    raw.githubusercontent.com (stanza-resources) и файлы с huggingface.co (stanfordnlp/stanza-de).
    Своих архивов моделей в этом репозитории нет и не будет.
    Конфиг MCP-клиента создаёт человек (образец: MCP-stanza-german\mcp.json.example): скрипт
    печатает готовый фрагмент с путями этой машины и проверяет, есть ли запись в конфиге
    (-McpConfig, по умолчанию %USERPROFILE%\.lmstudio\mcp.json); если её нет — код 2.
    gh и токены — это доступ на ЗАПИСЬ репозитория (push), к установке отношения не имеют: чтение
    публичного репозитория и модели от Stanford работают без них. Если токен задан
    (GH_TOKEN/GITHUB_TOKEN: сначала процесс, потом User-реестр — setx в текущем окне не виден),
    Test-Gh им авторизуется, и это шаг NOTE в отчёте, не блокер. Печать токена исключена
    (маскируется github_pat_***).

    Коды выхода (контракт, см. УСТАНОВКА.md):
        0  ГОТОВО
        2  НУЖЕН ЧЕЛОВЕК: нет Python 3.15 x64 / нет сети / мало места / в конфиге MCP нет записи
        3  ШАГ УПАЛ: pip, распаковка моделей, doctor (FAIL) — лечится повтором того же шага
        4  СЛОМАН ЗАПУСК: нет файлов скриптов, чужие ключи, не Windows

    Лог: install.log в корне проекта (токены маскируются).
#>
[CmdletBinding()]
param(
    [string]$Steps = "venv,deps,models,mcp,doctor",
    [string]$Zip = "",
    [string]$Python = "",
    [long]$MinFreeGB = 7,
    [string]$McpConfig = "",
    [string]$McpKey = "mcpServers",
    [switch]$CheckOnly,
    [switch]$DryRun,
    [switch]$Json,
    [string]$Log = ""
)

$ErrorActionPreference = "Continue"   # не Stop: нативные команды (pip, gh, python) пишут в stderr
                                       # штатные предупреждения, и PowerShell превращает их в
                                       # NativeCommandError и обрывает шаг. Решение — только $LASTEXITCODE.
$Code_Ready, $Code_Human, $Code_Step, $Code_Broken = 0, 2, 3, 4

try {
    # дети (doctor/setup/unpack) печатают UTF-8 — читать их тоже надо по-UTF-8
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    $OutputEncoding = [System.Text.Encoding]::UTF8
} catch { }
$env:PYTHONUTF8 = "1"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Log) { $Log = Join-Path $Root "install.log" }
$VenvPy = Join-Path $Root ".venv\Scripts\python.exe"
$NetHosts = @("https://pypi.org", "https://api.github.com")

$logLines = New-Object System.Collections.Generic.List[string]
$plan = New-Object System.Collections.Generic.List[object]
$done = New-Object System.Collections.Generic.List[object]

function Say($text, $color) { if (-not $Json) { if ($color) { Write-Host $text -ForegroundColor $color } else { Write-Host $text } } }
function Log($text) {
    # токен не должен попасть в лог ни при каких условиях
    $safe = [regex]::Replace("$text", '(gh_pat_|github_pat_)[A-Za-z0-9_]+', '$1***')
    $logLines.Add((Get-Date).ToString("HH:mm:ss") + " " + $safe)
}
function Add-Step($id, $status, $sec, $detail, $hint) {
    $done.Add([ordered]@{ id = $id; status = $status; seconds = $sec; detail = "$detail"; hint = "$hint" }) | Out-Null
    Say ("  [{0,-4}] {1,-7} {2}" -f $status, $id, $detail)
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
    $gh = Get-Command gh -ErrorAction SilentlyContinue
    if (-not $gh) { return @{ ok = $false; why = "no-gh" } }
    & gh auth status *> $null
    if ($LASTEXITCODE -eq 0) {
        # честный источник: gh сам берёт GH_TOKEN/GITHUB_TOKEN из окружения, keyring при этом молчит
        $src = $(if ($env:GH_TOKEN -or $env:GITHUB_TOKEN) { "токен из Process" } else { "keyring" })
        return @{ ok = $true; why = "gh $src" }
    }
    $t = Get-EnvToken
    if (-not $t) { return @{ ok = $false; why = "no-token" } }
    if ($DryRun -or $CheckOnly) {
        return @{ ok = $true; why = "$($t.Name) ($($t.Scope)), len=$($t.Value.Length)" }
    }
    "$($t.Value)" | & gh auth login --with-token *> $null
    if ($LASTEXITCODE -ne 0) { return @{ ok = $false; why = "gh auth login --with-token отказал ($($t.Name))" } }
    & gh auth setup-git *> $null
    Log("gh авторизован токеном $($t.Name) ($($t.Scope))")
    return @{ ok = $true; why = "$($t.Name) ($($t.Scope))" }
}

function Get-FreeGB($path) {
    try {
        $d = New-Object System.IO.DriveInfo(($path.Substring(0, 1) + ":\").ToUpper())
        return [math]::Round($d.AvailableFreeSpace / 1GB, 1)
    } catch { return -1 }
}

function Test-Net() {
    $bad = @()
    foreach ($u in $NetHosts) {
        try {
            $null = Invoke-WebRequest -Uri $u -Method Head -TimeoutSec 6 -UseBasicParsing
        } catch { $bad += $u }
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
    if (-not (Test-Path $VenvPy)) { return $false }
    & $py -c "import stanza, torch, mcp, pyphen" *> $null
    return ($LASTEXITCODE -eq 0)
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

Say "all.ps1: $Root" Cyan
Say ("режим : " + $(if ($CheckOnly) { "check-only (ничего не меняю)" } elseif ($DryRun) { "dry-run" } else { "установка" }))
$want = @($Steps -Split ',' | ForEach-Object { $_.Trim().ToLower() })
$known = @("venv", "deps", "models", "mcp", "doctor")

# ------------------------------------------------------------------ 0. префлайт

$t0 = Get-Date
$blockers = @()
$badSteps = @($want | Where-Object { $_ -notin $known })
if ($badSteps) {
    Add-Step "preflight" "FAIL" 0 ("неизвестный шаг: " + ($badSteps -join ", ") + "; известно: " + ($known -join ", ")) "код 4: поправьте -Steps"
    Add-Step "итог" "FAIL" 0 "СЛОМАН ЗАПУСК" ""
    if ($Json) { [pscustomobject]@{ ok = $false; code = $Code_Broken; verdict = "СЛОМАН ЗАПУСК"; steps = @([pscustomobject]@{ id = "preflight"; status = "FAIL"; seconds = 0; detail = "неизвестный шаг: $($badSteps -join ', ')"; hint = "поправьте -Steps" }) } | ConvertTo-Json -Depth 6 }
    exit $Code_Broken
}
if ($Zip -and -not (Test-Path $Zip)) {
    Add-Step "preflight" "FAIL" 0 "нет файла -Zip $Zip" "код 4: укажите существующий архив моделей"
    if ($Json) { [pscustomobject]@{ ok = $false; code = $Code_Broken; verdict = "СЛОМАН ЗАПУСК"; steps = @([pscustomobject]@{ id = "preflight"; status = "FAIL"; seconds = 0; detail = "нет файла -Zip $Zip"; hint = "укажите существующий архив" }) } | ConvertTo-Json -Depth 6 }
    exit $Code_Broken
}
$py = Find-Py315 $Python
if (-not $py) {
    $blockers += "нет Python 3.15 x64: winget install --id Python.Python.3.15 -e --accept-package-agreements, без winget — " +
                 "https://www.python.org/ftp/python/3.15.2/python-3.15.2-amd64.exe (/quiet InstallAllUsers=0 PrependPath=1); не даунгрейдить до 3.12/3.13"
}
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Add-Step "preflight" "NOTE" 0 "git не найден в PATH" "winget install --id Git.Git -e, без winget — https://github.com/git-for-windows/git/releases/download/v2.56.1.windows.1/Git-2.56.1-64-bit.exe (/VERYSILENT)"
}
if ($env:OS -notlike "Windows*") { $blockers += "all.ps1 рассчитан на Windows (PowerShell 5.1+)" }
foreach ($f in @("scripts\setup.ps1", "scripts\unpack_models.py", "scripts\doctor.py", "requirements.txt",
                 "MCP-stanza-german\server.py", "MCP-stanza-german\mcp.json.example")) {
    if (-not (Test-Path (Join-Path $Root $f))) { Add-Step "preflight" "FAIL" 0 "нет $f" "клон неполный — обновите репозиторий" }
}
$free = Get-FreeGB $Root
if ($free -ge 0 -and $free -lt $MinFreeGB) { $blockers += "на диске $free ГБ, просим >= $MinFreeGB ГБ (venv ~1 + модели 1.6 + кэш pip)" }
$gh = $null
$paths = $null
$depsOk = $false
if ($py) {
    $paths = Probe-Paths $py
    $depsOk = Test-Deps $VenvPy
    $gh = Test-Gh $py
    if (-not $gh.ok) {
        Add-Step "preflight" "NOTE" 0 ("gh: $($gh.why) — для установки не нужен (репозиторий публичный)") "для push: gh auth login + gh auth setup-git (УСТАНОВКА.md §1.2)"
    }
    if ($want -contains "deps" -and -not $DryRun -and -not $CheckOnly) {
        $bad = Test-Net
        if ($bad) { $blockers += ("нет доступа к " + ($bad -join ", ") + " (порт 443, прокси: HTTPS_PROXY)") }
    }
}
if ($blockers.Count) {
    foreach ($b in $blockers) { Add-Step "preflight" "BLOCK" 0 $b "нужен человек" }
    $code = $Code_Human
} elseif ($done | Where-Object { $_.status -eq "FAIL" }) {
    $code = $Code_Broken
} else {
    $det = "python $py; диск $free ГБ; gh: $($gh.why); пакеты: " + $(if ($depsOk) { "в .venv есть" } else { "нет" })
    if ($paths) { $det += "; модели: " + $(if ($paths.depparse) { "есть" } else { "нет" }) }
    Add-Step "preflight" "OK" ([math]::Round(((Get-Date) - $t0).TotalSeconds, 1)) $det ""
    $code = 0
}

# ------------------------------------------------------------------ шаги

if ($code -eq 0) {
    # 1+2. venv и зависимости — силами setup.ps1 (свою логику не дублируем)
    if ($want -contains "venv" -or $want -contains "deps") {
        $a = @("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $Root "scripts\setup.ps1"))
        if ($Python) { $a += @("-Python", $Python) }
        if ($DryRun) { $a += "-DryRun" }
        if ($want -notcontains "deps" -or (Test-Deps $VenvPy)) { $a += "-SkipDeps"; Add-Step "deps" "SKIP" 0 "пакеты уже стоят" "" }
        $rc = Run-Cmd $a[0] @($a[1..($a.Count - 1)]) "setup" "setup.ps1 упал: pip/сеть; повторите, при нехватке места — очистите кэш pip" (-not $DryRun -and -not $CheckOnly)
        if ($rc -ne 0) { $code = $Code_Step }
    }

    # 3. модели: локальный архив -> официальная загрузка Stanford (stanza.download)
    if ($code -eq 0 -and $want -contains "models") {
        $pyFor = $(if (Test-Path $VenvPy) { $VenvPy } else { $py })
        $haveModels = $true
        if ($paths) { $haveModels = $paths.depparse }
        if ($haveModels -and -not $Zip) {
            Add-Step "models" "SKIP" 0 "модели de уже в кэше ($($paths.model))" ""
        } else {
            $local = if ($Zip) { $Zip } else { (Get-ChildItem (Join-Path $Root "stanza-models-de-*.zip") -ErrorAction SilentlyContinue | Select-Object -First 1).FullName }
            if ($local -and (Test-Path $local)) {
                $rc = Run-Cmd $pyFor @((Join-Path $Root "scripts\unpack_models.py"), "--zip", $local, "--check") "models" "распаковка не вышла на 52/52: проверьте .sha256 рядом с архивом" (-not $DryRun -and -not $CheckOnly)
            } elseif ($CheckOnly -or $DryRun) {
                $rc = 0
                Add-Step "models" "plan" 0 "локального архива нет — модели качает stanza.download (huggingface.co + stanza-resources)" ""
            } elseif (Test-Deps $VenvPy) {
                $dl = "import stanza; stanza.download('de', verbose=False); print('модели de скачаны')"
                $rc = Run-Cmd $VenvPy @("-c", $dl) "models" "stanza.download не отдаёт модели: huggingface.co и raw.githubusercontent.com должны быть доступны (порт 443)" $true
            } else {
                $rc = 1
                Add-Step "models" "BLOCK" 0 "нет локального архива моделей, а пакеты (stanza) ещё не установлены" "сначала шаг deps, затем модели: stanza.download('de') или unpack_models.py --zip <архив>"
            }
            if ($rc -ne 0 -and $code -eq 0) { $code = $Code_Step }
        }
    }

    # 4. конфиг MCP-клиента: его создаёт человек — мы печатаем готовый фрагмент и проверяем запись
    if ($code -eq 0 -and $want -contains "mcp") {
        $pyFor = $(if (Test-Path $VenvPy) { $VenvPy } else { $py })
        $cfgPath = if ($McpConfig) { $McpConfig } else { Join-Path $env:USERPROFILE ".lmstudio\mcp.json" }
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
        Say "MCP-конфиг: $cfgPath (создаёт человек; образец — MCP-stanza-german\mcp.json.example)"
        Say "вставь в секцию `"$McpKey`":"
        foreach ($l in ($mcpSnippet -split "`n")) { Say ("  " + $l) }
        if ($found) {
            # запись есть — но клиент её не запустит, если enabled:false или command — python без пакетов
            $on = $true
            if ($srv.PSObject.Properties['enabled'] -and $srv.enabled -is [bool]) { $on = $srv.enabled }
            $cmd = [string]$srv.command
            if (-not $on) {
                Add-Step "mcp" "BLOCK" 0 "в $cfgPath запись stanza-german есть, но enabled: false" "поставь `"enabled": true" (или убери поле) и перезапусти клиент — иначе сервер не стартует"
                $code = $Code_Human
            } elseif ($cmd -and -not (Test-Path $cmd)) {
                if (Test-Path $VenvPy) {
                    Add-Step "mcp" "BLOCK" 0 "command в конфиге не найден: $cmd" "правь command на $pyFor (venv уже есть) и перезапусти клиент"
                    $code = $Code_Human
                } else {
                    Add-Step "mcp" "NOTE" 0 "command в конфиге = $cmd, на этой машине его нет" "установка не сделана: после шага venv поставь command = $pyFor и перезапусти клиент"
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
            $code = $Code_Human
        }
    }

    # 5. doctor — финальная проверка (тяжёлую приёмку с F1 не запускаем: см. УСТАНОВКА.md)
    if ($code -eq 0 -and $want -contains "doctor") {
        $pyFor = $(if (Test-Deps $VenvPy) { $VenvPy } else { $py })
        $a = @((Join-Path $Root "scripts\doctor.py"))
        if ($CheckOnly) { $a += "--soft-models" }
        $rc = Run-Cmd $pyFor $a "doctor" "doctor нашёл FAIL: список и лечение — УСТАНОВКА.md (окружение: setup.ps1, модели: unpack_models.py)" (-not $DryRun)
        if ($rc -ne 0 -and $code -eq 0) { $code = $Code_Step }
    }
}

# ------------------------------------------------------------------ итог

$verdict = @{ 0 = "ГОТОВО"; 2 = "НУЖЕН ЧЕЛОВЕК"; 3 = "ШАГ УПАЛ"; 4 = "СЛОМАН ЗАПУСК" }[$code]
$lastStep = ($done | Where-Object { $_.status -eq "FAIL" -or $_.status -eq "BLOCK" } | Select-Object -First 1)
Say ""
Say ("итог: $verdict (код $code)" + $(if ($lastStep) { " — " + $lastStep.id + ": " + $lastStep.detail + "; " + $lastStep.hint } else { "" })) $(if ($code -eq 0) { "Green" } else { "Red" })
if (-not $CheckOnly -and -not $DryRun -and $code -eq 0) {
    Say "приёмка (F1 0.777 / 0.686, 52/52) отдельными командами — см. таблицу приёмки в УСТАНОВКА.md"
}
Say ("лог: $Log")

if ($Json) {
    # PS 5.1 ломается на ConvertTo-Json у List[object] из OrderedDictionary — разворачиваем в pscustomobject
    $stepArr = @($done | ForEach-Object { [pscustomobject]@{ id = $_.id; status = $_.status; seconds = $_.seconds; detail = $_.detail; hint = $_.hint } })
    [pscustomobject]@{
        ok = ($code -eq 0); code = $code; verdict = $verdict; root = $Root
        mode = $(if ($CheckOnly) { "check-only" } elseif ($DryRun) { "dry-run" } else { "install" })
        python = $py; freeGB = $free; gh = $(if ($gh) { $gh.why }); mcp_snippet = $mcpSnippet
        steps = $stepArr; plan = [string[]]($plan | ForEach-Object { "$_" })
    } | ConvertTo-Json -Depth 6
}
try { [IO.File]::AppendAllText($Log, (($logLines -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding $false)) } catch { }
exit $code
