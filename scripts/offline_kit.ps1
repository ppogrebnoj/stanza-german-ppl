#Requires -Version 5.1
<#
    offline_kit.ps1 — офлайн-набор: архив репозитория + колёса + модели, с SHA256.

        powershell -File scripts\offline_kit.ps1 -Action make -TargetDir <root> -ArtifactDir <root>\.tmp -Python <python.exe>
        powershell -File scripts\offline_kit.ps1 -Action unpack -Archive <zip> -TargetDir <root> -ModelsDir <models>

    make:  pip download --only-binary=:all: -r requirements.lock -d <tmp>\wheels
    unpack: сверка SHA256 -> распаковка -> копирование исходников/моделей.
    Перезапись существует только с -Force.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateSet('make','unpack')][string]$Action,
    [string]$TargetDir = '',
    [string]$ArtifactDir = '',
    [string]$Archive = '',
    [string]$ModelsDir = '',
    [string]$Python = '',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
if (-not $TargetDir) { $TargetDir = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path }
if (-not $ArtifactDir) { $ArtifactDir = Join-Path $TargetDir '.tmp' }
if (-not (Test-Path -LiteralPath $ArtifactDir)) { New-Item -ItemType Directory -Force -Path $ArtifactDir | Out-Null }

function Get-Sha { param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function New-Kit {
    $staging = Join-Path $ArtifactDir 'offline-stage'
    if (Test-Path -LiteralPath $staging) { Remove-Item -LiteralPath $staging -Recurse -Force }
    $repo = Join-Path $staging 'repo'; $wheels = Join-Path $staging 'wheels'; $models = Join-Path $staging 'models'
    foreach ($d in @($repo, $wheels, $models)) { New-Item -ItemType Directory -Force -Path $d | Out-Null }
    $exclude = @('.git','.tmp','.venv','__pycache__','.pytest_cache','.stanza')
    Get-ChildItem -LiteralPath $TargetDir -Force | Where-Object { $exclude -notcontains $_.Name } | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $repo -Recurse -Force
    }
    $py = $Python
    if (-not $py -and (Test-Path -LiteralPath (Join-Path $TargetDir '.venv\Scripts\python.exe'))) {
        $py = Join-Path $TargetDir '.venv\Scripts\python.exe'
    }
    if (-not $py) {
        try { $py = (& python -c "import sys;print(sys.executable)" 2>$null | Select-Object -First 1) } catch { }
    }
    if ($py -and (Test-Path -LiteralPath $py)) {
        & $py -m pip download --only-binary=:all: --dest $wheels -r (Join-Path $TargetDir 'requirements.lock')
        if ($LASTEXITCODE -ne 0) { throw 'pip download колёс не удался (нужен --only-binary=:all:)' }
    } else {
        Write-Warning 'Python не найден: каталог wheels будет пустым'
    }
    $md = if ($ModelsDir) { $ModelsDir } else { Join-Path $TargetDir '.stanza\models' }
    if (Test-Path -LiteralPath $md) { Copy-Item -LiteralPath (Join-Path $md '*') -Destination $models -Recurse -Force }
    $zip = Join-Path $ArtifactDir 'stanza-offline-kit.zip'
    if (Test-Path -LiteralPath $zip) {
        if (-not $Force) { throw "есть $zip; нужен -Force для перезаписи" }
        Remove-Item -LiteralPath $zip -Force
    }
    Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $zip -CompressionLevel Optimal
    $hash = Get-Sha $zip
    [IO.File]::WriteAllText("$zip.sha256", "$hash  stanza-offline-kit.zip`n", (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "готово: $zip (SHA256 $hash)"
}

function Expand-Kit {
    if (-not $Archive -or -not (Test-Path -LiteralPath $Archive)) { throw "нет архива $Archive" }
    if (Test-Path -LiteralPath "$Archive.sha256") {
        $want = (Get-Content -LiteralPath "$Archive.sha256" -Raw -Encoding ASCII).Trim().Split()[0]
        $got = Get-Sha $Archive
        if ($want -and $want.ToLowerInvariant() -ne $got) { throw "SHA256 не совпал: $want != $got" }
    } else { Write-Warning 'нет .sha256 рядом с архивом — проверка суммы пропущена' }
    $unpack = Join-Path $ArtifactDir 'offline-unpack'
    if (Test-Path -LiteralPath $unpack) { Remove-Item -LiteralPath $unpack -Recurse -Force }
    Expand-Archive -LiteralPath $Archive -DestinationPath $unpack -Force
    $src = Join-Path $unpack 'repo'
    if (Test-Path -LiteralPath $src) {
        Get-ChildItem -LiteralPath $src -Force | ForEach-Object {
            $dst = Join-Path $TargetDir $_.Name
            if (Test-Path -LiteralPath $dst) {
                if (-not $Force) { throw "файл уже есть: $dst (нужен -Force)" }
                Remove-Item -LiteralPath $dst -Recurse -Force
            }
            Copy-Item -LiteralPath $_.FullName -Destination $dst -Recurse -Force
        }
    }
    $md = if ($ModelsDir) { $ModelsDir } else { Join-Path $TargetDir '.stanza\models' }
    $models = Join-Path $unpack 'models'
    if (Test-Path -LiteralPath $models) {
        if (-not (Test-Path -LiteralPath $md)) { New-Item -ItemType Directory -Force -Path $md | Out-Null }
        Copy-Item -LiteralPath (Join-Path $models '*') -Destination $md -Recurse -Force:$Force
    }
    Write-Host "распаковано: репозиторий $TargetDir; модели $md"
}

if ($Action -eq 'make') { New-Kit } else { Expand-Kit }
