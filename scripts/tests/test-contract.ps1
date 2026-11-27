#Requires -Version 5.1
<#
    test-contract.ps1 — регресс текущего контракта без Python и сети.

        powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\test-contract.ps1

    Проверяет: неизвестный параметр = код 4, -Check только чтение, capabilities = docs/flags.json,
    поля отчёта, NDJSON в файле, Resume SKIP,
    нормализацию архитектуры. Код выхода 0 = все тесты зелёные.
#>
$ErrorActionPreference = 'Continue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$entry = Join-Path $root 'install.ps1'
$failures = @()
$total = 0

function Check-Ok { param([bool]$Ok, [string]$Name, [string]$Detail = '')
    $script:total++
    if ($Ok) { Write-Host ("  PASS  " + $Name) -ForegroundColor Green }
    else { Write-Host ("  FAIL  " + $Name + " :: " + $Detail) -ForegroundColor Red; $script:failures += $Name }
}
function Invoke-Ki {
    param([string]$File, [string[]]$ArgList)
    $lines = @(& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $File @ArgList 2>&1 | ForEach-Object { "$_" })
    $rc = $LASTEXITCODE
    $final = $null
    $start = -1
    # итоговый JSON начинается с '{' без отступа; вложенные объекты ConvertTo-Json indentation
    for ($i = 0; $i -lt $lines.Count; $i++) {
        if ("$($lines[$i])" -match '^\{\r?$') { $start = $i; break }
    }
    if ($start -ge 0) {
        $tail = @($lines[$start..($lines.Count - 1)])
        try { $final = ($tail -join [Environment]::NewLine) | ConvertFrom-Json } catch { }
    }
    return [pscustomobject]@{ rc = $rc; lines = $lines; json = $final }
}

Write-Host "текущий контракт: $root" Cyan

# 1. неизвестный параметр
$r = Invoke-Ki $entry @('-Bogus','1','-Json')
Check-Ok ($r.rc -eq 4 -and $r.json -and $r.json.code -eq 4) 'unknown flag => code 4' ("rc=" + $r.rc + " out=" + ($r.lines -join ' '))

# 2. capabilities == docs/flags.json
$r1 = Invoke-Ki $entry @('-Check','capabilities','-Json')
$reg = Get-Content -LiteralPath (Join-Path $root 'docs\flags.json') -Raw -Encoding UTF8 | ConvertFrom-Json
$namesReg = @($reg.flags | ForEach-Object { $_.name }) -join ','
$namesOut = @($r1.json.capabilities.flags | ForEach-Object { $_.name }) -join ','
Check-Ok ($r1.rc -eq 0 -and $namesReg -eq $namesOut) 'capabilities == docs/flags.json' ("reg=$namesReg out=$namesOut")

# 2b. bootstrap.ps1 delegates argument parsing to installer/lib/flags.ps1
$bootText = [IO.File]::ReadAllText((Join-Path $root 'bootstrap.ps1'))
$bootOk = $bootText.Contains('Convert-InstallerArgs') -and $bootText.Contains('Read-FlagsRegistry') -and -not ($bootText -match '\$switchNames')
Check-Ok $bootOk 'bootstrap delegates flags registry' "delegated=$bootOk"

# 3. -Check не пишет файлы
$tmp = Join-Path $env:TEMP ('ki-contract-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmp | Out-Null
$before = @(Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName + '|' + $_.Length })
$r = Invoke-Ki $entry @('-Check','inventory','-Json','-ArtifactDir',$tmp)
$after = @(Get-ChildItem -LiteralPath $root -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object { $_.FullName + '|' + $_.Length })
Check-Ok (-not (Get-ChildItem -LiteralPath $tmp -Force | Where-Object { $_.Name -notlike 'ki-*' }) -and ($before -join "`n") -eq ($after -join "`n")) 'check modes are read-only' ('artifact dir: ' + ((Get-ChildItem $tmp -Force | Select-Object -ExpandProperty Name) -join ','))

# 4. -Check mcp explains the reason
$r = Invoke-Ki $entry @('-Check','mcp','-Json')
Check-Ok ($r.rc -eq 2 -and "$($r.json.detail)" -match 'mcp-snippet') 'check mcp explains reason' ("rc=" + $r.rc + " " + $r.json.detail)

# 5. отчёт + NDJSON в файле
$art = Join-Path $tmp 'art'
$r = Invoke-Ki $entry @('-Steps','doctor','-Json','-ArtifactDir',$art)
$report = $null
try { $report = Get-Content -LiteralPath (Join-Path $art 'install-report.json') -Raw -Encoding UTF8 | ConvertFrom-Json } catch { }
$need = @('code','ok','phase','root','python','precheck_report','report','steps')
$missing = @($need | Where-Object { $null -eq $report.PSObject.Properties[$_] })
Check-Ok (@(0, 1, 2, 3) -contains $r.json.code -and $missing.Count -eq 0 -and (Test-Path -LiteralPath (Join-Path $art 'install.log'))) 'report fields and artifacts' ("code=" + $r.json.code + " missing=" + ($missing -join ','))
$ndjson = @(Get-Content -LiteralPath (Join-Path $art 'progress.ndjson') -ErrorAction SilentlyContinue | Where-Object { $_.Trim() })
$parsed = 0
foreach ($line in $ndjson) { try { $null = $line | ConvertFrom-Json; $parsed++ } catch { } }
Check-Ok ($parsed -eq $ndjson.Count -and $parsed -gt 0) 'progress.ndjson parses line by line' ("$parsed/$($ndjson.Count)")
Check-Ok (Test-Path -LiteralPath (Join-Path $art 'install-report-precheck.json')) 'precheck report saved'

# 6. Resume: готовый шаг -> SKIP
$seed = [ordered]@{ code = 0; steps = @([pscustomobject]@{ id='doctor'; status='OK'; seconds=1; detail='seed' }) }
[IO.File]::WriteAllText((Join-Path $art 'install-report.json'), ($seed | ConvertTo-Json -Depth 5), (New-Object System.Text.UTF8Encoding($false)))
$r = Invoke-Ki $entry @('-Steps','doctor','-Resume','-Json','-ArtifactDir',$art)
Check-Ok ($r.rc -eq 0 -and $r.json.steps[0].status -eq 'SKIP') 'Resume skips ready steps' ("rc=" + $r.rc + " status=" + $r.json.steps[0].status)

# 7. нормализация архитектуры
$env:_KI_SAVED_ARCH = $env:PROCESSOR_ARCHITECTURE
$env:_KI_SAVED_WOW = $env:PROCESSOR_ARCHITEW6432
. (Join-Path $root 'installer\lib\env.ps1')
$env:PROCESSOR_ARCHITECTURE = 'x86'; $env:PROCESSOR_ARCHITEW6432 = 'AMD64'
$a1 = Get-MachineArch
$env:PROCESSOR_ARCHITECTURE = 'x86_64'; $env:PROCESSOR_ARCHITEW6432 = ''
$a2 = Get-MachineArch
$env:PROCESSOR_ARCHITECTURE = $env:_KI_SAVED_ARCH; $env:PROCESSOR_ARCHITEW6432 = $env:_KI_SAVED_WOW
Remove-Item Env:\_KI_SAVED_ARCH -ErrorAction SilentlyContinue; Remove-Item Env:\_KI_SAVED_WOW -ErrorAction SilentlyContinue
Check-Ok ($a1 -eq 'AMD64' -and $a2 -eq 'AMD64') 'arch normalization' ("$a1 / $a2")

# 8. файлы установки лежат в installer\; хеш bootstrap.ps1 — рядом с bootstrap.ps1 в корне
$needInstaller = @('INSTALL.md', 'requirements.txt', 'requirements.lock')
$missingInstaller = @($needInstaller | Where-Object { -not (Test-Path -LiteralPath (Join-Path $root ('installer\' + $_))) })
$rootLeftovers = @($needInstaller | Where-Object { Test-Path -LiteralPath (Join-Path $root $_) })
Check-Ok ($missingInstaller.Count -eq 0 -and $rootLeftovers.Count -eq 0 -and
          (Test-Path -LiteralPath (Join-Path $root 'bootstrap.ps1')) -and
          (Test-Path -LiteralPath (Join-Path $root 'bootstrap.ps1.sha256')) -and
          (Test-Path -LiteralPath (Join-Path $root 'installer\install.ps1'))) 'installer layout' ("missing=$($missingInstaller -join ',') root=$($rootLeftovers -join ',')")

# 9. venv BLOCK -> rc=2 and next_cmd contains -Steps venv,deps
. (Join-Path $root 'installer\lib\common.ps1')
. (Join-Path $root 'installer\lib\steps\venv.ps1')
$fakeRoot = Join-Path $tmp 'fake-root'
New-Item -ItemType Directory -Force -Path (Join-Path $fakeRoot '.venv\Scripts') | Out-Null
[IO.File]::WriteAllText((Join-Path $fakeRoot '.venv\pyvenv.cfg'), '', (New-Object System.Text.UTF8Encoding($false)))
[IO.File]::WriteAllText((Join-Path $fakeRoot '.venv\Scripts\python.exe'), 'not-an-exe', (New-Object System.Text.UTF8Encoding($false)))
$venvCtx = [pscustomobject]@{ Root = $fakeRoot; ArtifactDir = $art; Python = ''; TargetDir = ''; Force = $false }
$rv = Invoke-Step_venv $venvCtx 2>$null
Check-Ok ($rv.status -eq 'BLOCK' -and $rv.rc -eq 2 -and "$($rv.next_cmd)" -match '\-Steps\s+venv,deps') 'venv BLOCK rc=2 next_cmd' ("status=$($rv.status) rc=$($rv.rc) next=$($rv.next_cmd)")

# 10. deps conflict after clean lock install -> rc=1 non-retryable
$badLock = Join-Path $tmp 'bad.lock'
[IO.File]::WriteAllText($badLock, "ImpossiblePackage==0.0.0`n", (New-Object System.Text.UTF8Encoding($false)))
if (-not (Test-Path -LiteralPath $art)) { New-Item -ItemType Directory -Force -Path $art | Out-Null }
Set-LockInstalledMarker -ArtifactDir $art
$ciPy = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $ciPy) { $ciPy = (Get-Command py -ErrorAction SilentlyContinue).Source }
$ds = Test-DepsState -Root $root -ArtifactDir $art -LockPath $badLock -PythonPath $ciPy
Check-Ok ((-not $ds.ok) -and $ds.rc -eq 1 -and (-not $ds.retryable)) 'deps lock conflict rc=1 non-retryable' ("rc=$($ds.rc) retryable=$($ds.retryable)")
Remove-LockInstalledMarker -ArtifactDir $art

# 11. 2/BLOCK and 5/DELIVERY are different scenarios
$r2 = Invoke-Ki $entry @('-Check','mcp','-Json')
$missingKit = Join-Path $tmp 'missing-kit.zip'
$r5 = Invoke-Ki $entry @('-OfflineKit',$missingKit,'-Json')
Check-Ok ($r2.rc -eq 2 -and "$($r2.json.detail)" -match 'mcp-snippet' -and $r5.rc -eq 5 -and "$($r5.json.detail)" -match 'not delivered') 'BLOCK 2 vs DELIVERY 5' ("r2=$($r2.rc) r5=$($r5.rc)")

# 12. -Check writes no report/progress files
$checkArt = Join-Path $tmp 'check-art'
$null = Invoke-Ki $entry @('-Check','doctor','-Json','-ArtifactDir',$checkArt)
$checkFiles = @(Get-ChildItem -LiteralPath $checkArt -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -match 'install-report|progress\.ndjson' })
Check-Ok ($checkFiles.Count -eq 0) 'check mode writes no report artifacts' ("files=$($checkFiles.Count)")

# 12a. -Check server_check — валидная область (код 0/1/2, но не BROKEN 4)
$rSc = Invoke-Ki $entry @('-Check','server_check','-Json')
Check-Ok (@(0,1,2) -contains $rSc.rc) 'server_check is a known check area' ("rc=" + $rSc.rc)

# 13. -Resume -Steps deps reinstalls from lock and sets marker after rc=0
$depsText = [IO.File]::ReadAllText((Join-Path $root 'installer\lib\steps\deps.ps1'))
$resumeOk = $depsText.Contains('$state.ok -and -not $Ctx.Resume') -and $depsText.Contains('Remove-LockInstalledMarker') -and $depsText.Contains('Set-LockInstalledMarker')
Check-Ok $resumeOk 'resume deps always reinstalls from lock' ("source_contract=$resumeOk")

# 14-15. standalone-доставка: подменяем curl.exe функцией в дочернем powershell,
# чтобы симулировать отказ без сети и без записи в репозиторий.
$stand = Join-Path $tmp 'standalone'
New-Item -ItemType Directory -Force -Path $stand | Out-Null
Copy-Item -LiteralPath (Join-Path $root 'bootstrap.ps1') -Destination $stand -Force
$runnerText = @'
param([string]$Bootstrap = '', [string]$FixtureFlags = '', [string]$FixtureReg = '',
      [string]$ProjectDir = '', [switch]$FailRegistry, [switch]$FailSource, [switch]$Human)
$ErrorActionPreference = 'Continue'
function curl.exe {
  $a = @($args)
  $url = $a[$a.Count - 1]
  $out = ''
  for ($i = 0; $i -lt $a.Count; $i++) {
    if ($a[$i] -eq '-o' -and $i + 1 -lt $a.Count) { $out = $a[$i + 1] }
  }
  if ($FailRegistry -and $url -like '*docs/flags.json') {
    Write-Output 'curl: (22) simulated failure for docs/flags.json'
    $global:LASTEXITCODE = 22; return
  }
  if ($FailSource -and $url -like '*stanza-german-ppl-source.zip') {
    Write-Output 'curl: (35) simulated failure for source.zip'
    $global:LASTEXITCODE = 35; return
  }
  $src = if ($url -like '*flags.ps1') { $FixtureFlags } elseif ($url -like '*flags.json') { $FixtureReg } else { '' }
  if ($src -and $out) { Copy-Item -LiteralPath $src -Destination $out -Force }
  $global:LASTEXITCODE = 0
}
if ($Human) { & $Bootstrap -ProjectDir $ProjectDir } else { & $Bootstrap -Json -ProjectDir $ProjectDir }
exit $LASTEXITCODE
'@
$runner = Join-Path $stand 'curl-runner.ps1'
[IO.File]::WriteAllText($runner, $runnerText, (New-Object System.Text.UTF8Encoding($false)))
$runnerArgs = @(
  '-Bootstrap', (Join-Path $stand 'bootstrap.ps1'),
  '-FixtureFlags', (Join-Path $root 'installer\lib\flags.ps1'),
  '-FixtureReg', (Join-Path $root 'docs\flags.json'),
  '-ProjectDir', (Join-Path $stand 'project')
)

$r14 = Invoke-Ki $runner ($runnerArgs + @('-FailRegistry'))
$d14 = if ($r14.json -and $r14.json.failures) { "$($r14.json.failures[0].detail)" } else { '' }
$retry14 = if ($r14.json -and $r14.json.failures) { $r14.json.failures[0].retryable } else { $null }
Check-Ok ($r14.rc -eq 5 -and $r14.json.code -eq 5 -and $d14 -match 'docs.flags\.json' -and
          $d14 -match 'simulated failure' -and $retry14 -eq $true) `
  'flags.json delivery failure => 5/DELIVERY with file name' ("rc=$($r14.rc) detail=$d14 retryable=$retry14")

$r15 = Invoke-Ki $runner ($runnerArgs + @('-FailSource', '-Human'))
$out15 = ($r15.lines -join "`n")
Check-Ok ($r15.rc -eq 5 -and
          $out15 -match '\[bootstrap 3/11\] project directory:' -and
          $out15 -match '\[bootstrap 4/11\] download stanza-german-ppl-source\.zip' -and
          $out15 -match 'simulated failure for source\.zip') `
  'human progress shows step n/11, target dir and curl reason' ("rc=$($r15.rc) out=" + ($out15 -replace "`n", ' | '))

Write-Host "`nитого: $total проверок, ошибок $($failures.Count)" $(if ($failures.Count) { 'Red' } else { 'Green' })
if ($failures.Count) { exit 1 }
exit 0
