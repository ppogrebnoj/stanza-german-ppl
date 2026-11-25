#Requires -Version 5.1
# Common helpers for installer steps. No step logic here.

function New-StepResult {
    param(
        [string]$Id,
        [ValidateSet('OK','SKIP','BLOCK','FAIL','DELIVERY')][string]$Status,
        [int]$Rc = 0,
        [string]$Detail = '',
        [bool]$Retryable = $false,
        [string]$NextCmd = '',
        [string[]]$Warnings = @()
    )
    return [pscustomobject][ordered]@{
        id = $Id; status = $Status; rc = $Rc; detail = $Detail
        retryable = $Retryable; next_cmd = $NextCmd; warnings = @($Warnings)
    }
}

function Test-VenvBusy {
    param([string]$Root)
    $vp = Join-Path $Root '.venv\Scripts\python.exe'
    $busy = @()
    try {
        $procs = Get-CimInstance Win32_Process -ErrorAction Stop
        foreach ($p in $procs) {
            $cl = "$($p.CommandLine)"
            if ($cl -and $cl.ToLowerInvariant().Contains($vp.ToLowerInvariant())) {
                $busy += "pid=$($p.ProcessId) $cl"
            }
        }
    } catch { }
    return $busy
}

function Test-CorrectVenv {
    param([string]$Root)
    $vp = Join-Path $Root '.venv\Scripts\python.exe'
    $res = [pscustomobject]@{ ok = $false; exists = $false; pip_ok = $false; detail = ''; py = $vp; warnings = @() }
    if (-not (Test-Path -LiteralPath $vp -PathType Leaf)) { $res.detail = '.venv python missing'; return $res }
    $res.exists = $true

    $code = @(& $vp -c "import sys,struct;print('%s|%d.%d|%d' % (sys.prefix, sys.version_info[0], sys.version_info[1], struct.calcsize('P')*8))" 2>$null)
    $rc = $LASTEXITCODE
    if ($rc -ne 0 -or $code.Count -eq 0) { $res.detail = 'cannot run .venv python'; return $res }
    $parts = ("$($code[0])" -split '\|')
    $prefix = "$($parts[0])"; $ver = "$($parts[1])"; $bits = "$($parts[2])"
    $cfg = Join-Path $Root '.venv\pyvenv.cfg'
    $prefixOk = $prefix.ToLowerInvariant().StartsWith((Join-Path $Root '.venv').ToLowerInvariant())
    if ($ver -ne '3.15' -or $bits -ne '64' -or -not (Test-Path -LiteralPath $cfg) -or -not $prefixOk) {
        $res.detail = "bad venv: python=$ver bits=$bits prefix=$prefix"
        return $res
    }
    $null = & $vp -m pip --version 2>$null
    $res.pip_ok = ($LASTEXITCODE -eq 0)
    if (-not $res.pip_ok) { $res.detail = 'pip is missing or broken'; return $res }
    $res.ok = $true
    $res.detail = "venv OK: python=$ver bits=$bits"
    return $res
}

function Test-LockInstalledMarker {
    param([string]$ArtifactDir)
    return (Test-Path -LiteralPath (Join-Path $ArtifactDir 'deps-installed-from-lock.json'))
}

function Set-LockInstalledMarker {
    param([string]$ArtifactDir)
    $json = '{"installed_from_lock":true}'
    [IO.File]::WriteAllText((Join-Path $ArtifactDir 'deps-installed-from-lock.json'), $json, (New-Object System.Text.UTF8Encoding($false)))
}

function Remove-LockInstalledMarker {
    param([string]$ArtifactDir)
    $p = Join-Path $ArtifactDir 'deps-installed-from-lock.json'
    if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue }
}

function Test-DepsState {
    param([string]$Root, [string]$ArtifactDir, [int]$TimeoutMs = 300000)
    $py = Join-Path $Root '.venv\Scripts\python.exe'
    $warnings = @()
    $clean = Test-LockInstalledMarker $ArtifactDir

    $null = & $py -m pip check 2>&1
    $pipRc = $LASTEXITCODE
    if ($pipRc -ne 0) {
        return [pscustomobject]@{ ok = $false; detail = "pip check rc=$pipRc"; clean = $clean; rc = $(if ($clean) { 1 } else { 3 }); retryable = (-not $clean); warnings = $warnings }
    }

    $lock = Join-Path $Root 'installer\requirements.lock'
    $checkScript = @'
import importlib.metadata as m, json, sys
bad = []
with open(sys.argv[1], encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, want = [x.strip() for x in line.split("==", 1)]
        try:
            got = m.version(name)
        except Exception:
            got = None
        if got != want:
            bad.append("%s %s != %s" % (name, got, want))
print(json.dumps(bad))
'@
    $out = @(& $py -c $checkScript $lock 2>$null)
    if ($LASTEXITCODE -ne 0 -or $out.Count -eq 0) {
        return [pscustomobject]@{ ok = $false; detail = 'lock version check failed'; clean = $clean; rc = 3; retryable = $true; warnings = $warnings }
    }
    $bad = ("$($out[0])" | ConvertFrom-Json)
    if (@($bad).Count -gt 0) {
        return [pscustomobject]@{ ok = $false; detail = (@($bad) -join '; '); clean = $clean; rc = $(if ($clean) { 1 } else { 3 }); retryable = (-not $clean); warnings = $warnings }
    }

    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $py
    $psi.Arguments = '-c "import stanza, torch, numpy, mcp, pyphen"'
    $psi.UseShellExecute = $false
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi
    try {
        $null = $proc.Start()
        $so = $proc.StandardOutput.ReadToEnd()
        $se = $proc.StandardError.ReadToEnd()
        if (-not $proc.WaitForExit($TimeoutMs)) {
            try { $proc.Kill() } catch { }
            return [pscustomobject]@{ ok = $false; detail = "import smoke timeout ${TimeoutMs}ms"; clean = $clean; rc = 3; retryable = $true; warnings = $warnings }
        }
        if ($proc.ExitCode -ne 0) {
            $tail = (@($se -split "`n") | Select-Object -Last 20) -join ' | '
            return [pscustomobject]@{ ok = $false; detail = "import smoke rc=$($proc.ExitCode); stderr_tail=$tail"; clean = $clean; rc = $(if ($clean) { 1 } else { 3 }); retryable = (-not $clean); warnings = $warnings }
        }
        if ($se) { $warnings += 'import smoke wrote stderr (ignored)' }
    } catch {
        return [pscustomobject]@{ ok = $false; detail = "import smoke error: $_"; clean = $clean; rc = 3; retryable = $true; warnings = $warnings }
    } finally { try { $proc.Dispose() } catch { } }

    return [pscustomobject]@{ ok = $true; detail = 'pip check + lock + imports OK'; clean = $clean; rc = 0; retryable = $false; warnings = $warnings }
}
