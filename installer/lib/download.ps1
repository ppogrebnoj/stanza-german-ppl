#Requires -Version 5.1
<#
    _download.ps1 — загрузки с ретраями, SHA256 и зеркалами (dot-source, без param-блока).

    * curl.exe: -4 --http1.1 --retry 3 -C - (докачка оборванного), таймауты;
    * фоллбэк Invoke-WebRequest (-UseBasicParsing) если curl недоступен;
    * зеркала: HF_ENDPOINT для huggingface.co и KI_DOWNLOAD_MIRRORS
      (список «префикс=новый_префикс» через ';');
    * preflight Range GET по фактическим ассетам: 200/206 = канал годен;
    * каждая загрузка сверяется с SHA256 (файл .sha256 рядом или явный -Sha256).

    Никаких секретов в логах: токены передаются переменными окружения процесса.
#>

function Get-FileSha256 {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return '' }
    try { return ((Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()) } catch { return '' }
}

function Get-DownloadUrls {
    param([string]$Url)
    $urls = New-Object System.Collections.Generic.List[string]
    if ($Url -and -not $urls.Contains($Url)) { $urls.Add($Url) }
    # HF_ENDPOINT: зеркало Hugging Face (env процесса, не файл настроек)
    if ($Url -match '^https?://(?:www\.)?huggingface\.co(?:/.*)?$' -and $env:HF_ENDPOINT) {
        $mirror = "$($env:HF_ENDPOINT.TrimEnd('/'))" + ($Url -replace '^https?://(?:www\.)?huggingface\.co', '')
        if (-not $urls.Contains($mirror)) { $urls.Add($mirror) }
    }
    # общие зеркала: KI_DOWNLOAD_MIRRORS="https://primary/=https://mirror/;..."
    foreach ($rule in ("$env:KI_DOWNLOAD_MIRRORS" -split ';')) {
        if (-not $rule -or $rule -notmatch '=') { continue }
        $parts = $rule -split '=', 2
        $from = $parts[0].Trim(); $to = $parts[1].Trim()
        if ($from -and $to -and $Url.StartsWith($from, [StringComparison]::OrdinalIgnoreCase)) {
            $mirror = $to + $Url.Substring($from.Length)
            if (-not $urls.Contains($mirror)) { $urls.Add($mirror) }
        }
    }
    return $urls.ToArray()
}

function Test-DownloadPreflight {
    param([string]$Url, [int]$TimeoutSec = 12)
    $code = 0; $detail = ''
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if ($curl) {
        try {
            $out = & curl.exe -sS -4 --http1.1 --connect-timeout 5 --max-time $TimeoutSec `
                     -r 0-0 -o NUL -w '%{http_code}' "$Url" 2>$null
            $code = [int]("$out".Trim())
        } catch { $detail = "$_" }
    } else {
        try {
            $r = Invoke-WebRequest -Uri $Url -Method Head -TimeoutSec $TimeoutSec -UseBasicParsing
            $code = [int]$r.StatusCode
        } catch { $detail = "$_" }
    }
    $ok = ($code -eq 200 -or $code -eq 206)
    return [pscustomobject]@{ ok = $ok; code = $code; url = $Url; detail = $detail }
}

function Invoke-Download {
    param(
        [string]$Url,
        [string]$Dest,
        [string]$Sha256 = '',
        [int]$Retries = 4,
        [string]$DownloadDir = '',
        [scriptblock]$OnProgress
    )
    if (-not $Url -or -not $Dest) { throw 'Invoke-Download: нужны -Url и -Dest' }
    if (-not $DownloadDir) { $DownloadDir = Split-Path -Parent $Dest }
    if ($DownloadDir -and -not (Test-Path -LiteralPath $DownloadDir)) {
        New-Item -ItemType Directory -Force -Path $DownloadDir | Out-Null
    }
    $destDir = Split-Path -Parent $Dest
    if ($destDir -and -not (Test-Path -LiteralPath $destDir)) { New-Item -ItemType Directory -Force -Path $destDir | Out-Null }
    $urls = @(Get-DownloadUrls $Url)
    $expected = $Sha256
    if (-not $expected -and (Test-Path -LiteralPath "$Url.sha256")) {
        $expected = ((Get-Content -LiteralPath "$Url.sha256" -Raw -ErrorAction SilentlyContinue) -split '\s+')[0]
    }
    if (-not $expected -and (Test-Path -LiteralPath "$Dest.sha256")) {
        $expected = ((Get-Content -LiteralPath "$Dest.sha256" -Raw -ErrorAction SilentlyContinue) -split '\s+')[0]
    }
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    $last = ''
    for ($attempt = 1; $attempt -le [math]::Max(1, $Retries); $attempt++) {
        foreach ($u in $urls) {
            $partial = "$Dest.part"
            $rc = -1
            try {
                if ($curl) {
                    $args = @('-fL', '--retry', '2', '--retry-all-errors', '--retry-delay', '3',
                              '--connect-timeout', '20', '--max-time', '3600', '-4', '--http1.1')
                    if (Test-Path -LiteralPath $partial) { $args += @('-C', '-') }
                    $args += @('-o', $partial, "$u")
                    if ($OnProgress) { & $OnProgress @{ ev = 'progress'; pct = 0; url = $u; attempt = $attempt } }
                    & curl.exe @args 2>&1 | Out-Null
                    $rc = $LASTEXITCODE
                } else {
                    if ($OnProgress) { & $OnProgress @{ ev = 'progress'; pct = 0; url = $u; attempt = $attempt } }
                    Invoke-WebRequest -Uri $u -OutFile $partial -TimeoutSec 3600 -UseBasicParsing -ErrorAction Stop
                    $rc = 0
                }
            } catch { $last = "$_"; $rc = -1 }
            if ($rc -eq 0) {
                $got = Get-FileSha256 $partial
                if ($expected -and $got -ne $expected.ToLowerInvariant()) {
                    $last = "SHA256 не совпал: ждали $expected, получили $got ($u)"
                    Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
                    continue
                }
                Move-Item -LiteralPath $partial -Destination $Dest -Force
                if ($OnProgress) {
                    $len = (Get-Item -LiteralPath $Dest).Length
                    & $OnProgress @{ ev = 'done'; pct = 100; bytes = $len; url = $u; sha256 = $got }
                }
                return [pscustomobject]@{ ok = $true; path = $Dest; sha256 = $got; url = $u; bytes = (Get-Item -LiteralPath $Dest).Length }
            }
            $last = "curl rc=$rc; $last"
            if ($rc -eq 33) {   # сервер не-understands Range — начинаем с нуля
                Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
            }
            if ($attempt -lt $Retries) { Start-Sleep -Seconds ([math]::Min(15, 3 * $attempt)) }
        }
    }
    return [pscustomobject]@{ ok = $false; path = ''; sha256 = ''; url = $Url; bytes = 0; detail = $last }
}
