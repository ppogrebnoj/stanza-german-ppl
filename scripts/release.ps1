#Requires -Version 5.1
<#
    release.ps1 — сборка ассетов релиза установки (вызывается CI по тегу v*).

    Версия берётся из первого заголовка MCP-stanza-german/CHANGELOG.md:
        ## 4.0.2 (2026-11-17)  ->  тег v4.0.2
    Ассеты: bootstrap.ps1(.sha256) и stanza-german-ppl-source.zip(.sha256).
    Хеш bootstrap.ps1 НЕ пишется в README: он публикуется рядом с установщиком
    и проверяется человеком/агентом из того же релиза.
#>
[CmdletBinding()]
param(
    [string]$Root = '',
    [string]$OutDir = '',
    [string]$Tag = ''
)
$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path }
if (-not $OutDir) { $OutDir = Join-Path $Root '.tmp\release' }
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Get-Sha { param([string]$Path) (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Get-ProjectVersion {
    param([string]$ProjectRoot)
    $changelog = Join-Path $ProjectRoot 'MCP-stanza-german\CHANGELOG.md'
    if (-not (Test-Path -LiteralPath $changelog)) { throw 'нет MCP-stanza-german/CHANGELOG.md — неоткуда взять версию' }
    $text = [IO.File]::ReadAllText($changelog, $utf8)
    $m = [regex]::Match($text, '(?m)^##\s+(\d+\.\d+\.\d+)(?:\s|$)')
    if (-not $m.Success) { throw 'в CHANGELOG.md нет заголовка версии вида "## 4.0.2"' }
    return $m.Groups[1].Value
}

$version = Get-ProjectVersion $Root
if (-not $Tag) { $Tag = "v$version" }
if ($Tag -ne "v$version") {
    throw "тег $Tag не совпадает с версией CHANGELOG.md (v$version); версию берём оттуда"
}

$bootstrap = Join-Path $Root 'bootstrap.ps1'
if (-not (Test-Path -LiteralPath $bootstrap)) { throw 'нет bootstrap.ps1' }
$sum = Get-Sha $bootstrap
[IO.File]::WriteAllText((Join-Path $Root 'bootstrap.ps1.sha256'), "$sum  bootstrap.ps1`n", $utf8)
Copy-Item -LiteralPath $bootstrap -Destination (Join-Path $OutDir 'bootstrap.ps1') -Force
[IO.File]::WriteAllText((Join-Path $OutDir 'bootstrap.ps1.sha256'), "$sum  bootstrap.ps1`n", $utf8)

$stage = Join-Path $OutDir 'source'
if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
New-Item -ItemType Directory -Force -Path $stage | Out-Null
$skip = @('.git', '.tmp', '.venv', '.stanza', '__pycache__')
Get-ChildItem -LiteralPath $Root -Force | Where-Object { $skip -notcontains $_.Name } | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $stage -Recurse -Force
}
$zip = Join-Path $OutDir 'stanza-german-ppl-source.zip'
if (Test-Path -LiteralPath $zip) { Remove-Item -LiteralPath $zip -Force }
Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zip -CompressionLevel Optimal
$zsum = Get-Sha $zip
[IO.File]::WriteAllText("$zip.sha256", "$zsum  stanza-german-ppl-source.zip`n", $utf8)

$body = @"
# stanza-german-ppl $version — установка (тег $Tag)

Версия взята из MCP-stanza-german/CHANGELOG.md (совпадает с version.json).

SHA256 bootstrap.ps1: $sum
SHA256 stanza-german-ppl-source.zip: $zsum

``````powershell
curl.exe -L -o bootstrap.ps1 https://github.com/ppogrebnoj/stanza-german-ppl/releases/latest/download/bootstrap.ps1
(Get-FileHash .\bootstrap.ps1 -Algorithm SHA256).Hash
powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1
``````

Хеш установщика лежит рядом с ним в релизе: bootstrap.ps1.sha256.
Агент: -Json, -ProgressJson, install-report.json (schema_version 2), коды 0/2/3/4/6.
"@
[IO.File]::WriteAllText((Join-Path $OutDir 'RELEASE_BODY.md'), $body, $utf8)
Write-Host "version=$version tag=$Tag"
Write-Host "bootstrap.ps1 SHA256=$sum"
Write-Host "source zip SHA256=$zsum"
Write-Host "assets: $OutDir"
