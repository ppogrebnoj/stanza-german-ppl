#Requires -Version 5.1
<#
    all.ps1 — внутренний оркестратор установки (контракт v2).
    Публичная точка входа — корневой install.ps1; он пробрасывает параметры без изменений.

        powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Yes
        .\install.ps1 -Check inventory -Json
        .\install.ps1 -Acceptance -Json -ProgressJson

    Режимы -Check только читают: не пишут файлы, реестр и окружение пользователя.
    Коды: 0 готово (MCP-registration — одно действие человека в next_action),
          2 нужен человек (blockers[].fix_cmd), 3 шаг упал (retryable),
          4 ошибка скрипта/среды/неизвестный параметр, 6 нужна перезагрузка/перелогин.

    Все создаваемые файлы лежат в -ArtifactDir (по умолчанию .tmp) под фиксированными
    именами: install.log, install-report.json, install-report-<UTC>.json, progress.ndjson,
    downloads\, mcp-snippet.json (+ копия в корне проекта).
#>
[CmdletBinding()]
param(
    [switch]$Yes,
    [string]$Check = '',
    [switch]$Acceptance,
    [switch]$Json,
    [switch]$ProgressJson,
    [string]$ArtifactDir = '',
    [string]$Python = '',
    [string]$TargetDir = '',
    [string]$ModelsDir = '',
    [string]$Models = '',
    [string]$OfflineKit = '',
    [string]$Steps = '',
    [switch]$Resume,
    [switch]$Venv,
    [switch]$Force,
    [switch]$Repair,
    [switch]$Uninstall,
    [switch]$Update,
    [switch]$CheckUpdates,
    [switch]$RaisePython,
    [switch]$MakeOfflineKit,
    [int]$Retries = 4,
    # совместимость со старыми ключами (см. docs/flags.json)
    [switch]$Inventory,
    [switch]$InventoryOnly,
    [switch]$CheckOnly,
    [switch]$DryRun,
    [string]$Zip = '',
    [string]$Log = '',
    [switch]$Help,
    [Parameter(ValueFromRemainingArguments = $true)][object[]]$Rest
)

$ErrorActionPreference = 'Continue'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Code_Ready = 0; $Code_Human = 2; $Code_Step = 3; $Code_Broken = 4; $Code_Reboot = 6

function Say { param([string]$Text, $Color)
    if ($Json) { return }
    if ($Color) { Write-Host $Text -ForegroundColor $Color } else { Write-Host $Text }
}
function Emit-Json { param($Object)
    if ($Object -is [string]) { [Console]::Out.WriteLine($Object) }
    else { [Console]::Out.WriteLine(($Object | ConvertTo-Json -Depth 12)) }
}

# ------------------------------------------------------------------ загрузка библиотек
$libOk = $true
foreach ($lib in @('_env.ps1', '_download.ps1', '_state.ps1', 'progress.ps1')) {
    $p = Join-Path $PSScriptRoot $lib
    if (-not (Test-Path -LiteralPath $p)) { $libOk = $false; continue }
    try { . $p } catch { $libOk = $false }
}
$global:KI_LIB_ONLY = $true
$invPath = Join-Path $PSScriptRoot 'inventory.ps1'
if (Test-Path -LiteralPath $invPath) { try { . $invPath } catch { $libOk = $false } } else { $libOk = $false }
foreach ($fn in @('Get-MachineArch', 'Find-Python', 'Get-PythonInfo', 'Get-StanzaResourcesDir',
                  'Invoke-Download', 'Initialize-Artifacts', 'Release-Artifacts', 'Write-Step',
                  'Open-ProgressLog', 'Close-ProgressLog', 'Get-Inventory', 'Save-Report')) {
    if (-not (Test-Path "function:$fn")) { $libOk = $false }
}
if (-not $libOk) {
    Say 'СЛОМАН ЗАПУСК: не загрузились модули установщика (scripts\_env.ps1, _download.ps1, _state.ps1, progress.ps1, inventory.ps1)' Red
    if ($Json) { Emit-Json ([pscustomobject][ordered]@{ schema_version = 2; code = $Code_Broken; ok = $false; failures = @([pscustomobject]@{ id = 'modules'; detail = 'не загрузились модули установщика'; retryable = $false }) }) }
    exit $Code_Broken
}

# ------------------------------------------------------------------ параметры и реестр флагов
$flagsPath = Join-Path $Root 'docs\flags.json'
$flagsReg = $null
if (Test-Path -LiteralPath $flagsPath) {
    try { $flagsReg = (Get-Content -LiteralPath $flagsPath -Raw -Encoding UTF8 | ConvertFrom-Json) } catch { }
}
$allowed = @()
if ($flagsReg) { $allowed = @($flagsReg.flags | ForEach-Object { $_.name }) }
else { $allowed = @('Yes','Check','Acceptance','Json','ProgressJson','ArtifactDir','Python','TargetDir','ModelsDir','Models','OfflineKit','Steps','Resume','Venv','Force','Repair','Uninstall','Update','CheckUpdates','RaisePython','MakeOfflineKit','Retries','Inventory','InventoryOnly','CheckOnly','DryRun','Zip','Log','Help') }

$badArgs = @()
foreach ($r in @($Rest)) {
    $s = "$r"
    if ($s -like '-*' -and $s -notlike '--*') {
        $n = $s.TrimStart('-')
        if ($allowed -notcontains $n) { $badArgs += $n }
    }
}
if ($badArgs.Count) {
    $msg = 'неизвестный параметр: ' + (($badArgs | Select-Object -Unique) -join ', ')
    Say "СЛОМАН ЗАПУСК: $msg (код 4)" Red
    if ($Json) { Emit-Json ([pscustomobject][ordered]@{ schema_version = 2; code = $Code_Broken; ok = $false; arch = (Get-MachineArch); failures = @([pscustomobject]@{ id = 'params'; detail = $msg; retryable = $false }) }) }
    exit $Code_Broken
}

$mode = 'install'
if ($Inventory -or $InventoryOnly) { $Check = 'inventory' }
if ($CheckOnly) { $Check = 'ready' }
if ($DryRun) { $Check = 'plan' }
if ($Zip -and -not $OfflineKit) { $OfflineKit = $Zip }
if ($Log -and -not $ArtifactDir) { $ArtifactDir = (Split-Path -Parent $Log) }
if ($Repair) { $mode = 'repair' }
if ($Uninstall) { $mode = 'uninstall' }
if ($Update) { $mode = 'update' }
if ($CheckUpdates) { $mode = 'check-updates'; $Check = '' }
if ($RaisePython) { $mode = 'raise-python'; $Check = '' }
if ($MakeOfflineKit) { $mode = 'make-offline-kit'; $Check = '' }
$checkModes = @('inventory', 'ready', 'plan', 'mcp', 'status', 'capabilities')
$checkMode = ''
if ($Check) { $checkMode = "$Check".ToLowerInvariant() }
if ($checkMode) {
    $mode = "check-$checkMode"
    if ($checkModes -notcontains $checkMode) {
        Say "СЛОМАН ЗАПУСК: неизвестная область -Check '$Check' (код 4)" Red
        if ($Json) { Emit-Json ([pscustomobject][ordered]@{ schema_version = 2; code = $Code_Broken; ok = $false; failures = @([pscustomobject]@{ id = 'params'; detail = "неизвестная область -Check: $Check"; retryable = $false }) }) }
        exit $Code_Broken
    }
}
$readOnly = $checkMode -ne ''

# ------------------------------------------------------------------ платформа
$arch = Get-MachineArch
if ($arch -ne 'AMD64' -or [IntPtr]::Size -ne 8) {
    $msg = "нужна Windows x64 (AMD64); текущая архитектура: $arch, шелл: $([IntPtr]::Size * 8) бит. Загрузки не начинались"
    Say "СЛОМАН ЗАПУСК: $msg" Red
    if ($Json) { Emit-Json ([pscustomobject][ordered]@{ schema_version = 2; code = $Code_Broken; ok = $false; arch = $arch; mode = $mode; failures = @([pscustomobject]@{ id = 'platform'; detail = $msg; retryable = $false; remedy = 'запустите 64-битный PowerShell на Windows x64' }) }) }
    exit $Code_Broken
}

$artifactDir = if ($ArtifactDir) { $ArtifactDir } else { Get-DefaultArtifactDir $Root }
$resources = Get-StanzaResourcesDir -Root $Root -ModelsDir $ModelsDir
$target = if ($TargetDir) { $TargetDir } else { Get-DefaultTargetDir }
$started = Get-Date
$stepResults = New-Object System.Collections.Generic.List[object]
$blockers = New-Object System.Collections.Generic.List[object]
$failures = New-Object System.Collections.Generic.List[object]
$nextAction = [ordered]@{ kind = ''; command = ''; snippet = '' }
$reportPath = ''
$snippetPath = ''
$pyInfo = $null
$py = ''
$acceptance = $null
$mcpRegistration = 'human'
$mcpSnippetJson = ''
$serverStatus = ''

function Add-Blocker { param([string]$Component, [string]$Reason, [string]$FixCmd)
    $blockers.Add([pscustomobject]@{ component = $Component; reason = $Reason; fix_cmd = $FixCmd }) | Out-Null
    Say ("  БЛОКЕР [{0}] {1}; fix: {2}" -f $Component, $Reason, $FixCmd) Yellow
}
function Add-Failure { param([string]$Id, [string]$Detail, [bool]$Retryable, [string]$Remedy)
    $failures.Add([pscustomobject]@{ id = $Id; detail = $Detail; retryable = $Retryable; remedy = $Remedy }) | Out-Null
}
function New-Step { param([string]$Id, [string]$Status = 'OK', [double]$Seconds = 0, [string]$Phase = '',
                          [int]$Rc = 0, [string]$Detail = '', [string]$Remedy = '', [bool]$Retryable = $false,
                          [string]$NextCmd = '', [long]$Bytes = 0)
    return [pscustomobject][ordered]@{
        id = $Id; status = $Status; seconds = $Seconds; phase = $Phase; rc = $Rc
        detail = $Detail; remedy = $Remedy; retryable = $Retryable; next_cmd = $NextCmd
        bytes = $Bytes; hint = $Remedy
    }
}
function Add-StepResult { param($Step)
    $stepResults.Add($Step) | Out-Null
    Say ("  [{0,-4}] {1,-12} {2}s {3}" -f $Step.status, $Step.id, $Step.seconds, $Step.detail)
    $state = 'ok'
    if ($Step.status -eq 'FAIL') { $state = 'fail' }
    elseif ($Step.status -eq 'SKIP') { $state = 'skip' }
    elseif ($Step.status -eq 'BLOCK') { $state = 'fail' }
    try { Write-Step -Step $Step.id -State $state -Seconds $Step.seconds -Msg ($Step.detail + ' ' + $Step.remedy).Trim() } catch { }
    if ($Step.status -eq 'FAIL') { Add-Failure -Id $Step.id -Detail $Step.detail -Retryable $Step.retryable -Remedy $Step.remedy }
    if ($Step.status -eq 'BLOCK' -and $blockers.Count -eq $blockerCountBeforeStep) {
        Add-Blocker $Step.id $Step.detail $Step.remedy
    }
}

function Invoke-Logged {
    param([string]$Exe, [string[]]$Argv, [string]$Id, [switch]$NoLogOutput)
    $logFile = Join-Path $artifactDir ($Id + '.log')
    $enc = New-Object System.Text.UTF8Encoding($false)
    try { [IO.File]::AppendAllText($logFile, ("> $Exe " + ($Argv -join ' ') + "`n"), $enc) } catch { }
    $out = @()
    try {
        $prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
        $out = @(& $Exe @Argv 2>&1 | ForEach-Object { "$_" })
        $rc = $LASTEXITCODE
        $ErrorActionPreference = $prev
    } catch { $rc = 1; $out = @("$_") }
    if ($out.Count) {
        try { [IO.File]::AppendAllText($logFile, (($out -join "`n") + "`n"), $enc) } catch { }
        if (-not $NoLogOutput -and -not $Json) { foreach ($l in $out) { Say ('  | ' + $l) } }
    }
    if ($rc -eq $null) { $rc = 1 }
    return [int]$rc
}

# GUI-установщики (python.org, git-scm) возвращают управление сразу: ждём процессом.
function Invoke-Installer {
    param([string]$Exe, [string[]]$Argv, [string]$Id)
    $logFile = Join-Path $artifactDir ($Id + '.log')
    try { [IO.File]::AppendAllText($logFile, ("> $Exe " + ($Argv -join ' ') + "`n"), (New-Object System.Text.UTF8Encoding($false))) } catch { }
    try {
        $p = Start-Process -FilePath $Exe -ArgumentList $Argv -Wait -PassThru -NoNewWindow -ErrorAction Stop
        return [int]$p.ExitCode
    } catch {
        try { [IO.File]::AppendAllText($logFile, ("$_`n"), (New-Object System.Text.UTF8Encoding($false))) } catch { }
        return 1
    }
}

function Get-DirBytes { param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path)) { return [long]0 }
    try { return [long]((Get-ChildItem -LiteralPath $Path -Recurse -File -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum) } catch { return [long]0 }
}

function Get-NextCommand { param([string]$Id = '')
    $cmd = 'powershell -ExecutionPolicy Bypass -File .\install.ps1 -Resume'
    if ($Id) { $cmd += " -Steps $Id" }
    if ($Yes) { $cmd += ' -Yes' }
    return $cmd
}

function Test-EnvReady { param([object]$Info, [object]$Flags)
    $bad = @()
    if (-not $Info) { return @('нет Python 3.15 x64') }
    if (-not $Info.Usable) { $bad += "Python $($Info.Version) [$($Info.Reason)]: $($Info.Path)" }
    $pyExe = $Info.Path
    if ($Venv) {
        $vp = Join-Path $Root '.venv\Scripts\python.exe'
        if (Test-Path -LiteralPath $vp) { $pyExe = $vp } else { $bad += 'нет .venv (нужен -Venv)' }
    }
    if ($bad.Count) { return $bad }
    $code = @'
import importlib.metadata as M, pathlib, sys
lock = pathlib.Path(sys.argv[1])
miss = []
for line in lock.read_text(encoding="utf-8").splitlines():
    line = line.split("#", 1)[0].strip()
    if "=" not in line or not line[0].isalpha():
        continue
    name, want = line.split("==", 1)
    try: have = M.version(name).split("+", 1)[0]
    except Exception: miss.append(name + ":missing"); continue
    if have != want.strip(): miss.append(name + ":" + have + "!=" + want.strip())
print("\n".join(miss))
'@
    $tmpPy = Join-Path $artifactDir 'verify_deps.py'
    if (-not $readOnly -and -not (Test-Path -LiteralPath $tmpPy)) {
        [IO.File]::WriteAllText($tmpPy, $code, (New-Object System.Text.UTF8Encoding($false)))
    }
    $outFile = Join-Path $artifactDir 'deps_versions.txt'
    if ($readOnly) {
        $out = & $pyExe -c $code (Get-LockPath $Root) 2>$null
    } else {
        $null = & $pyExe $tmpPy (Get-LockPath $Root) > $outFile 2>&1
        $out = @(Get-Content -LiteralPath $outFile -ErrorAction SilentlyContinue)
    }
    if ($LASTEXITCODE -ne 0) { return @('не удалось проверить версии пакетов') }
    foreach ($m in @($out)) { if ("$m".Trim()) { $bad += "версия пакета: $m" } }
    return $bad
}

function Test-ModelsReady {
    param([string]$PyExe, [string]$Processors, [switch]$Load)
    if (-not $PyExe -or -not (Test-Path -LiteralPath $PyExe)) { return $false }
    $script = Join-Path $PSScriptRoot 'check_models.py'
    if (-not (Test-Path -LiteralPath $script)) { return $false }
    $oldRes = $env:STANZA_RESOURCES_DIR; $oldUtf = $env:PYTHONUTF8
    try {
        $env:STANZA_RESOURCES_DIR = $resources
        $env:PYTHONUTF8 = '1'
        $a = @($script, '--processors', $Processors, '--json')
        if ($Load) { $a += '--load' }
        $null = & $PyExe @a 2>$null
        $rc = $LASTEXITCODE
    } finally {
        $env:STANZA_RESOURCES_DIR = $oldRes; $env:PYTHONUTF8 = $oldUtf
    }
    return ($rc -eq 0)
}

# ------------------------------------------------------------------ режимы -Check (только чтение)
function Read-McpSnippet {
    $p = Join-Path $Root 'mcp-snippet.json'
    if (-not (Test-Path -LiteralPath $p)) { return [pscustomobject]@{ ok = $false; reason = "нет $p"; path = $p } }
    $bytes = [IO.File]::ReadAllBytes($p)
    if ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF) {
        return [pscustomobject]@{ ok = $false; reason = 'файл с BOM (нужен UTF-8 без BOM)'; path = $p }
    }
    $text = [Text.Encoding]::UTF8.GetString($bytes)
    try { $obj = $text | ConvertFrom-Json } catch {
        return [pscustomobject]@{ ok = $false; reason = 'не парсится JSON'; path = $p }
    }
    $srv = $null
    try { $srv = $obj.mcpServers.'stanza-german' } catch { }
    if (-not $srv) { return [pscustomobject]@{ ok = $false; reason = 'нет записи mcpServers."stanza-german"'; path = $p } }
    $cmd = [string]$srv.command
    if (-not $cmd -or -not (Test-Path -LiteralPath $cmd)) {
        return [pscustomobject]@{ ok = $false; reason = "command не найден: $cmd"; path = $p }
    }
    $envObj = $srv.env
    if (-not $envObj -or -not $envObj.PSObject.Properties['STANZA_RESOURCES_DIR'] -or -not $envObj.PSObject.Properties['PYTHONUTF8']) {
        return [pscustomobject]@{ ok = $false; reason = 'env без PYTHONUTF8 / STANZA_RESOURCES_DIR'; path = $p }
    }
    return [pscustomobject]@{ ok = $true; reason = 'snippet валиден'; path = $p; command = $cmd; snippet = $text }
}

function Invoke-CheckMode {
    param([string]$Area)
    $result = [ordered]@{ schema_version = 2; check = $Area; ok = $false; code = $Code_Ready; arch = $arch; mode = $mode }

    if ($Area -eq 'capabilities') {
        if (-not $flagsReg) { $result.code = $Code_Broken; $result.reason = 'нет docs/flags.json' }
        else { $result.ok = $true; $result.capabilities = $flagsReg }
        $result.code = $(if ($result.ok) { 0 } else { 4 })
        return $result
    }
    if ($Area -eq 'inventory') {
        $inv = Get-Inventory -Quiet -NoNetwork
        $result.inventory = $inv
        $bad = @($inv.items | Where-Object { $_.need -eq 'required' -and $_.status -notin @('OK','NOTE','ADMIN','USER','set','NOT_REQUIRED','SLOW') })
        $result.blockers = @($bad | ForEach-Object { [pscustomobject]@{ component = $_.name; reason = $_.status; fix_cmd = [string]$_.fix } })
        $result.ok = ($bad.Count -eq 0); $result.code = $(if ($result.ok) { 0 } else { 2 })
        if (-not $Json) {
            foreach ($l in @((Format-InvText $inv $false))) { Say $l }
            Say ("инвентаризация: блокирующих {0}, код {1}" -f $bad.Count, $result.code)
        }
        return $result
    }
    if ($Area -eq 'ready') {
        $info = Find-Python -Explicit $Python -TargetDir $target
        $pyExe = Get-InterpreterPath -PythonInfo $info -Root $Root -Venv:$Venv
        $bad = @()
        if (-not $info) { $bad += 'нет Python 3.15 x64' }
        elseif (-not $info.Usable) { $bad += "Python $($info.Version) [$($info.reason)]: $($info.Path)" }
        if (-not $bad.Count) { $bad += @(Test-EnvReady -Info $info -Flags $flagsReg) }
        $snippet = Read-McpSnippet
        if (-not $snippet.ok) { $bad += "MCP snippet: $($snippet.reason)" }
        $models = $false
        if (-not $bad.Count) { $models = Test-ModelsReady -PyExe $pyExe -Processors 'tokenize,mwt,pos,lemma,depparse' }
        if (-not $models -and -not $bad.Count) { $bad += 'модели Stanza (5 процессоров) не готовы' }
        $result.python_path = $pyExe
        $result.stanza_resources = $resources
        $result.mcp_snippet = $snippet.path
        $result.blockers = @($bad | ForEach-Object { [pscustomobject]@{ component = 'ready'; reason = $_; fix_cmd = (Get-NextCommand) } })
        $result.ok = ($bad.Count -eq 0)
        $result.code = $(if ($result.ok) { 0 } else { 2 })
        return $result
    }
    if ($Area -eq 'plan') {
        $info = Find-Python -Explicit $Python -TargetDir $target
        $badDeps = @()
        if ($info) { $badDeps = @(Test-EnvReady -Info $info -Flags $flagsReg) }
        $plan = @()
        foreach ($id in @('winget','python','git','deps','models','snippet','doctor')) {
            $need = $true; $why = ''
            switch ($id) {
                'python' { $need = -not $info -or -not $info.Usable; $why = $(if ($need) { '.python 3.15 x64' } else { 'python уже есть' }) }
                'deps'   { $need = $badDeps.Count -gt 0; $why = $(if ($need) { 'пакеты не сверены с lock' } else { 'пакеты готовы' }) }
                'models' { $need = -not $info -or -not (Test-ModelsReady -PyExe (Get-InterpreterPath -PythonInfo $info -Root $Root -Venv:$Venv) -Processors 'tokenize,mwt,pos,lemma,depparse'); $why = $(if ($need) { 'нет 5 процессоров' } else { 'модели готовы' }) }
                'snippet' { $need = -not (Read-McpSnippet).ok; $why = 'создать mcp-snippet.json (_registration человек)' }
                'doctor' { $need = $true; $why = 'проверка doctor.py' }
                'winget' { $need = -not (Get-Command winget -ErrorAction SilentlyContinue); $why = 'проверить winget' }
                'git' { $need = -not (Get-Command git -ErrorAction SilentlyContinue); $why = 'проверить git' }
            }
            $plan += [pscustomobject]@{ id = $id; status = $(if ($need) { 'PLAN' } else { 'SKIP' }); detail = $why }
        }
        $result.plan = $plan; $result.ok = $true; $result.code = 0
        return $result
    }
    if ($Area -eq 'mcp') {
        $s = Read-McpSnippet
        $result.snippet = $s
        $result.ok = $s.ok
        $result.code = $(if ($s.ok) { 0 } else { 2 })
        if (-not $s.ok) {
            $result.fix_cmd = 'powershell -ExecutionPolicy Bypass -File .\install.ps1 -Steps snippet'
            $result.hint = "Причина: $($s.reason). Сервер не видит конфиг клиента: добавьте запись stanza-german из mcp-snippet.json и перезапустите клиент."
        }
        return $result
    }
    if ($Area -eq 'status') {
        $p = Join-Path $artifactDir 'install-report.json'
        if (-not (Test-Path -LiteralPath $p)) {
            $result.ok = $false; $result.code = 2; $result.reason = "нет $p"; $result.fix_cmd = (Get-NextCommand)
            return $result
        }
        $r = Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json
        $result.report = $r
        $result.code = [int]$r.code; $result.ok = [bool]$r.ok
        return $result
    }
    return $result
}

if ($readOnly) {
    $res = Invoke-CheckMode $checkMode
    if ($Json) { Emit-Json $res }
    elseif ($checkMode -eq 'capabilities' -and $flagsReg) { Say 'реестр флагов: docs/flags.json' }
    $rc = [int]$res.code
    exit $rc
}

# ------------------------------------------------------------------ рабочий прогон (пишет артефакты)
try {
    $artifactDir = Initialize-Artifacts -ArtifactDir $artifactDir
} catch {
    Say "СЛОМАН ЗАПУСК: $_" Red
    if ($Json) { Emit-Json ([pscustomobject][ordered]@{ schema_version = 2; code = $Code_Step; ok = $false; failures = @([pscustomobject]@{ id = 'mutex'; detail = "$_"; retryable = $true; next_cmd = (Get-NextCommand) }) }) }
    exit $Code_Step
}
if (-not (Test-Path -LiteralPath $artifactDir)) { $artifactDir = (Resolve-Path -LiteralPath $artifactDir).Path }
$progressFile = Join-Path $artifactDir 'progress.ndjson'
$logFile = Join-Path $artifactDir 'install.log'
$stepIds = @('winget','python','git','deps','models','snippet','doctor','acceptance')
if ($Steps) {
    $want = @($Steps -split ',' | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })
    $badSteps = @($want | Where-Object { $stepIds -notcontains $_ })
    if ($badSteps.Count) {
        Say ('СЛОМАН ЗАПУСК: неизвестный шаг ' + ($badSteps -join ', ')) Red
        if ($Json) { Emit-Json ([pscustomobject][ordered]@{ schema_version = 2; code = $Code_Broken; ok = $false; failures = @([pscustomobject]@{ id = 'params'; detail = 'неизвестный шаг: ' + ($badSteps -join ', '); retryable = $false }) }) }
        Release-Artifacts; exit $Code_Broken
    }
    $stepIds = $want
}
if ($Acceptance -and $stepIds -notcontains 'acceptance') { $stepIds += 'acceptance' }
$env:PYTHONUTF8 = '1'
try {
    [Console]::OutputEncoding = [Text.Encoding]::UTF8
    $OutputEncoding = [Text.Encoding]::UTF8
} catch { }
Open-ProgressLog -Json:$Json -ProgressJson:$ProgressJson -LogPath $logFile -EventFile $progressFile -Steps $stepIds

Say "установка: $Root" Cyan
Say ("артефакты: $artifactDir; ресурсы Stanza: $resources")
$prevReport = $null
if ($Resume -and (Test-Path -LiteralPath (Join-Path $artifactDir 'install-report.json'))) {
    try { $prevReport = Get-Content -LiteralPath (Join-Path $artifactDir 'install-report.json') -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
}
function Get-PrevStep { param([string]$Id)
    if (-not $prevReport) { return $null }
    return @($prevReport.steps | Where-Object { $_.id -eq $Id } | Select-Object -Last 1)
}

# реестр флагов — CI-контракт: вывод -Check capabilities совпадает с docs/flags.json
$planArr = @($stepIds | ForEach-Object { [pscustomobject]@{ id = $_; status = 'PLAN' } })

# ------------------------------------------------------------------ шаги
foreach ($id in $stepIds) {
    $t0 = Get-Date
    $prev = Get-PrevStep $id
    if ($Resume -and $prev -and @('OK','SKIP') -contains $prev.status) {
        Add-StepResult (New-Step -Id $id -Status 'SKIP' -Phase 'resume' -Detail "готово в previous run: $($prev.detail)" -Seconds 0)
        continue
    }
    Write-Step -Step $id -State 'start' -Msg $mode
    $blockerCountBeforeStep = $blockers.Count
    $result = $null
    try {
        switch ($id) {
            'winget' {
                $winget = Get-Command winget -ErrorAction SilentlyContinue
                if ($winget) {
                    $result = New-Step -Id $id -Phase 'preflight' -Status 'SKIP' -Detail 'winget уже установлен'
                } elseif (-not $Yes) {
                    Add-Blocker 'winget' 'winget (App Installer) не найден' 'winget: Install-Module Microsoft.WinGet.Client -Force -Repository PSGallery; Repair-WinGetPackageManager -AllUsers  (или запустите с -Yes)'
                    $result = New-Step -Id $id -Phase 'preflight' -Status 'BLOCK' -Detail 'winget не найден, -Yes не задан' -Remedy 'запустите с -Yes или установите App Installer вручную'
                } else {
                    $okBoot = $true; $detail = ''
                    try {
                        Import-Module Microsoft.WinGet.Client -Force -ErrorAction Stop
                        Repair-WinGetPackageManager -AllUsers -ErrorAction Stop
                    } catch { $okBoot = $false; $detail = "$_" }
                    if (-not $okBoot) {
                        $rc = Invoke-Logged -Exe 'powershell.exe' -Argv @('-NoProfile','-ExecutionPolicy','Bypass','-Command','Install-Module Microsoft.WinGet.Client -Force -Repository PSGallery; Repair-WinGetPackageManager -AllUsers') -Id 'winget-bootstrap'
                        $okBoot = ($rc -eq 0)
                    }
                    try { $env:Path = (@([Environment]::GetEnvironmentVariable('Path','Machine'), [Environment]::GetEnvironmentVariable('Path','User')) | Where-Object { $_ }) -join ';' } catch { }
                    if ($okBoot -and (Get-Command winget -ErrorAction SilentlyContinue)) {
                        $result = New-Step -Id $id -Phase 'install' -Detail 'winget установлен из PSGallery (Microsoft.WinGet.Client + Repair-WinGetPackageManager -AllUsers)'
                    } else {
                        # winget не обязателен: все компоненты ставятся прямыми ссылками
                        $result = New-Step -Id $id -Phase 'install' -Status 'SKIP' -Detail "winget недоступен ($detail); используется прямой путь установки" -Remedy 'проверьте App Installer и PSGallery; на установку это не влияет'
                    }
                }
            }
            'python' {
                $info = Find-Python -Explicit $Python -TargetDir $target
                if ($info -and $info.Usable) {
                    $pyInfo = $info; $py = $info.Path
                    $result = New-Step -Id $id -Phase 'preflight' -Status 'SKIP' -Detail "Python $($info.Version) x64: $($info.Path)"
                } elseif ($info) {
                    Add-Blocker 'python' "Python $($info.Version) непригоден: $($info.Reason) ($($info.Path))" 'удалите externally-managed интерпретатор или задайте -Python <путь к per-user Python 3.15.2 x64>'
                    $result = New-Step -Id $id -Phase 'preflight' -Status 'BLOCK' -Detail "Python: $($info.Reason)" -Remedy 'нужен per-user Python 3.15.2 x64 без PEP668'
                } elseif (-not $Yes) {
                    Add-Blocker 'python' 'нет Python 3.15.2 x64' "winget install --id Python.Python.3.15 -e; или запустите с -Yes (офлайн: python-3.15.2-amd64.exe /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1)"
                    $result = New-Step -Id $id -Phase 'preflight' -Status 'BLOCK' -Detail 'нет Python 3.15 x64, -Yes не задан' -Remedy 'запустите с -Yes'
                } else {
                    # SHA256 берём из манифеста winget-pkgs (InstallerSha256)
                    $hash = ''
                    $manifestUrls = @(
                        'https://raw.githubusercontent.com/microsoft/winget-pkgs/master/manifests/p/Python/Python/3.15/Python.Python.3.15.installer.yaml',
                        'https://raw.githubusercontent.com/microsoft/winget-pkgs/master/manifests/p/Python/Python/3.15/3.15.2/Python.Python.3.15.installer.yaml'
                    )
                    foreach ($mu in $manifestUrls) {
                        try {
                            $mf = (Invoke-WebRequest -Uri $mu -UseBasicParsing -TimeoutSec 20).Content
                            if ($mf -match '(?im)InstallerSha256:\s*([0-9a-fA-F]{64})') { $hash = $Matches[1].ToLowerInvariant(); break }
                        } catch { }
                    }
                    $url = 'https://www.python.org/ftp/python/3.15.2/python-3.15.2-amd64.exe'
                    $exe = Join-Path $artifactDir 'downloads\python-3.15.2-amd64.exe'
                    $dl = Invoke-Download -Url $url -Dest $exe -Sha256 $hash -Retries $Retries -DownloadDir (Join-Path $artifactDir 'downloads') -OnProgress { param($e)
                        if ($e.ev -eq 'progress') { Write-Progress2 -Step 'python' -Sub 'скачивание python.org' -Pct $e.pct }
                    }
                    if (-not $dl.ok) {
                        $result = New-Step -Id $id -Phase 'download' -Status 'FAIL' -Detail "не скачан Python: $($dl.detail)" -Retryable $true -Remedy 'проверьте HTTPS_PROXY/сеть; повторите с -Resume; SHA256 сверяется с winget-pkgs' -NextCmd (Get-NextCommand $id)
                    } else {
                        $args = @('/quiet','InstallAllUsers=0','PrependPath=1','Include_launcher=1','Include_test=0',("TargetDir=$target"))
                        $rc = Invoke-Installer -Exe $exe -Argv $args -Id 'python-install'
                        if ($rc -eq 0 -or $rc -eq 3010) {
                            try { $env:Path = (@([Environment]::GetEnvironmentVariable('Path','Machine'), [Environment]::GetEnvironmentVariable('Path','User')) | Where-Object { $_ }) -join ';' } catch { }
                            $info = Find-Python -Explicit (Join-Path $target 'python.exe') -TargetDir $target
                            if ($info -and $info.Usable) {
                                $pyInfo = $info; $py = $info.Path
                                $result = New-Step -Id $id -Phase 'install' -Status 'OK' -Detail "Python $($info.Version) установлен: $($info.Path); реестр/launcher/PATH перечитаны" -Bytes $dl.bytes -Rc $rc
                            } else {
                                $result = New-Step -Id $id -Phase 'verify' -Status 'FAIL' -Detail "установщик rc=$rc, но Python 3.15 x64 не найден по TargetDir/реестру/PATH" -Retryable $true -Remedy 'перелогиньтесь и повторите с -Resume' -NextCmd (Get-NextCommand $id) -Rc $rc -Bytes $dl.bytes
                            }
                        } else {
                            $result = New-Step -Id $id -Phase 'install' -Status 'FAIL' -Detail "установщик python.org вернул $rc" -Retryable $true -Remedy 'см. install.log в ArtifactDir; повторите с -Resume' -NextCmd (Get-NextCommand $id) -Rc $rc -Bytes $dl.bytes
                        }
                    }
                }
            }
            'git' {
                if (Get-Command git -ErrorAction SilentlyContinue) {
                    $result = New-Step -Id $id -Phase 'preflight' -Status 'SKIP' -Detail 'git уже установлен'
                } elseif (-not $Yes) {
                    Add-Blocker 'git' 'git не найден' 'winget install --id Git.Git -e; или запустите с -Yes'
                    $result = New-Step -Id $id -Phase 'preflight' -Status 'BLOCK' -Detail 'git не найден, -Yes не задан' -Remedy 'запустите с -Yes'
                } elseif (Get-Command winget -ErrorAction SilentlyContinue) {
                    $rc = Invoke-Logged -Exe 'winget.exe' -Argv @('install','--id','Git.Git','-e','--accept-package-agreements','--accept-source-agreements','--disable-interactivity') -Id 'git-install'
                    $result = if ($rc -eq 0) { New-Step -Id $id -Phase 'install' -Detail 'Git.Git установлен winget' }
                              else { New-Step -Id $id -Phase 'install' -Status 'FAIL' -Detail "winget Git.Git rc=$rc" -Retryable $true -Remedy 'повторите с -Resume или ставьте с git-scm.com' -NextCmd (Get-NextCommand $id) -Rc $rc }
                } else {
                    $url = 'https://github.com/git-for-windows/git/releases/download/v2.56.1.windows.1/Git-2.56.1-64-bit.exe'
                    $exe = Join-Path $artifactDir 'downloads\Git-2.56.1-64-bit.exe'
                    $dl = Invoke-Download -Url $url -Dest $exe -Retries $Retries -DownloadDir (Join-Path $artifactDir 'downloads')
                    if (-not $dl.ok) {
                        $result = New-Step -Id $id -Phase 'download' -Status 'FAIL' -Detail "git не скачан: $($dl.detail)" -Retryable $true -Remedy 'проверьте доступ к github.com; повторите с -Resume' -NextCmd (Get-NextCommand $id)
                    } else {
                        $rc = Invoke-Installer -Exe $exe -Argv @('/VERYSILENT','/NORESTART') -Id 'git-install'
                        $result = if ($rc -eq 0 -or $rc -eq 3010) { New-Step -Id $id -Phase 'install' -Detail 'Git установлен с git-scm.com' -Bytes $dl.bytes }
                                  else { New-Step -Id $id -Phase 'install' -Status 'FAIL' -Detail "установщик Git вернул $rc" -Retryable $true -Remedy 'повторите с -Resume' -Rc $rc -NextCmd (Get-NextCommand $id) }
                    }
                }
                # ZIP-копия без .git: init + origin + fetch + reset --mixed + pre-commit hook
                if ($result.status -eq 'OK' -and (Test-Path (Join-Path $Root '.git')) -eq $false) {
                    if (-not $Force) {
                        $result = New-Step -Id $id -Phase 'git-init' -Status 'BLOCK' -Detail 'ZIP-копия: нет .git, нужен -Force для init/fetch/reset --mixed' -Remedy 'запустите с -Force -Yes (или сделайте git clone)'
                        Add-Blocker 'git-repo' 'ZIP-копия не превращена в репозиторий' 'powershell -ExecutionPolicy Bypass -File .\install.ps1 -Steps git -Force -Yes'
                    } else {
                        # Invoke-Logged не умеет конвейеры: выполняем по шагам
                        $rcAll = 0
                        foreach ($ga in @(@('init','-b','master','.'), @('remote','add','origin','https://github.com/ppogrebnoj/stanza-german-ppl.git'), @('fetch','origin','master'), @('reset','--mixed','FETCH_HEAD'))) {
                            $rcOne = Invoke-Logged -Exe 'git.exe' -Argv $ga -Id 'git-repo'
                            if ($rcOne -ne 0 -and $ga[0] -ne 'remote') { $rcAll = $rcOne; break }
                        }
                        $hookSrc = Join-Path $Root 'правило\git-hooks\pre-commit'
                        $hookDst = Join-Path $Root '.git\hooks\pre-commit'
                        if ($rcAll -eq 0 -and (Test-Path -LiteralPath $hookSrc)) {
                            $text = [IO.File]::ReadAllText($hookSrc) -replace "`r`n", "`n"
                            [IO.File]::WriteAllText($hookDst, $text, (New-Object System.Text.UTF8Encoding($false)))
                        }
                        $result = New-Step -Id $id -Phase 'git-init' -Rc $rcAll -Detail 'ZIP-копия: init/origin/fetch/reset --mixed + pre-commit hook' -Status $(if ($rcAll -eq 0) { 'OK' } else { 'FAIL' }) -Retryable ($rcAll -ne 0) -NextCmd (Get-NextCommand $id)
                    }
                }
            }
            'deps' {
                $info = Find-Python -Explicit $Python -TargetDir $target
                if ($info -and $info.Usable) { $pyInfo = $info; $py = $info.Path }
                if (-not $info -or -not $info.Usable) {
                    $result = New-Step -Id $id -Phase 'preflight' -Status 'BLOCK' -Detail 'нет пригодного Python 3.15 x64' -Remedy 'сначала шаг python; fix_cmd: winget install --id Python.Python.3.15 -e'
                } else {
                    $py = $info.Path
                    if ($Venv) {
                        $vp = Join-Path $Root '.venv\Scripts\python.exe'
                        if (-not (Test-Path -LiteralPath $vp)) {
                            $rc = Invoke-Logged -Exe $py -Argv @('-m','venv',(Join-Path $Root '.venv')) -Id 'venv'
                            if ($rc -ne 0) {
                                $result = New-Step -Id $id -Phase 'venv' -Status 'FAIL' -Detail "создание .venv rc=$rc" -Retryable $true -Remedy 'проверьте Python 3.15 x64 и место на диске' -Rc $rc -NextCmd (Get-NextCommand $id)
                            }
                        }
                        if (Test-Path -LiteralPath $vp) { $py = $vp }
                    }
                    if (-not $result) {
                        $lock = Get-LockPath $Root
                        $dry = @('-m','pip','install','--dry-run','--only-binary=:all:','--disable-pip-version-check','-r',$lock)
                        $rcDry = Invoke-Logged -Exe $py -Argv $dry -Id 'deps-dry-run'
                        if ($rcDry -ne 0) {
                            $logText = Get-Content -LiteralPath (Join-Path $artifactDir 'deps-dry-run.log') -Raw -ErrorAction SilentlyContinue
                            $sd = ''
                            if ("$logText" -match '(?im)Building wheel for ([A-Za-z0-9_.\-]+)') { $sd = $Matches[1] }
                            elseif ("$logText" -match '(?im)package has no wheels|sdist') { $sd = 'sm-package' }
                            $fix = if ($sd) { "обновите пин $sd в requirements.lock до версии с колесом cp315-win_amd64 (например PyYAML 6.0.4; 6.0.3 колеса нет): python -m pip index versions $sd; python -m pip download --only-binary=:all: $sd" } else { 'проверьте requirements.lock и доступ к PyPI' }
                            Add-Blocker 'deps' "dry-run --only-binary=:all: нашёл sdist: $sd" $fix
                            $result = New-Step -Id $id -Phase 'dry-run' -Status 'BLOCK' -Detail "dry-run rc=$rcDry (sdist: $sd)" -Remedy $fix -Rc $rcDry
                        } else {
                            $rc = Invoke-Logged -Exe $py -Argv @('-m','pip','install','--only-binary=:all:','--retries',"$Retries",'--timeout','60','--disable-pip-version-check','-r',$lock) -Id 'deps'
                            if ($rc -eq 0) {
                                $null = & $py -m pip check > (Join-Path $artifactDir 'pip-check.txt') 2>&1
                                $rcCheck = $LASTEXITCODE
                                if ($rcCheck -ne 0) {
                                    $result = New-Step -Id $id -Phase 'verify' -Status 'FAIL' -Detail "pip check rc=$rcCheck (конфликт версий)" -Retryable $false -Remedy 'сверьте requirements.lock; исправьте конфликт и повторите' -Rc $rcCheck -NextCmd (Get-NextCommand $id)
                                } else {
                                    $bad = @(Test-EnvReady -Info $info -Flags $flagsReg)
                                    $result = New-Step -Id $id -Phase 'verify' -Detail 'pip dry-run + install (--only-binary=:all:) + pip check + сверка версий с lock: OK' -Bytes (Get-DirBytes (Join-Path $Root '.venv'))
                                    if ($bad.Count) { $result = New-Step -Id $id -Phase 'verify' -Status 'FAIL' -Detail ('версии после установки не сошлись с lock: ' + ($bad -join '; ')) -Retryable $true -Remedy 'pip install --force-reinstall -r requirements.lock --only-binary=:all:' -NextCmd (Get-NextCommand $id) }
                                }
                            } else {
                                $result = New-Step -Id $id -Phase 'install' -Status 'FAIL' -Detail "pip install rc=$rc" -Retryable $true -Remedy 'сетевой сбой/прокси/нет колеса: повторите с -Resume; подробности в install.log' -NextCmd (Get-NextCommand $id) -Rc $rc
                            }
                        }
                    }
                }
            }
            'models' {
                $info = Find-Python -Explicit $Python -TargetDir $target
                if ($info -and $info.Usable) { $pyInfo = $info; $py = $info.Path }
                $pyFor = Get-InterpreterPath -PythonInfo $info -Root $Root -Venv:$Venv
                if (-not $info -or -not (Test-Path -LiteralPath $pyFor)) {
                    $result = New-Step -Id $id -Phase 'preflight' -Status 'BLOCK' -Detail 'нет интерпретатора для загрузки моделей' -Remedy 'сначала шаг python и deps'
                } else {
                    $env:STANZA_RESOURCES_DIR = $resources
                    $env:PYTHONUTF8 = '1'
                    $base = 'tokenize,mwt,pos,lemma,depparse'
                    $extra = @()
                    if ($Models) {
                        if ($Models -eq 'all') { $extra = @('ner','sentiment') }
                        else { $extra = @($Models -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ -and $_ -notin ($base -split ',') }) }
                    }
                    $processors = (($base -split ',') + $extra) -join ','
                    $checker = Join-Path $PSScriptRoot 'check_models.py'
                    $needDownload = $true
                    if (Test-Path -LiteralPath $checker) {
                        $env:STANZA_RESOURCES_DIR = $resources
                        $null = & $pyFor $checker --processors $processors --json > (Join-Path $artifactDir 'models-check-before.json') 2>&1
                        $needDownload = ($LASTEXITCODE -ne 0)
                    }
                    if (-not $needDownload) {
                        $result = New-Step -Id $id -Phase 'preflight' -Status 'SKIP' -Detail "модели готовы: $resources (5+ процессоров)"
                    } elseif ($OfflineKit -and (Test-Path -LiteralPath $OfflineKit)) {
                        $offArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'offline_kit.ps1'),'-Action','unpack','-Archive',$OfflineKit,'-TargetDir',$Root,'-ModelsDir',$resources)
                        if ($Force) { $offArgs += '-Force' }
                        $rc = Invoke-Logged -Exe 'powershell.exe' -Argv $offArgs -Id 'offline-unpack'
                        $result = if ($rc -eq 0) { New-Step -Id $id -Phase 'offline' -Detail "модели распакованы из офлайн-набора $OfflineKit" } else { New-Step -Id $id -Phase 'offline' -Status 'FAIL' -Detail "распаковка rc=$rc" -Retryable $false -Remedy 'проверьте архив и его .sha256' -Rc $rc }
                    } else {
                        $dlOk = $false; $dlDetail = ''
                        for ($i = 1; $i -le [math]::Max(1,$Retries); $i++) {
                            $pre = Test-DownloadPreflight -Url 'https://raw.githubusercontent.com/stanfordnlp/stanza-resources/main/resources_1.15.0.json'
                            if (-not $pre.ok) { $dlDetail = "ресурсы Stanza недоступны (HTTP $($pre.code))" }
                            $pyCode = "import stanza; stanza.download('de', processors='$processors', verbose=False)"
                            $rc = Invoke-Logged -Exe $pyFor -Argv @('-c',$pyCode) -Id "models-attempt-$i"
                            if ($rc -eq 0) { $dlOk = $true; break }
                            $dlDetail = "stanza.download rc=$rc (попытка $i/$Retries)"
                            if ($i -lt $Retries) { Write-Progress2 -Step $id -Sub "повтор $i/$Retries" -Msg $dlDetail; Start-Sleep -Seconds 10 }
                        }
                        if (-not $dlOk) {
                            $result = New-Step -Id $id -Phase 'download' -Status 'FAIL' -Detail $dlDetail -Retryable $true -Remedy 'TLS-reset/10054: проверьте HTTPS_PROXY/HF_ENDPOINT и повторите с -Resume; или используйте -OfflineKit' -NextCmd (Get-NextCommand $id)
                        } else {
                            $result = New-Step -Id $id -Phase 'download' -Detail "stanza.download('de', processors='$processors') + манифест" -Bytes (Get-DirBytes $resources)
                        }
                    }
                    if ($result.status -eq 'OK') {
                        $null = & $pyFor $checker --processors $processors --json --load > (Join-Path $artifactDir 'models-check-after.json') 2>&1
                        if ($LASTEXITCODE -ne 0) {
                            $result = New-Step -Id $id -Phase 'verify' -Status 'FAIL' -Detail 'манифест процессоров/pipeline не прошёл проверку' -Retryable $true -Remedy 'удалите повреждённые файлы моделей (нужен -Force) и повторите загрузку' -NextCmd (Get-NextCommand $id)
                        }
                    }
                }
            }
            'snippet' {
                $info = Find-Python -Explicit $Python -TargetDir $target
                if ($info -and $info.Usable) { $pyInfo = $info; $py = $info.Path }
                $pyFor = Get-InterpreterPath -PythonInfo $info -Root $Root -Venv:$Venv
                if (-not $pyFor) {
                    $result = New-Step -Id $id -Phase 'preflight' -Status 'BLOCK' -Detail 'нет python для command в mcp-snippet.json' -Remedy 'сначала шаг python'
                } else {
                    $entry = [ordered]@{
                        command = $pyFor
                        args = @((Join-Path $Root 'MCP-stanza-german\server.py'))
                        # RULE_ROOT сервер определяет сам; env содержит только нужные переменные
                        env = [ordered]@{ PYTHONUTF8 = '1'; STANZA_RESOURCES_DIR = $resources }
                    }
                    $obj = [ordered]@{ mcpServers = [ordered]@{ 'stanza-german' = $entry } }
                    $mcpSnippetJson = $obj | ConvertTo-Json -Depth 6
                    $snippetPath = Save-McpSnippet -ArtifactDir $artifactDir -Root $Root -Json $mcpSnippetJson
                    $valid = Read-McpSnippet
                    # шим use.ps1 / python.cmd: абсолютный путь + переменные процесса
                    $use = "@echo off`r`n`$env:PYTHONUTF8='1'`r`n`$env:STANZA_RESOURCES_DIR='$resources'`r`n`"$pyFor`" %*`r`n"
                    [IO.File]::WriteAllText((Join-Path $Root 'python.cmd'), $use, (New-Object System.Text.ASCIIEncoding))
                    $usePs = "`$env:PYTHONUTF8='1'`r`n`$env:STANZA_RESOURCES_DIR='$resources'`r`n& '$pyFor' @args`r`n"
                    [IO.File]::WriteAllText((Join-Path $Root 'use.ps1'), $usePs, (New-Object System.Text.UTF8Encoding($false)))
                    $serverCheck = $null
                    $serverScript = Join-Path $PSScriptRoot 'server_check.py'
                    if (Test-Path -LiteralPath $serverScript) {
                        $null = & $pyFor $serverScript --json > (Join-Path $artifactDir 'server-check.json') 2>&1
                        if ($LASTEXITCODE -eq 0) {
                            try { $sc = Get-Content -LiteralPath (Join-Path $artifactDir 'server-check.json') -Raw -Encoding UTF8 | ConvertFrom-Json; $serverStatus = $sc.rule_status } catch { }
                        }
                    }
                    $nextAction.kind = 'mcp_registration'
                    $nextAction.command = ''
                    $nextAction.snippet = $mcpSnippetJson
                    $nextAction.hint = "Добавьте запись stanza-german из $snippetPath в конфиг MCP-клиента и перезапустите клиент"
                    $result = if ($valid.ok) {
                        New-Step -Id $id -Phase 'verify' -Detail "mcp-snippet.json создан и проверен ($snippetPath); сервер: $serverStatus" -Remedy 'запись в конфиг клиента выполняет человек (next_action)'
                    } else {
                        New-Step -Id $id -Phase 'verify' -Status 'FAIL' -Detail "snippet не прошёл проверку: $($valid.reason)" -Retryable $false -Remedy 'проверьте путь/кодировку mcp-snippet.json'
                    }
                }
            }
            'doctor' {
                $info = Find-Python -Explicit $Python -TargetDir $target
                if ($info -and $info.Usable) { $pyInfo = $info; $py = $info.Path }
                $pyFor = Get-InterpreterPath -PythonInfo $info -Root $Root -Venv:$Venv
                if (-not $pyFor) {
                    $result = New-Step -Id $id -Phase 'preflight' -Status 'BLOCK' -Detail 'нет python для doctor.py' -Remedy 'сначала шаг python'
                } else {
                    $env:STANZA_RESOURCES_DIR = $resources
                    $rc = Invoke-Logged -Exe $pyFor -Argv @((Join-Path $Root 'scripts\doctor.py'),'--json') -Id 'doctor'
                    $counts = ''
                    try { $d = Get-Content -LiteralPath (Join-Path $artifactDir 'doctor.log') -Raw -Encoding UTF8 | ConvertFrom-Json; $counts = "OK $($d.counts.OK), WARN $($d.counts.WARN), FAIL $($d.counts.FAIL)" } catch { }
                    $result = if ($rc -eq 0) { New-Step -Id $id -Phase 'verify' -Detail "doctor: $counts" }
                              else { New-Step -Id $id -Phase 'verify' -Status 'FAIL' -Detail "doctor rc=$rc ($counts)" -Retryable $true -Remedy 'исправьте FAIL из doctor.log; повторите с -Resume' -NextCmd (Get-NextCommand $id) -Rc $rc }
                }
            }
            'acceptance' {
                $info = Find-Python -Explicit $Python -TargetDir $target
                if ($info -and $info.Usable) { $pyInfo = $info; $py = $info.Path }
                $pyFor = Get-InterpreterPath -PythonInfo $info -Root $Root -Venv:$Venv
                if (-not $pyFor) {
                    $result = New-Step -Id $id -Phase 'preflight' -Status 'BLOCK' -Detail 'нет python для приёмки' -Remedy 'сначала шаг python'
                } else {
                    $env:STANZA_RESOURCES_DIR = $resources
                    $rc = Invoke-Logged -Exe $pyFor -Argv @((Join-Path $PSScriptRoot 'acceptance.py'),'--json') -Id 'acceptance'
                    try { $acceptance = Get-Content -LiteralPath (Join-Path $artifactDir 'acceptance.log') -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
                    $f1 = ''
                    if ($acceptance -and $acceptance.f1) { $f1 = "corpus52 $($acceptance.f1.corpus52) / heldout_51 $($acceptance.f1.heldout_51)" }
                    $result = if ($rc -eq 0 -and $acceptance -and $acceptance.verdict -eq 'PASS') {
                        New-Step -Id $id -Phase 'verify' -Detail "приёмка зелёная: doctor, smoke fast/full, валидаторы, mcp_probe; F1 $f1"
                    } else {
                        New-Step -Id $id -Phase 'verify' -Status 'FAIL' -Detail "приёмка rc=$rc ($f1); verdict=$($acceptance.verdict)" -Retryable $true -Remedy 'см. acceptance.log; повторите с -Resume -Acceptance' -NextCmd (Get-NextCommand $id) -Rc $rc
                    }
                }
            }
            default {
                $result = New-Step -Id $id -Phase 'unknown' -Status 'FAIL' -Detail "неизвестный шаг $id" -Retryable $false
            }
        }
    } catch {
        $result = New-Step -Id $id -Phase 'exception' -Status 'FAIL' -Detail "$_" -Retryable $true -Remedy 'внутренняя ошибка шага; повторите с -Resume' -NextCmd (Get-NextCommand $id)
    }
    if (-not $result) { $result = New-Step -Id $id -Phase 'unknown' -Status 'FAIL' -Detail 'шаг не вернул результат' -Retryable $true }
    $result.seconds = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
    Add-StepResult $result
}

# ------------------------------------------------------------------ жизненный контур
if ($mode -eq 'make-offline-kit' -or $MakeOfflineKit) {
    $t0 = Get-Date
    $kitArgs = @('-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'offline_kit.ps1'),'-Action','make','-TargetDir',$Root,'-ArtifactDir',$artifactDir,'-ModelsDir',$resources,'-Python',$py)
    if ($Force) { $kitArgs += '-Force' }
    $rc = Invoke-Logged -Exe 'powershell.exe' -Argv $kitArgs -Id 'offline-kit'
    Add-StepResult (New-Step -Id 'offline-kit' -Phase 'package' -Seconds ([math]::Round(((Get-Date) - $t0).TotalSeconds,1)) -Status $(if ($rc -eq 0) {'OK'} else {'FAIL'}) -Detail "сборка офлайн-набора rc=$rc" -Rc $rc -Retryable ($rc -ne 0))
}
if ($mode -eq 'uninstall') {
    $removed = @()
    foreach ($f in @('mcp-snippet.json','python.cmd','use.ps1')) {
        $p = Join-Path $Root $f
        if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force; $removed += $f }
    }
    if ($Force) {
        foreach ($d in @((Join-Path $Root '.venv'), $resources)) {
            if (Test-Path -LiteralPath $d) { Remove-Item -LiteralPath $d -Recurse -Force; $removed += $d }
        }
    }
    Add-StepResult (New-Step -Id 'uninstall' -Phase 'cleanup' -Detail ('удалено: ' + ($removed -join ', ')))
}
if ($mode -eq 'raise-python' -or ($blockers | Where-Object { $_.component -eq 'python' })) {
    $nextAction.kind = 'raise-python'
    $nextAction.command = 'winget upgrade --id Python.Python.3.15 -e'
    $nextAction.snippet = 'Нужна Python 3.15.2 x64 per-user; более старые версии не поддерживаются (колёса cp315, F1 0.777/0.686).'
}
if ($mode -eq 'check-updates') {
    $t0 = Get-Date
    $pyFor = if ($py) { $py } else { (Get-InterpreterPath -PythonInfo (Find-Python -TargetDir $target) -Root $Root -Venv:$Venv) }
    $rc = 4
    if ($pyFor) { $rc = Invoke-Logged -Exe $pyFor -Argv @((Join-Path $PSScriptRoot 'pins.py'),'--latest','--json') -Id 'check-updates' }
    $detail = ''
    try { $detail = ((Get-Content -LiteralPath (Join-Path $artifactDir 'check-updates.log') -Raw -Encoding UTF8) -split "`n" | Select-Object -First 8) -join ' ' } catch { }
    Add-StepResult (New-Step -Id 'check-updates' -Phase 'verify' -Seconds ([math]::Round(((Get-Date)-$t0).TotalSeconds,1)) -Status $(if ($rc -eq 0) {'OK'} else {'FAIL'}) -Detail $detail -Rc $rc -Retryable ($rc -ne 0))
}

# ------------------------------------------------------------------ итог и отчёт
$retryableFail = @($stepResults | Where-Object { $_.status -eq 'FAIL' -and $_.retryable })
$hardFail = @($stepResults | Where-Object { $_.status -eq 'FAIL' -and -not $_.retryable })
$reboot = @($stepResults | Where-Object { $_.rc -eq 3010 -or $_.detail -match 'перезагрузк' })
if ($mode -eq 'uninstall' -or $mode -eq 'make-offline-kit') { $code = $(if ($hardFail.Count -or $retryableFail.Count) { $Code_Step } else { 0 }) }
elseif ($blockers.Count) { $code = $Code_Human }
elseif ($reboot.Count) { $code = $Code_Reboot }
elseif ($retryableFail.Count) { $code = $Code_Step }
elseif ($hardFail.Count) { $code = $Code_Broken }
else { $code = 0 }

if (-not $nextAction.command -and $retryableFail.Count) { $nextAction.command = $retryableFail[0].next_cmd }
if (-not $nextAction.kind -and $blockers.Count) { $nextAction.kind = 'human'; $nextAction.command = $blockers[0].fix_cmd }

$snippetPresent = Test-Path -LiteralPath (Join-Path $Root 'mcp-snippet.json')
$serverOk = @($stepResults | Where-Object { $_.id -eq 'snippet' -and $_.status -eq 'OK' }).Count -gt 0
$verdict = $(if ($code -eq 0 -and $serverOk) { 'ГОТОВО: сервер установлен и проверен' }
             elseif ($code -eq 0) { 'ГОТОВО' }
             elseif ($code -eq 2) { 'НУЖЕН ЧЕЛОВЕК' }
             elseif ($code -eq 3) { 'ШАГ УПАЛ (retryable)' }
             elseif ($code -eq 6) { 'НУЖНА ПЕРЕЗАГРУЗКА' } else { 'СЛОМАН ЗАПУСК' })

$secs = [math]::Round(((Get-Date) - $started).TotalSeconds, 1)
$sizes = [ordered]@{
    packages_mb = [math]::Round((Get-DirBytes $(if ($Venv) { (Join-Path $Root '.venv') } else { '' })) / 1MB, 1)
    models_mb = [math]::Round((Get-DirBytes $resources) / 1MB, 1)
    downloads_mb = [math]::Round((Get-DirBytes (Join-Path $artifactDir 'downloads')) / 1MB, 1)
}
$timing = [ordered]@{ started = $started.ToString('yyyy-MM-ddTHH:mm:ssZ'); finished = (Get-Date).ToString('yyyy-MM-ddTHH:mm:ssZ'); total_seconds = $secs }
$report = [ordered]@{
    schema_version = 2; code = $code; ok = ($code -eq 0); verdict = $verdict
    arch = $arch; mode = $mode; mcp_registration = $mcpRegistration
    report_path = (Join-Path $artifactDir 'install-report.json')
    mcp_snippet_path = $snippetPath
    python_path = $pyInfo.Path
    stanza_resources = $resources
    steps = @($stepResults.ToArray()); blockers = @($blockers.ToArray()); failures = @($failures.ToArray())
    next_action = $nextAction; sizes = $sizes; timings = $timing
    acceptance = $acceptance; server_status = $serverStatus; plan = $planArr
    snippet_present = $snippetPresent
}
try { $reportPath = Save-Report -Report $report -ArtifactDir $artifactDir } catch { Say "не удалось записать отчёт: $_" Red }
Add-LogLine -ArtifactDir $artifactDir -Text ("ИТОГ: $verdict (код $code) за $secs с")

if ($Json) {
    Emit-Json $report
} else {
    Say ''
    Say "итог: $verdict (код $code) за $secs с" $(if ($code -eq 0) { 'Green' } else { 'Red' })
    if ($code -eq 0 -and $snippetPresent) {
        Say 'Сервер установлен и проверен. Осталось одно действие человека:' Green
        Say "1) откройте mcp-snippet.json: $snippetPath" Yellow
        Say '2) добавьте запись stanza-german в конфиг MCP-клиента (mcp.json и аналоги)' Yellow
        Say '3) перезапустите MCP-клиент и проверьте: .\install.ps1 -Check mcp' Yellow
    }
    foreach ($b in $blockers) { Say ("БЛОКЕР: {0}: {1}; fix: {2}" -f $b.component, $b.reason, $b.fix_cmd) Yellow }
    foreach ($f in $failures) { Say ("СБОЙ: {0}: {1}; remedy: {2}" -f $f.id, $f.detail, $f.remedy) Red }
    if ($nextAction.command) { Say ("next_action.command: " + $nextAction.command) }
    Say ("отчёт: $reportPath; лог: $logFile; NDJSON: $progressFile")
}
Close-ProgressLog
Release-Artifacts
exit $code
