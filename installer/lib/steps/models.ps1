#Requires -Version 5.1
function Invoke-Step_models {
    param([object]$Ctx)
    $py = Join-Path $Ctx.Root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $py)) {
        return New-StepResult -Id 'models' -Status BLOCK -Rc 2 -Detail '.venv missing' -NextCmd 'bootstrap.ps1 -Steps venv,deps,models'
    }
    $resources = if ($Ctx.ModelsDir) { $Ctx.ModelsDir } else { Join-Path $Ctx.Root '.stanza\models' }
    $runner = Join-Path $Ctx.Root 'scripts\run_checks.py'

    # Базовый контракт — 5 процессоров (~315 МБ, 8 каталогов в de, без de/default.zip).
    # -Models добавляет процессоры (ner,sentiment) или all; без флага сеть не нужна,
    # если нужные процессоры уже на месте.
    $processors = New-Object System.Collections.Generic.List[string]
    foreach ($p in @('tokenize','mwt','pos','lemma','depparse')) { $processors.Add($p) }
    if ($Ctx.Models) {
        $extra = if ("$($Ctx.Models)".Trim().ToLowerInvariant() -eq 'all') {
            @('ner','sentiment')
        } else { @("$($Ctx.Models)" -split ',') }
        foreach ($p in $extra) {
            $p = "$($p)".Trim().ToLowerInvariant()
            if ($p -and -not $processors.Contains($p)) { $processors.Add($p) }
        }
    }
    $wanted = $processors.ToArray() -join ','

    $busy = @(Test-VenvBusy -Root $Ctx.Root)
    $warn = @()
    if ($busy.Count -gt 0) { $warn += "venv busy: $($busy -join ' | ')" }

    $old = $env:STANZA_RESOURCES_DIR
    $env:STANZA_RESOURCES_DIR = $resources
    try {
        if (Test-Path -LiteralPath $runner) {
            $null = & $py $runner --check models --json -- --processors $wanted --load 2>&1
            if ($LASTEXITCODE -eq 0) {
                return New-StepResult -Id 'models' -Status SKIP -Detail "models already present: $resources ($wanted)" -Warnings $warn
            }
        }

        # stanza 1.15 берёт resources.json с raw.githubusercontent.com через requests;
        # в VM этот хост иногда отдаёт TLS reset 10054. Качаем манифест curl'ом с
        # ретраями и запрещаем stanza сетевой запрос за ним (download_json=False).
        $manifest = Join-Path $resources 'resources.json'
        if (-not (Test-Path -LiteralPath $manifest)) {
            if (-not (Test-Path -LiteralPath $resources)) { New-Item -ItemType Directory -Force -Path $resources | Out-Null }
            $dl = Invoke-Download -Url 'https://raw.githubusercontent.com/stanfordnlp/stanza-resources/main/resources_1.15.0.json' `
                                  -Dest $manifest -Retries ([math]::Max(3, [int]$Ctx.Retries))
            if (-not $dl.ok) {
                return New-StepResult -Id 'models' -Status DELIVERY -Rc 5 -Retryable $true -Detail "resources.json download failed: $($dl.detail)" -NextCmd 'bootstrap.ps1 -Resume -Steps models' -Warnings $warn
            }
        }

        $code = "import stanza; stanza.download('de', processors='$wanted', verbose=False, download_json=False)"
        $out = @()
        $rc = -1
        for ($attempt = 1; $attempt -le 3; $attempt++) {
            $out = @(& $py -c $code 2>&1)
            $rc = $LASTEXITCODE
            if ($rc -eq 0) { break }
            if ($attempt -lt 3) { Start-Sleep -Seconds (3 * $attempt) }
        }
        if ($rc -ne 0) {
            $tail = (@($out | Select-Object -Last 8) -join ' | ')
            return New-StepResult -Id 'models' -Status FAIL -Rc 3 -Retryable $true -Detail "stanza.download rc=$rc ($wanted): $tail" -NextCmd 'bootstrap.ps1 -Resume -Steps models' -Warnings $warn
        }
        if (Test-Path -LiteralPath $runner) {
            $null = & $py $runner --check models --json -- --processors $wanted --load 2>&1
            if ($LASTEXITCODE -ne 0) {
                return New-StepResult -Id 'models' -Status FAIL -Rc 3 -Retryable $true -Detail 'model processor check failed' -NextCmd 'bootstrap.ps1 -Resume -Steps models' -Warnings $warn
            }
        }
        return New-StepResult -Id 'models' -Status OK -Detail "models ready: $resources ($wanted)" -Warnings $warn
    } finally {
        $env:STANZA_RESOURCES_DIR = $old
    }
}
