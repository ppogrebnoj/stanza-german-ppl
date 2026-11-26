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

function Say { param([string]$Text, [string]$Color) if (-not $script:wantsJson) { if ($Color) { Write-Host $Text -ForegroundColor $Color } else { Write-Host $Text } } }
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
if (-not (Test-Path -LiteralPath $flagsLib)) {
    # Standalone one-liner: fetch the two minimal parser files from the release tag.
    $libDir = Split-Path -Parent $flagsLib
    if (-not (Test-Path -LiteralPath $libDir)) { New-Item -ItemType Directory -Force -Path $libDir | Out-Null }
    if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'docs'))) { New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot 'docs') | Out-Null }
    $raw = "https://raw.githubusercontent.com/$Repo/$ReleaseTag"
    & curl.exe -fL @CurlRetry -o $flagsLib "$raw/installer/lib/flags.ps1" 2>$null
    & curl.exe -fL @CurlRetry -o (Join-Path $PSScriptRoot 'docs\flags.json') "$raw/docs/flags.json" 2>$null
}
# Парсер и реестр — это доставка, пока нет installer/install.ps1: код 5, а не 4.
if (-not (Test-Path -LiteralPath $flagsLib)) { Emit-Broken 5 'flags parser not delivered' $true }
. $flagsLib
$regPath = Join-Path $PSScriptRoot 'docs\flags.json'
if (-not (Test-Path -LiteralPath $regPath)) { $regPath = Join-Path $AppDir 'docs\flags.json' }
try { $reg = Read-FlagsRegistry -Path $regPath } catch { Emit-Broken 5 "flags registry not delivered: $_" $true }
$parsed = Convert-InstallerArgs -Rest $Rest -Registry $reg
$script:wantsJson = $parsed.bound.ContainsKey('Json')
if ($script:wantsJson) { try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { } }
if ($parsed.errors.Count) { Emit-Broken 4 ($parsed.errors -join '; ') }

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
    Say "downloading source: $ReleaseBase/stanza-german-ppl-source.zip" Cyan
    & curl.exe -fL @CurlRetry -o $zip "$ReleaseBase/stanza-german-ppl-source.zip" 2>$null
    if ($LASTEXITCODE -ne 0) { Emit-Broken 5 'source download failed' $true }
    & curl.exe -fL @CurlRetry -o $sha "$ReleaseBase/stanza-german-ppl-source.zip.sha256" 2>$null
    if (Test-Path -LiteralPath $sha) {
        $want = ((Get-Content -LiteralPath $sha -Raw -Encoding ASCII) -split '\s+')[0].ToLowerInvariant()
        $got = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($want -and $want -ne $got) { Emit-Broken 5 "source SHA256 mismatch: $want != $got" }
    } else { Emit-Broken 5 'source .sha256 missing' $true }
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
    # -LiteralPath НЕ раскрывает '*': копируем именно через -Path (иначе 0 файлов).
    Copy-Item -Path (Join-Path $srcRoot '*') -Destination $AppDir -Recurse -Force
    $entry = Join-Path $AppDir 'installer\install.ps1'
    if (-not (Test-Path -LiteralPath $entry)) { Emit-Broken 5 'extracted source has no installer/install.ps1' }
}

if (-not $parsed.bound.ContainsKey('Check') -and -not $parsed.bound.ContainsKey('Yes')) { $parsed.bound['Yes'] = $true }
# Forward all canonical flags unchanged, including -Steps/-Resume/-Acceptance/-Force.
$b = $parsed.bound
& $entry @b
exit $LASTEXITCODE
