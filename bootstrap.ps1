#Requires -Version 5.1
<#
    bootstrap.ps1 — ОДИН файл для чистой Windows x64: поднимает winget, получает исходники
    проекта из GitHub Release (постоянный адрес latest/download), проверяет SHA256 и
    запускает install.ps1 с теми же параметрами вызова.

        curl.exe -L -o bootstrap.ps1 https://github.com/ppogrebnoj/stanza-german-ppl/releases/latest/download/bootstrap.ps1
        (Get-FileHash .\bootstrap.ps1 -Algorithm SHA256).Hash
        powershell -ExecutionPolicy Bypass -File .\bootstrap.ps1

    Секретов нет. Полный прогон работает без вопросов: bootstrap сам добавляет -Yes,
    если человек не задал -Check (установка системного софта — смысл bootstrap).
    Коды и NDJSON/JSON — те же, что у install.ps1 (текущий контракт).
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)][object[]]$Rest
)

$ErrorActionPreference = 'Continue'
$Repo = 'ppogrebnoj/stanza-german-ppl'
$ReleaseBase = "https://github.com/$Repo/releases/latest/download"
$AppDir = Join-Path $env:LOCALAPPDATA 'stanza-german-ppl\app'
$Work = Join-Path $env:TEMP 'stanza-german-bootstrap'
$Code_Ready = 0; $Code_Human = 2; $Code_Step = 3; $Code_Broken = 4

# реестр ключей: тот же, что docs/flags.json (bootstrap не содержит секретов и не читает токены)
$switchNames = @('Yes','Acceptance','Json','ProgressJson','Resume','Venv','Force','Repair','Uninstall','Update','CheckUpdates','RaisePython','MakeOfflineKit','Inventory','InventoryOnly','CheckOnly','DryRun')
$valueNames = @('Check','ArtifactDir','Python','TargetDir','ModelsDir','Models','OfflineKit','Steps','Retries','Zip','Log')
$allowed = @($switchNames + $valueNames)

$bound = @{}
$bad = @()
$i = 0
while ($Rest -and $i -lt $Rest.Count) {
    $a = "$($Rest[$i])"
    if ($a -like '-*') {
        $name = $a.TrimStart('-')
        if ($allowed -notcontains $name) { $bad += "неизвестный параметр -$name"; $i++; continue }
        if ($switchNames -contains $name) { $bound[$name] = $true; $i++ }
        else {
            if ($i + 1 -ge $Rest.Count -or "$($Rest[$i+1])" -like '-*') { $bad += "-$name требует значения"; $i++ }
            else { $bound[$name] = "$($Rest[$i+1])"; $i += 2 }
        }
    } else { $i++ }
}
$wantsJson = $bound.ContainsKey('Json')
if ($wantsJson) { try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { } }
function Say { param([string]$Text, [string]$Color)
    if ($wantsJson) { return }
    if ($Color) { Write-Host $Text -ForegroundColor $Color } else { Write-Host $Text }
}
function Emit-Broken { param([int]$Code, [string]$Detail, [bool]$Retryable = $false)
    if ($wantsJson) {
        [Console]::Out.WriteLine(([pscustomobject][ordered]@{
            code = $Code; ok = $false
            failures = @([pscustomobject]@{ id = 'bootstrap'; detail = $Detail; retryable = $Retryable })
        } | ConvertTo-Json -Depth 5))
    } else { Say "bootstrap: $Detail" Red }
    exit $Code
}
if ($bad.Count) { Emit-Broken $Code_Broken (($bad -join '; ')) }

$arch = $env:PROCESSOR_ARCHITEW6432
if (-not $arch) { $arch = $env:PROCESSOR_ARCHITECTURE }
if (-not $arch) { $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture }
$arch = (($arch -replace '^x86[-_]?64$', 'AMD64' -replace '^x64$', 'AMD64')).ToUpperInvariant()
if ($arch -ne 'AMD64' -or [IntPtr]::Size -ne 8) {
    Emit-Broken $Code_Broken "нужна Windows x64 (AMD64), 64-битный PowerShell; текущая: $arch / $([IntPtr]::Size * 8) бит. Загрузки не начинались"
}

$checkMode = "$($bound['Check'])".ToLowerInvariant()
if ($bound.ContainsKey('Inventory') -or $bound.ContainsKey('InventoryOnly')) { $checkMode = 'inventory' }
if ($bound.ContainsKey('CheckOnly')) { $checkMode = 'ready' }
if ($bound.ContainsKey('DryRun')) { $checkMode = 'plan' }
$readOnly = [bool]$checkMode

if (-not $readOnly) {
    # 1. winget (App Installer) — PSGallery + Repair-WinGetPackageManager -AllUsers.
    # Неблокирующий шаг: при отсутствии Магазина install.ps1 ставит софт прямыми ссылками.
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Say 'winget не найден: поднимаю Microsoft.WinGet.Client из PSGallery' Yellow
        try {
            Install-Module Microsoft.WinGet.Client -Force -Repository PSGallery -Scope CurrentUser -ErrorAction Stop
            Import-Module Microsoft.WinGet.Client -Force -ErrorAction Stop
            Repair-WinGetPackageManager -AllUsers -ErrorAction Stop
        } catch { Say ("winget недоступен, продолжаем по прямой ссылке: " + $_) Yellow }
        try {
            $env:Path = (@([Environment]::GetEnvironmentVariable('Path', 'Machine'),
                           [Environment]::GetEnvironmentVariable('Path', 'User')) | Where-Object { $_ }) -join ';'
        } catch { }
    }

    # 2. исходники из релиза: постоянный latest/download + SHA256 рядом
    if (-not (Test-Path -LiteralPath (Join-Path $AppDir 'install.ps1'))) {
        if (-not (Test-Path -LiteralPath $Work)) { New-Item -ItemType Directory -Force -Path $Work | Out-Null }
        $zip = Join-Path $Work 'stanza-german-ppl-source.zip'
        $sha = Join-Path $Work 'stanza-german-ppl-source.zip.sha256'
        Say "скачиваю исходники: $ReleaseBase/stanza-german-ppl-source.zip" Cyan
        & curl.exe -fL --retry 3 --retry-delay 3 --connect-timeout 20 -4 --http1.1 -o $zip "$ReleaseBase/stanza-german-ppl-source.zip" 2>$null
        $rcZip = $LASTEXITCODE
        if ($rcZip -ne 0) {
            Say 'ассет релиза недоступен: пробую codeload с master' Yellow
            $rcZip = 0
            & curl.exe -fL --retry 3 --connect-timeout 20 -4 --http1.1 -o $zip "https://codeload.github.com/$Repo/zip/refs/heads/master" 2>$null
            $rcZip = $LASTEXITCODE
        }
        if ($rcZip -ne 0) { Emit-Broken $Code_Step 'не скачан архив репозитория (проверьте сеть и HTTPS_PROXY)' $true }
        if (-not (Test-Path -LiteralPath $sha)) {
            & curl.exe -fL --retry 2 --connect-timeout 15 -4 --http1.1 -o $sha "$ReleaseBase/stanza-german-ppl-source.zip.sha256" 2>$null
        }
        if (Test-Path -LiteralPath $sha) {
            $want = ((Get-Content -LiteralPath $sha -Raw -Encoding ASCII) -split '\s+')[0].ToLowerInvariant()
            $got = (Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash.ToLowerInvariant()
            if ($want -and $want -ne $got) { Emit-Broken $Code_Broken "SHA256 архива не совпал: ждали $want, получили $got" }
        } else {
            Say 'ВНИМАНИЕ: .sha256 рядом с архивом нет — целостность не проверена' Yellow
        }
        $stage = Join-Path $Work 'src'
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
        Expand-Archive -LiteralPath $zip -DestinationPath $stage -Force
        $found = Get-ChildItem -LiteralPath $stage -Recurse -Filter install.ps1 -File | Select-Object -First 1
        if (-not $found) { Emit-Broken $Code_Broken 'в архиве нет install.ps1' }
        $srcDir = $found.Directory.FullName
        if (-not (Test-Path -LiteralPath $AppDir)) { New-Item -ItemType Directory -Force -Path $AppDir | Out-Null }
        Copy-Item -LiteralPath (Join-Path $srcDir '*') -Destination $AppDir -Recurse -Force
        Copy-Item -LiteralPath (Join-Path $srcDir '.github') -Destination $AppDir -Recurse -Force -ErrorAction SilentlyContinue
        Say "исходники: $AppDir" Green
    } else {
        Say "исходники уже есть: $AppDir" Cyan
    }
    # bootstrap — это осознанный полный прогон: системный софт ставится без лишнего вопроса.
    if (-not $bound.ContainsKey('Yes')) { $bound['Yes'] = $true }
} elseif (-not (Test-Path -LiteralPath (Join-Path $AppDir 'install.ps1'))) {
    Emit-Broken $Code_Human "режим -Check до первой установки: нет $AppDir\install.ps1; сначала запустите bootstrap.ps1 без -Check"
}

$install = Join-Path $AppDir 'install.ps1'
& $install @bound
exit $LASTEXITCODE
