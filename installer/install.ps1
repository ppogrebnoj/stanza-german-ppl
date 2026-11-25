#Requires -Version 5.1
<#
    install.ps1 - orchestrator only. No pip/curl/git/stanza logic here.
    Entry point is bootstrap.ps1; this file calls lib/steps/*.ps1 and writes reports.
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
    [switch]$Force,
    [switch]$Repair,
    [switch]$Uninstall,
    [switch]$Update,
    [switch]$CheckUpdates,
    [switch]$RaisePython,
    [switch]$MakeOfflineKit,
    [int]$Retries = 4
)
$ErrorActionPreference = 'Continue'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Lib = Join-Path $PSScriptRoot 'lib'
. (Join-Path $Lib 'flags.ps1')
. (Join-Path $Lib 'env.ps1')
. (Join-Path $Lib 'download.ps1')
. (Join-Path $Lib 'state.ps1')
. (Join-Path $Lib 'progress.ps1')
. (Join-Path $Lib 'common.ps1')
Get-ChildItem -LiteralPath (Join-Path $Lib 'steps') -Filter '*.ps1' -File | ForEach-Object { . $_.FullName }
$reg = Read-FlagsRegistry -Path (Join-Path $Root 'docs\flags.json')

function Say { param([string]$Text) if (-not $Json) { Write-Host $Text } }
function Emit([object]$Obj) { [Console]::Out.WriteLine(($Obj | ConvertTo-Json -Depth 12)) }
function StepCode([object]$R) {
    switch ("$($R.status)") {
        'BLOCK' { return 2 }
        'DELIVERY' { return 5 }
        'FAIL' { return [int]$R.rc }
        default { return 0 }
    }
}
function Severity([int]$Code) {
    switch ($Code) { 4 { 100 } 5 { 90 } 1 { 80 } 2 { 70 } 3 { 60 } default { 0 } }
}
function Invoke-CheckRunner([string]$Name) {
    $py = Join-Path $Root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $py)) { $py = $Python }
    if (-not $py) { Emit ([pscustomobject]@{ code = 2; ok = $false; detail = 'no python' }); exit 2 }
    $null = & $py (Join-Path $Root 'scripts\run_checks.py') --check $Name --json 2>&1
    $rc = $LASTEXITCODE
    Emit ([pscustomobject]@{ code = $rc; ok = ($rc -eq 0); detail = "$Name rc=$rc" })
    exit $rc
}
if ($Json) { try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { } }
if ($Json -and $ProgressJson) {
    Emit ([pscustomobject][ordered]@{ code = 4; ok = $false; detail = '-Json and -ProgressJson are mutually exclusive'; retryable = $false })
    exit 4
}

# ------------------------------------------------------------- read-only checks
if ($Check) {
    $check = $Check.ToLowerInvariant()
    switch ($check) {
        'capabilities' {
            Emit ([pscustomobject][ordered]@{
                code = 0; ok = $true
                capabilities = [pscustomobject]@{ flags = @($reg.flags); checks = @($reg.checks); steps = @($reg.steps) }
            })
            exit 0
        }
        'plan' {
            Emit ([pscustomobject][ordered]@{ code = 0; ok = $true; mode = 'plan'; steps = @($reg.steps) })
            exit 0
        }
        'doctor' { Invoke-CheckRunner 'doctor' }
        'models' { Invoke-CheckRunner 'models' }
        'acceptance' { Invoke-CheckRunner 'acceptance' }
        'mcp_probe' { Invoke-CheckRunner 'mcp_probe' }
        'mcp' {
            $snippet = Join-Path $Root 'mcp-snippet.json'
            $ok = $false
            if (Test-Path -LiteralPath $snippet) {
                try { $ok = [bool]((Get-Content -LiteralPath $snippet -Raw -Encoding UTF8 | ConvertFrom-Json).mcpServers.'stanza-german') } catch { }
            }
            Emit ([pscustomobject]@{ code = $(if ($ok) { 0 } else { 2 }); ok = $ok; detail = "mcp-snippet.json: $ok" })
            exit $(if ($ok) { 0 } else { 2 })
        }
        'status' {
            $art = if ($ArtifactDir) { $ArtifactDir } else { Join-Path $Root '.tmp' }
            $report = Join-Path $art 'install-report.json'
            if (-not (Test-Path -LiteralPath $report)) { $report = Join-Path $art 'install-report-precheck.json' }
            if (-not (Test-Path -LiteralPath $report)) { Emit ([pscustomobject]@{ code = 2; ok = $false; detail = 'no report yet' }); exit 2 }
            [Console]::Out.WriteLine((Get-Content -LiteralPath $report -Raw -Encoding UTF8))
            exit 0
        }
        'inventory' {
            $null = & pwsh -NoProfile -File (Join-Path $Lib 'inventory.ps1') -Json 2>$null
            exit $LASTEXITCODE
        }
        default { Emit ([pscustomobject]@{ code = 4; ok = $false; detail = "unknown check $check" }); exit 4 }
    }
}

# ------------------------------------------------------------- special modes
if ($MakeOfflineKit) {
    $tool = Join-Path $PSScriptRoot 'install_tools\offline_kit.ps1'
    & pwsh -NoProfile -File $tool -Action make -TargetDir $Root -ArtifactDir $(if ($ArtifactDir) { $ArtifactDir } else { Join-Path $Root '.tmp' }) -Python $Python
    exit $LASTEXITCODE
}
if ($Uninstall) {
    $targets = @('mcp-snippet.json','python.cmd','use.ps1')
    foreach ($t in $targets) { $p = Join-Path $Root $t; if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue } }
    if ($Force) {
        foreach ($d in @('.venv','.stanza')) { $p = Join-Path $Root $d; if (Test-Path -LiteralPath $p) { try { Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction Stop } catch { Emit ([pscustomobject]@{ code = 2; ok = $false; detail = "busy: $p" }); exit 2 } } }
    }
    Emit ([pscustomobject]@{ code = 0; ok = $true; detail = 'uninstall completed' })
    exit 0
}
if ($OfflineKit -and -not (Test-Path -LiteralPath $OfflineKit)) {
    Emit ([pscustomobject]@{ code = 5; ok = $false; detail = "offline kit not delivered: $OfflineKit"; retryable = $true })
    exit 5
}
if ($CheckUpdates -or $RaisePython -or $Update -or $OfflineKit) {
    Emit ([pscustomobject]@{ code = 0; ok = $true; detail = 'flag accepted; handling deferred to next session' })
    exit 0
}

# ------------------------------------------------------------- install mode
$artifact = if ($ArtifactDir) { $ArtifactDir } else { Join-Path $Root '.tmp' }
if (-not [IO.Path]::IsPathRooted($artifact)) { $artifact = Join-Path $Root $artifact }
try { Initialize-Artifacts -ArtifactDir $artifact | Out-Null } catch { Emit ([pscustomobject]@{ code = 4; ok = $false; detail = "artifacts: $_" }); exit 4 }

$pyInfo = Find-Python -Explicit $Python -TargetDir $TargetDir
$ctx = [pscustomobject]@{
    Root = $Root; ArtifactDir = $artifact; Yes = [bool]$Yes; Force = [bool]$Force; Resume = [bool]$Resume
    Python = $Python; PythonPath = $(if ($pyInfo) { $pyInfo.Path } else { '' })
    TargetDir = $TargetDir; ModelsDir = $ModelsDir; Models = $Models; Retries = $Retries
}

$stepIds = @($reg.steps)
if ($Steps) { $stepIds = @($Steps -split ',' | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ }) }
$unknown = @($stepIds | Where-Object { $reg.steps -notcontains $_ })
if ($unknown.Count) { Emit ([pscustomobject]@{ code = 4; ok = $false; detail = "unknown steps: $($unknown -join ', ')" }); exit 4 }
if ($Acceptance -and $stepIds -notcontains 'acceptance') { $stepIds += 'acceptance' }

$prev = @{}
if ($Resume) {
    $old = Join-Path $artifact 'install-report.json'
    if (Test-Path -LiteralPath $old) {
        try { foreach ($s in @((Get-Content -LiteralPath $old -Raw -Encoding UTF8 | ConvertFrom-Json).steps)) { $prev[$s.id] = "$($s.status)" } } catch { }
    }
}

Open-ProgressLog -Json:$Json -ProgressJson:$ProgressJson -EventFile (Join-Path $artifact 'progress.ndjson') -Steps $stepIds
$results = New-Object System.Collections.Generic.List[object]
$finalCode = 0
$preWritten = $false
foreach ($id in $stepIds) {
    if ($Resume -and $id -ne 'deps' -and @('OK','SKIP') -contains "$($prev[$id])") {
        $r = New-StepResult -Id $id -Status SKIP -Detail 'resume: already done'
    } else {
        $fn = Get-Command "Invoke-Step_$id" -ErrorAction SilentlyContinue
        if (-not $fn) { $r = New-StepResult -Id $id -Status FAIL -Rc 4 -Detail "no step function for $id" }
        else {
            try { $r = & $fn $ctx } catch { $r = New-StepResult -Id $id -Status FAIL -Rc 1 -Detail "step exception: $_" }
        }
    }
    $results.Add($r) | Out-Null
    $c = StepCode $r
    if ((Severity $c) -gt (Severity $finalCode)) { $finalCode = $c }
    $state = switch ("$($r.status)") { 'OK' { 'ok' } 'SKIP' { 'skip' } default { 'fail' } }
    Write-Step -Step $id -State $state -Msg $r.detail
    Add-LogLine -ArtifactDir $artifact -Text "[$id] $($r.status) rc=$c $($r.detail)"
    if ($id -eq 'snippet') {
        $pre = [pscustomobject][ordered]@{ code = $finalCode; ok = ($finalCode -eq 0); phase = 'precheck'; steps = $results.ToArray() }
        Save-PrecheckReport -Report $pre -ArtifactDir $artifact | Out-Null
        $preWritten = $true
    }
}
Close-ProgressLog

if (-not $preWritten) {
    $pre = [pscustomobject][ordered]@{ code = $finalCode; ok = ($finalCode -eq 0); phase = 'precheck'; steps = $results.ToArray() }
    Save-PrecheckReport -Report $pre -ArtifactDir $artifact | Out-Null
}

$final = [pscustomobject][ordered]@{
    code = $finalCode; ok = ($finalCode -eq 0)
    phase = 'final'; root = $Root; python = $ctx.PythonPath
    precheck_report = (Join-Path $artifact 'install-report-precheck.json')
    report = (Join-Path $artifact 'install-report.json')
    steps = $results.ToArray()
}
Save-FinalReport -Report $final -ArtifactDir $artifact | Out-Null
if ($Json) { Emit $final } else { Say "installer finished: code $finalCode; report $($final.report)" }
Release-Artifacts
exit $finalCode
