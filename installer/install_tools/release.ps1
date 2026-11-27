#Requires -Version 5.1
<#
    release.ps1 — сборка ассетов релиза установки (вызывается CI по тегу v*).

    Версия берётся из MCP-stanza-german/version.json (единственный источник):
        "server_version": "4.0.6"  ->  тег v4.0.6
    Ассеты: bootstrap.ps1(.sha256), stanza-german-ppl-source.zip(.sha256)
    и RELEASE_BODY.md (одновременно --notes-file и плоский ассет).
    Хеши и коды выхода в теле релиза НЕ захардкожены: они читаются из
    .sha256-файлов и docs/flags.json. Хеш в README не публикуется.
#>
[CmdletBinding()]
param(
    [string]$Root = '',
    [string]$OutDir = '',
    [string]$Tag = ''
)
$ErrorActionPreference = 'Stop'
if (-not $Root) { $Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path }
if (-not $OutDir) { $OutDir = Join-Path $Root '.tmp\release' }
if (-not (Test-Path -LiteralPath $OutDir)) { New-Item -ItemType Directory -Force -Path $OutDir | Out-Null }
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Get-Sha { param([string]$Path) (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Get-ProjectVersion {
    param([string]$ProjectRoot)
    $vjson = Join-Path $ProjectRoot 'MCP-stanza-german\version.json'
    if (-not (Test-Path -LiteralPath $vjson)) { throw 'нет MCP-stanza-german/version.json — неоткуда взять версию' }
    try { $data = [IO.File]::ReadAllText($vjson, $utf8) | ConvertFrom-Json } catch { throw "version.json не парсится: $_" }
    $version = [string]$data.server_version
    if ($version -notmatch '^\d+\.\d+\.\d+$') { throw "version.json: некорректная версия '$version'" }
    return $version
}

$version = Get-ProjectVersion $Root
if (-not $Tag) { $Tag = "v$version" }
if ($Tag -ne "v$version") {
    throw "тег $Tag не совпадает с версией version.json (v$version); версию берём оттуда"
}

$bootstrap = Join-Path $Root 'bootstrap.ps1'
if (-not (Test-Path -LiteralPath $bootstrap)) { throw 'нет bootstrap.ps1' }
$sumComputed = Get-Sha $bootstrap
# Контрольная сумма лежит рядом с bootstrap.ps1 в корне и публикуется плоским ассетом.
$sumFile = Join-Path $Root 'bootstrap.ps1.sha256'
[IO.File]::WriteAllText($sumFile, "$sumComputed  bootstrap.ps1`n", $utf8)
# Тело релиза берёт хеш из .sha256-файла, а не из захардкоженной строки.
$sum = (((Get-Content -LiteralPath $sumFile -Raw -Encoding ASCII) -split '\s+')[0]).ToLowerInvariant()
if ($sum -ne $sumComputed) { throw "bootstrap.ps1.sha256 не совпадает с файлом: $sum != $sumComputed" }
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
# Не Compress-Archive: он не ставит флаг UTF-8 у имён внутри архива, и кириллица
# распаковывается как «ð+ÐÇð¦ð¦ð©ð+ð¥» вместо «правило». CreateFromDirectory с явным
# entryNameEncoding=UTF8 записывает флаг, и имена читаются правильно везде.
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    $stage, $zip,
    [System.IO.Compression.CompressionLevel]::Optimal,
    $false,
    (New-Object System.Text.UTF8Encoding($false)))
$zsumComputed = Get-Sha $zip
[IO.File]::WriteAllText("$zip.sha256", "$zsumComputed  stanza-german-ppl-source.zip`n", $utf8)
$zsum = (((Get-Content -LiteralPath "$zip.sha256" -Raw -Encoding ASCII) -split '\s+')[0]).ToLowerInvariant()
if ($zsum -ne $zsumComputed) { throw "source.zip.sha256 не совпадает с архивом: $zsum != $zsumComputed" }

# Единственный источник кодов выхода — реестр флагов; код 6 больше не существует.
$regPath = Join-Path $Root 'docs\flags.json'
if (-not (Test-Path -LiteralPath $regPath)) { throw 'нет docs/flags.json' }
$reg = Get-Content -LiteralPath $regPath -Raw -Encoding UTF8 | ConvertFrom-Json
$codes = @($reg.exit_codes.PSObject.Properties | Sort-Object { [int]$_.Name } |
    ForEach-Object { "$($_.Name): $($_.Value)" }) -join '; '
if (-not $codes) { throw 'docs/flags.json: пустые exit_codes' }

# Одинарный here-string: $base/$want/$got остаются буквальными в сниппете.
$template = @'
# stanza-german-ppl __VERSION__ — установка (тег __TAG__)

Версия взята из MCP-stanza-german/version.json. Хеши ниже прочитаны из ассетов этого релиза.

SHA256 bootstrap.ps1: __SUM__
SHA256 stanza-german-ppl-source.zip: __ZSUM__

```powershell
$base = "https://github.com/ppogrebnoj/stanza-german-ppl/releases/latest/download"
curl.exe -L --retry 4 --retry-all-errors --retry-delay 2 -o bootstrap.ps1 "$base/bootstrap.ps1"
curl.exe -L --retry 4 --retry-all-errors --retry-delay 2 -o bootstrap.ps1.sha256 "$base/bootstrap.ps1.sha256"
$want = ((Get-Content .\bootstrap.ps1.sha256 -Raw).Trim() -split '\s+')[0].ToLowerInvariant()
$got = (Get-FileHash .\bootstrap.ps1 -Algorithm SHA256).Hash.ToLowerInvariant()
if ($got -ne $want) { throw "SHA256 mismatch: $got != $want" }
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 -Yes
```

Коды выхода (docs/flags.json): __CODES__.
Агент: -Json, -ProgressJson, install-report.json, progress.ndjson.
Без -Json в консоли видны шаги n/11, объём загрузки и ETA.
'@
$body = $template.Replace('__VERSION__', $version).Replace('__TAG__', $Tag).
    Replace('__SUM__', $sum).Replace('__ZSUM__', $zsum).Replace('__CODES__', $codes)
[IO.File]::WriteAllText((Join-Path $OutDir 'RELEASE_BODY.md'), $body, $utf8)
Write-Host "version=$version tag=$Tag"
Write-Host "bootstrap.ps1 SHA256=$sum"
Write-Host "source zip SHA256=$zsum"
Write-Host "assets: $OutDir"
