#Requires -Version 5.1
<#
    _env.ps1 — единственный источник правды о среде (dot-source, без param-блока):
    архитектура, каталоги артефактов/моделей/установки Python, поиск интерпретатора,
    STANZA_RESOURCES_DIR. all.ps1, setup.ps1 и inventory.ps1 обязаны пользоваться
    именно этой функцией поиска Python (Get-PythonInfo / Find-Python).

    Ничего не пишет: библиотека пригодна для -Check (режим только чтение).
#>

function Get-MachineArch {
    $a = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    if (-not $a) { $a = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture }
    if (-not $a) { return 'UNKNOWN' }
    return (($a -replace '^x86[-_]?64$', 'AMD64' -replace '^x64$', 'AMD64').ToUpperInvariant())
}

function Get-ProjectRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

function Get-DefaultArtifactDir { param([string]$Root = (Get-ProjectRoot))
    return (Join-Path $Root '.tmp')
}
function Get-DefaultTargetDir {
    return (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python315')
}
function Get-DefaultModelsDir { param([string]$Root = (Get-ProjectRoot))
    return (Join-Path $Root '.stanza\models')
}

# Единственный источник STANZA_RESOURCES_DIR: явный -ModelsDir > process env > каталог проекта.
# В -Check режимы переменная НЕ меняется и НЕ создаётся.
function Get-StanzaResourcesDir {
    param([string]$Root = (Get-ProjectRoot), [string]$ModelsDir = '')
    if ($ModelsDir) { return (Resolve-Path -LiteralPath $ModelsDir -ErrorAction SilentlyContinue).Path }
    if ($env:STANZA_RESOURCES_DIR) { return $env:STANZA_RESOURCES_DIR }
    return (Get-DefaultModelsDir $Root)
}

function Get-PythonInfo {
    param([string]$Path)
    if (-not $Path -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    try { $Path = (Resolve-Path -LiteralPath $Path).Path } catch { }
    $ver = $null; $bits = $null
    try {
        $ver = (& $Path -c "import sys;print('%d.%d.%d' % sys.version_info[:3])" 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -ne 0) { $ver = $null }
        $bits = (& $Path -c "import struct;print(struct.calcsize('P') * 8)" 2>$null | Select-Object -First 1)
        if ($LASTEXITCODE -ne 0) { $bits = $null }
    } catch { }
    if (-not $ver) { return $null }
    $ver = "$ver".Trim(); $bits = "$bits".Trim()
    $storeAlias = $Path -match '\\WindowsApps\\'
    $dir = Split-Path -Parent $Path
    $pep668 = $false
    foreach ($marker in @((Join-Path $dir 'Lib\EXTERNALLY-MANAGED'), (Join-Path $dir 'EXTERNALLY-MANAGED'))) {
        if (Test-Path -LiteralPath $marker) { $pep668 = $true; break }
    }
    # Проверка прав БЕЗ записи (Get-Acl): -Check режимы не меняют файлы.
    $writable = $true
    try {
        $acl = Get-Acl -LiteralPath $dir -ErrorAction Stop
        $me = [Security.Principal.WindowsIdentity]::GetCurrent()
        $sid = $me.User.Value
        $allow = $false; $deny = $false
        foreach ($r in $acl.Access) {
            try { if ($r.IdentityReference.Value -ne $sid) { continue } } catch { continue }
            if ($r.AccessControlType -eq 'Deny' -and ($r.FileSystemRights -band [Security.AccessControl.FileSystemRights]::Write)) { $deny = $true }
            if ($r.AccessControlType -eq 'Allow' -and ($r.FileSystemRights -band [Security.AccessControl.FileSystemRights]::Write)) { $allow = $true }
        }
        if ($deny -or -not $allow) { $writable = $false }
    } catch { }
    $reason = ''
    if ($storeAlias) { $reason = 'store-alias' }
    elseif ($ver -notmatch '^3\.15\.') { $reason = 'wrong-version' }
    elseif ($bits -ne '64') { $reason = 'wrong-bits' }
    elseif (-not $writable) { $reason = 'not-writable' }
    elseif ($pep668) { $reason = 'pep668' }
    return [pscustomobject]@{
        Path = $Path; Version = $ver; Bits = $bits; StoreAlias = $storeAlias
        ExternallyManaged = $pep668; Writable = $writable; Reason = $reason
        Usable = [string]::IsNullOrEmpty($reason)
    }
}

function Find-Python {
    param([string]$Explicit = '', [string]$TargetDir = '', [switch]$AllowUnusable)
    $cands = New-Object System.Collections.Generic.List[string]
    if ($Explicit) { $cands.Add($Explicit) }
    # реестр per-user / machine: единственный надёжный признак «установлен официальным инсталлятором»
    foreach ($hive in @('HKCU:\Software\Python\PythonCore\3.15\InstallPath',
                        'HKLM:\SOFTWARE\Python\PythonCore\3.15\InstallPath',
                        'HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore\3.15\InstallPath')) {
        try {
            $key = Get-ItemProperty -LiteralPath $hive -ErrorAction Stop
            foreach ($v in @($key.'ExecutablePath', $key.'(default)', $key.InstallPath)) {
                if (-not $v) { continue }
                if ($v -match 'python(?:\.exe)?$') {
                    $p = "$v"
                    if ($p -notmatch '\.exe$') { $p = Join-Path $p 'python.exe' }
                    $cands.Add($p)
                } elseif (Test-Path -LiteralPath (Join-Path "$v" 'python.exe')) {
                    $cands.Add((Join-Path "$v" 'python.exe'))
                }
            }
        } catch { }
    }
    try {
        foreach ($line in (& py -0p 2>$null)) {
            if ("$line" -match '-V:3\.15' -and "$line" -match 'python\.exe') {
                $cands.Add((("$line" -split '\s+')[-1]).Trim())
            }
        }
    } catch { }
    try {
        $p = (& python -c "import sys;print(sys.executable)" 2>$null | Select-Object -First 1)
        if ($p) { $cands.Add(("$p".Trim())) }
    } catch { }
    if (-not $TargetDir) { $TargetDir = Get-DefaultTargetDir }
    $cands.Add((Join-Path $TargetDir 'python.exe'))
    $cands.Add((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python315\python.exe'))
    $cands.Add('C:\Program Files\Python315\python.exe')
    $cands.Add('C:\Program Files\Python\Python315\python.exe')

    $seen = @{}
    $firstBad = $null
    foreach ($p in $cands) {
        if (-not $p -or $seen.ContainsKey($p.ToLowerInvariant())) { continue }
        $seen[$p.ToLowerInvariant()] = $true
        $info = Get-PythonInfo -Path $p
        if (-not $info) { continue }
        if ($AllowUnusable -or $info.Usable) { return $info }
        # запоминаем первую непригодную находку для blockers[].fix_cmd, но продолжаем поиск
        if (-not $firstBad) { $firstBad = $info }
    }
    return $firstBad
}

function Get-InterpreterPath {
    param([object]$PythonInfo, [string]$Root = (Get-ProjectRoot), [switch]$Venv)
    if ($Venv) {
        $vp = Join-Path $Root '.venv\Scripts\python.exe'
        if (Test-Path -LiteralPath $vp) { return $vp }
    }
    if ($PythonInfo) { return $PythonInfo.Path }
    return ''
}

function Get-RegistryPathValue {
    param([string]$Path, [string]$Name)
    try {
        $key = Get-ItemProperty -LiteralPath $Path -ErrorAction Stop
        if ($Name -eq '(default)') { return [string]$key.'(default)' }
        return [string]$key.$Name
    } catch { return '' }
}
