#Requires -Version 5.1
function Invoke-Step_workspace {
    param([object]$Ctx)

    $need = @('install.ps1','bootstrap.ps1','installer\install.ps1','installer\requirements.lock','MCP-stanza-german\server.py')
    $missing = @($need | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Ctx.Root $_)) })
    if ($missing.Count -gt 0) {
        return New-StepResult -Id 'workspace' -Status BLOCK -Rc 2 -Detail "missing project files: $($missing -join ', ')" -NextCmd 'clone or unpack the project first'
    }
    # git мог быть поставлен предыдущим шагом: подхватываем PATH и известные каталоги.
    Refresh-ProcessPath
    $gitPath = Ensure-GitOnPath
    if (-not $gitPath) {
        return New-StepResult -Id 'workspace' -Status BLOCK -Rc 2 -Detail 'git missing' -NextCmd 'bootstrap.ps1 -Yes -Steps git'
    }

    # ASCII-only source: the on-disk directory is `rule` (not its legacy Cyrillic spelling).
    $hookSrc = Join-Path $Ctx.Root 'rule\git-hooks\pre-commit'
    if (-not (Test-Path -LiteralPath $hookSrc)) {
        return New-StepResult -Id 'workspace' -Status BLOCK -Rc 2 -Detail "hook source missing: $hookSrc" -NextCmd 'restore rule/git-hooks/pre-commit from the release archive'
    }

    $gitDir = Join-Path $Ctx.Root '.git'
    $warnings = @()
    if (-not (Test-Path -LiteralPath $gitDir)) {
        # ZIP-копия приходит без истории. git init + origin — безопасные операции,
        # поэтому -Force для них НЕ нужен; -Force включает только fetch/reset.
        $null = & git -C $Ctx.Root init 2>&1
        if ($LASTEXITCODE -ne 0) {
            return New-StepResult -Id 'workspace' -Status FAIL -Rc 1 -Detail 'git init failed' -Warnings $warnings
        }
    }
    $origin = @(& git -C $Ctx.Root remote get-url origin 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $origin -or -not "$($origin[0])".Trim()) {
        $null = & git -C $Ctx.Root remote add origin https://github.com/ppogrebnoj/stanza-german-ppl.git 2>&1
        if ($LASTEXITCODE -ne 0) {
            return New-StepResult -Id 'workspace' -Status FAIL -Rc 1 -Detail 'git remote add failed' -Warnings $warnings
        }
    }

    if ($Ctx.Force) {
        # Историю подтягиваем только по явному -Force и с жёстким таймаутом:
        # рабочее дерево уже полное, сетевой fetch не должен блокировать установку.
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = 'git'
        $psi.Arguments = '-C "' + $Ctx.Root + '" fetch origin --quiet'
        $psi.WorkingDirectory = $Ctx.Root
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $proc = New-Object System.Diagnostics.Process
        $proc.StartInfo = $psi
        $fetched = $false
        try {
            $null = $proc.Start()
            $so = $proc.StandardOutput.ReadToEnd()
            $se = $proc.StandardError.ReadToEnd()
            if (-not $proc.WaitForExit(90000)) {
                try { $proc.Kill() } catch { }
                $warnings += 'git fetch timeout after 90s (working tree is complete; history skipped)'
            } elseif ($proc.ExitCode -eq 0) {
                $fetched = $true
            } else {
                $tail = (@($se -split "`n") | Select-Object -Last 3) -join ' | '
                $warnings += "git fetch rc=$($proc.ExitCode): $tail"
            }
        } catch {
            $warnings += "git fetch error: $_"
        } finally { try { $proc.Dispose() } catch { } }
        if ($fetched) {
            $null = & git -C $Ctx.Root reset --mixed origin/master 2>&1
            if ($LASTEXITCODE -ne 0) { $warnings += 'git reset --mixed origin/master failed' }
        }
    }

    try {
        $hookDst = Join-Path $gitDir 'hooks\pre-commit'
        if (-not (Test-Path -LiteralPath (Split-Path -Parent $hookDst))) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $hookDst) | Out-Null
        }
        # doctor требует LF: CRLF даёт WARN git_hook.
        $text = [IO.File]::ReadAllText($hookSrc) -replace "`r`n", "`n"
        [IO.File]::WriteAllText($hookDst, $text, (New-Object System.Text.UTF8Encoding($false)))
    } catch {
        return New-StepResult -Id 'workspace' -Status FAIL -Rc 1 -Detail "pre-commit hook install failed: $_" -Warnings $warnings
    }
    $note = if ($Ctx.Force) { 'project files, origin and git hook ready (forced history sync)' } else { 'project files, origin and git hook ready (ZIP copy; history sync needs -Force)' }
    return New-StepResult -Id 'workspace' -Status OK -Detail $note -Warnings $warnings
}
