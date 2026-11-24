#Requires -Version 5.1
<#
    _state.ps1 — артефакты установки v2 (dot-source, без param-блока):
    фиксированные имена в -ArtifactDir, mutex параллельных прогонов, отчёты и
    mcp-snippet.json (UTF-8 без BOM, кириллица в \uXXXX).

    В -Check режимах НИ ОДНА из функций этого файла не вызывается: check не пишет файлы.
#>

$script:KiMutex = $null

function Initialize-Artifacts {
    param([string]$ArtifactDir, [string[]]$Steps = @())
    if (-not $ArtifactDir) { $ArtifactDir = Get-DefaultArtifactDir }
    if (-not (Test-Path -LiteralPath $ArtifactDir)) {
        New-Item -ItemType Directory -Force -Path $ArtifactDir | Out-Null
    }
    $downloads = Join-Path $ArtifactDir 'downloads'
    if (-not (Test-Path -LiteralPath $downloads)) { New-Item -ItemType Directory -Force -Path $downloads | Out-Null }
    $enc = New-Object System.Text.UTF8Encoding($false)
    foreach ($f in @((Join-Path $ArtifactDir 'install.log'), (Join-Path $ArtifactDir 'progress.ndjson'))) {
        [IO.File]::WriteAllText($f, '', $enc)
    }
    # параллельные прогоны одного каталога артефактов разделяет mutex
    $key = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((Resolve-Path -LiteralPath $ArtifactDir).Path))
    if ($key.Length -gt 100) { $key = $key.Substring(0, 100) }
    $name = 'Global\stanza-german-install-' + $key
    $m = New-Object System.Threading.Mutex($false, $name)
    $got = $false
    try { $got = $m.WaitOne(10000) } catch { $got = $false }
    if (-not $got) {
        $m.Dispose()
        throw "другой прогон уже работает с $ArtifactDir (mutex $name)"
    }
    $script:KiMutex = $m
    return $ArtifactDir
}

function Release-Artifacts {
    if ($script:KiMutex) {
        try { $script:KiMutex.ReleaseMutex() } catch { }
        try { $script:KiMutex.Dispose() } catch { }
        $script:KiMutex = $null
    }
}

function Add-LogLine {
    param([string]$ArtifactDir, [string]$Text)
    if (-not $ArtifactDir) { return }
    $safe = [regex]::Replace("$Text", '(gh[pou]_[A-Za-z0-9_]{8,}|github_pat_[A-Za-z0-9_]{8,})', '$1***')
    try {
        [IO.File]::AppendAllText((Join-Path $ArtifactDir 'install.log'),
            ((Get-Date).ToString('HH:mm:ss') + ' ' + $safe + "`n"), (New-Object System.Text.UTF8Encoding($false)))
    } catch { }
}

# ConvertTo-Json в PS 5.1 оставляет кириллицу буквами; контракт требует \uXXXX.
function ConvertTo-JsonAscii {
    param([string]$Json)
    $sb = New-Object System.Text.StringBuilder
    foreach ($ch in $Json.ToCharArray()) {
        $code = [int]$ch
        if ($code -gt 127) {
            [void]$sb.Append('\u' + $code.ToString('x4'))
        } else {
            [void]$sb.Append($ch)
        }
    }
    return $sb.ToString()
}

function Write-JsonNoBom {
    param([string]$Path, [string]$Json)
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
    $tmp = "$Path.tmp"
    [IO.File]::WriteAllText($tmp, $Json, (New-Object System.Text.UTF8Encoding($false)))
    Move-Item -LiteralPath $tmp -Destination $Path -Force
}

function Save-Report {
    param([hashtable]$Report, [string]$ArtifactDir)
    $json = $Report | ConvertTo-Json -Depth 12
    $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ')
    Write-JsonNoBom -Path (Join-Path $ArtifactDir 'install-report.json') -Json $json
    Write-JsonNoBom -Path (Join-Path $ArtifactDir "install-report-$stamp.json") -Json $json
    return (Join-Path $ArtifactDir 'install-report.json')
}

function Save-McpSnippet {
    param([string]$ArtifactDir, [string]$Root, [string]$Json)
    $body = ConvertTo-JsonAscii $Json
    $path = Join-Path $ArtifactDir 'mcp-snippet.json'
    Write-JsonNoBom -Path $path -Json $body
    try { Write-JsonNoBom -Path (Join-Path $Root 'mcp-snippet.json') -Json $body } catch { }
    return $path
}
