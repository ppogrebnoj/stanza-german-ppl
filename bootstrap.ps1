#Requires -Version 5.1
<#
    bootstrap.ps1 - ENTRY POINT ONLY.

    Safe one-liner:
        irm https://.../bootstrap.ps1 -OutFile bootstrap.ps1
        irm https://.../bootstrap.ps1.sha256 -OutFile bootstrap.ps1.sha256
        # verify SHA256, then:
        powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1

    This file parses flags, obtains the project source when needed, calls
    installer/install.ps1 and returns its exit code. No installation step logic.
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)][object[]]$Rest
)
$ErrorActionPreference = 'Continue'
$Repo = 'ppogrebnoj/stanza-german-ppl'
# Тег, которому принадлежит этот bootstrap: standalone-ветка берёт парсер флагов
# из своего тега, а не из master (иначе релиз берёт флаги будущей версии).
$ReleaseTag = 'v4.0.5'
$ReleaseBase = "https://github.com/$Repo/releases/latest/download"
# --retry-all-errors закрывает TLS-reset/10054, которые --retry не ловит.
$CurlRetry = @('--retry', '4', '--retry-all-errors', '--retry-delay', '2',
               '--connect-timeout', '20', '-4', '--http1.1')
$AppDir = Join-Path $env:LOCALAPPDATA 'stanza-german-ppl\app'
$Work = Join-Path $env:TEMP 'stanza-german-bootstrap'
$TotalProgressSteps = 11
# JSON-режим может понадобиться до парсинга: доставка флагов тоже обязана
# возвращать машинный 5/DELIVERY, а не человеческий текст.
$script:wantsJson = @($Rest | Where-Object { "$_" -eq '-Json' }).Count -gt 0

function Say { param([string]$Text, [string]$Color) if (-not $script:wantsJson) { if ($Color) { Write-Host $Text -ForegroundColor $Color } else { Write-Host $Text } } }
function Step-Note {
    param([int]$N, [string]$Text)
    Say "[bootstrap $N/$TotalProgressSteps] $Text" Cyan
}
function Invoke-Download {
    param([int]$Step, [string]$Label, [string]$Url, [string]$Out)
    $dir = Split-Path -Parent $Out
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    Step-Note $Step "download $Label from $Url"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $lines = New-Object 'System.Collections.Generic.List[string]'
    # curl сам показывает объём/процент/ETA в --progress-bar (stderr).
    # Забираем stderr в конвейер: в человеческом режиме показываем прогресс,
    # в -Json — молчим, но причину отказа сохраняем для detail.
    & curl.exe -fL @CurlRetry --progress-bar -o $Out $Url 2>&1 | ForEach-Object {
        $s = "$_"
        [void]$lines.Add($s)
        if (-not $script:wantsJson -and ($s -match '%' -or $s -match 'curl:')) { Write-Host -NoNewline $s }
    }
    $rc = $LASTEXITCODE
    $sw.Stop()
    if (-not $script:wantsJson) { Write-Host '' }
    if ($rc -ne 0) {
        $reason = @($lines | ForEach-Object { "$_" -replace '[\r\n]+', ' ' } |
            Where-Object { $_ -match '\S' } | Select-Object -Last 3) -join '; '
        if (-not $reason) { $reason = "curl exit $rc" }
        return [pscustomobject]@{ ok = $false; rc = $rc; reason = $reason }
    }
    $bytes = if (Test-Path -LiteralPath $Out) { (Get-Item -LiteralPath $Out).Length } else { 0 }
    if (-not $script:wantsJson) {
        Say ('    {0}: {1:N1} MB ({2:N0} bytes) in {3:N1}s' -f $Label, ($bytes / 1MB), $bytes, $sw.Elapsed.TotalSeconds) DarkGray
    }
    return [pscustomobject]@{ ok = $true; rc = 0; reason = ''; bytes = $bytes }
}
function Emit-Broken {
    param([int]$Code, [string]$Detail, [bool]$Retryable = $false)
    if ($script:wantsJson) {
        [Console]::Out.WriteLine(([pscustomobject][ordered]@{
            code = $Code; ok = $false
            failures = @([pscustomobject]@{ id = 'bootstrap'; detail = $Detail; retryable = $Retryable })
        } | ConvertTo-Json -Depth 5))
    } else { Say "bootstrap: $Detail" Red }
    exit $Code
}

$flagsLib = Join-Path $PSScriptRoot 'installer\lib\flags.ps1'
$regPath = Join-Path $PSScriptRoot 'docs\flags.json'
if (-not (Test-Path -LiteralPath $flagsLib) -or -not (Test-Path -LiteralPath $regPath)) {
    # Standalone one-liner: оба файла нужны одновременно — парсер без реестра бесполезен.
    $raw = "https://raw.githubusercontent.com/$Repo/$ReleaseTag"
    $deliverables = @(
        [pscustomobject]@{ Name = 'installer\lib\flags.ps1'; Url = "$raw/installer/lib/flags.ps1"; Path = $flagsLib; Step = 1 },
        [pscustomobject]@{ Name = 'docs\flags.json'; Url = "$raw/docs/flags.json"; Path = $regPath; Step = 2 }
    )
    foreach ($item in $deliverables) {
        if (Test-Path -LiteralPath $item.Path) { continue }
        $dl = Invoke-Download -Step $item.Step -Label $item.Name -Url $item.Url -Out $item.Path
        if (-not $dl.ok) { Emit-Broken 5 "delivery failed: $($item.Name) (curl exit $($dl.rc): $($dl.reason)); retry the same command" $true }
        if (-not (Test-Path -LiteralPath $item.Path)) { Emit-Broken 5 "delivery failed: $($item.Name) (curl exit 0, file missing); retry the same command" $true }
    }
}
# Парсер и реестр — это доставка, пока нет installer/install.ps1: код 5, а не 4.
if (-not (Test-Path -LiteralPath $flagsLib)) { Emit-Broken 5 'delivery failed: installer\lib\flags.ps1 (missing); retry the same command' $true }
if (-not (Test-Path -LiteralPath $regPath)) { Emit-Broken 5 'delivery failed: docs\flags.json (missing); retry the same command' $true }
. $flagsLib
try { $reg = Read-FlagsRegistry -Path $regPath } catch { Emit-Broken 5 "delivery failed: docs\flags.json ($_); retry the same command" $true }
$parsed = Convert-InstallerArgs -Rest $Rest -Registry $reg
$script:wantsJson = $parsed.bound.ContainsKey('Json')
if ($script:wantsJson) { try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { } }
if ($parsed.errors.Count) { Emit-Broken 4 ($parsed.errors -join '; ') }

# -ProjectDir выбирает каталог разворачивания проекта в standalone-режиме.
# Относительный путь считается от текущего каталога, а не от bootstrap.ps1.
if ($parsed.bound.ContainsKey('ProjectDir')) {
    $p = [Environment]::ExpandEnvironmentVariables([string]$parsed.bound['ProjectDir'])
    if (-not [IO.Path]::IsPathRooted($p)) { $p = Join-Path (Get-Location).Path $p }
    $AppDir = [IO.Path]::GetFullPath($p)
}
Step-Note 3 "project directory: $AppDir"

$arch = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
if (-not $arch) { $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture }
$arch = (($arch -replace '^x86[-_]?64$', 'AMD64' -replace '^x64$', 'AMD64')).ToUpperInvariant()
if ($arch -ne 'AMD64' -or [IntPtr]::Size -ne 8) {
    Emit-Broken 4 "Windows x64 and 64-bit PowerShell required; got $arch / $([IntPtr]::Size * 8) bit"
}

# Boundary: until installer/install.ps1 exists, any source/asset problem is
# 5 / DELIVERY. Once it exists, broken invocation/flags are 4 / BROKEN.
$entry = Join-Path $PSScriptRoot 'installer\install.ps1'
$root = $PSScriptRoot
if (-not (Test-Path -LiteralPath $entry)) {
    $root = $AppDir
    $entry = Join-Path $root 'installer\install.ps1'
}
if (-not (Test-Path -LiteralPath $entry)) {
    if (-not (Test-Path -LiteralPath $Work)) { New-Item -ItemType Directory -Force -Path $Work | Out-Null }
    $zip = Join-Path $Work 'stanza-german-ppl-source.zip'
    $sha = Join-Path $Work 'stanza-german-ppl-source.zip.sha256'
    $dl = Invoke-Download -Step 4 -Label 'stanza-german-ppl-source.zip' -Url "$ReleaseBase/stanza-german-ppl-source.zip" -Out $zip
    if (-not $dl.ok) { Emit-Broken 5 "delivery failed: stanza-german-ppl-source.zip (curl exit $($dl.rc): $($dl.reason)); retry the same command" $true }
    $dl = Invoke-Download -Step 5 -Label 'stanza-german-ppl-source.zip.sha256' -Url "$ReleaseBase/stanza-german-ppl-source.zip.sha256" -Out $sha
    if (-not $dl.ok) { Emit-Broken 5 "delivery failed: stanza-german-ppl-source.zip.sha256 (curl exit $($dl.rc): $($dl.reason)); retry the same command" $true }
    if (-not (Test-Path -LiteralPath $sha)) { Emit-Broken 5 'delivery failed: stanza-german-ppl-source.zip.sha256 (missing); retry the same command' $true }
    Step-Note 6 'verify source SHA256 and unpack'
    $want = ((Get-Content -LiteralPath $sha -Raw -Encoding ASCII) -split '\s+')[0].ToLowerInvariant()
    $got = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
    if (-not $want) { Emit-Broken 5 'delivery failed: stanza-german-ppl-source.zip.sha256 (empty digest); retry the same command' $true }
    if ($want -ne $got) { Emit-Broken 5 "source SHA256 mismatch: $want != $got" }
    $stage = Join-Path $Work 'src'
    if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory($zip, $stage, (New-Object System.Text.UTF8Encoding($false)))
    # Ищем каталог, где есть installer/install.ps1: корневой install.ps1 — форвардер,
    # копировать его родителя было бы недостаточно.
    $found = @(Get-ChildItem -LiteralPath $stage -Recurse -Filter 'install.ps1' -File |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.Directory.FullName 'installer\install.ps1') } |
        Select-Object -First 1)
    if ($found.Count -eq 0) { Emit-Broken 5 'no install.ps1 in source archive' }
    $srcRoot = $found[0].Directory.FullName
    if (-not (Test-Path -LiteralPath $AppDir)) { New-Item -ItemType Directory -Force -Path $AppDir | Out-Null }
    Step-Note 7 "deploy source to $AppDir"
    # -LiteralPath НЕ раскрывает '*': копируем именно через -Path (иначе 0 файлов).
    Copy-Item -Path (Join-Path $srcRoot '*') -Destination $AppDir -Recurse -Force
    $entry = Join-Path $AppDir 'installer\install.ps1'
    if (-not (Test-Path -LiteralPath $entry)) { Emit-Broken 5 'extracted source has no installer/install.ps1' }
}

if (-not $parsed.bound.ContainsKey('Check') -and -not $parsed.bound.ContainsKey('Yes')) { $parsed.bound['Yes'] = $true }
# Forward all canonical flags unchanged, including -Steps/-Resume/-Acceptance/-Force.
# ProjectDir — bootstrap-only: оркестратор берёт Root из своего расположения.
$b = $parsed.bound
$b.Remove('ProjectDir') | Out-Null
Step-Note 8 'starting installer'
& $entry @b
exit $LASTEXITCODE
