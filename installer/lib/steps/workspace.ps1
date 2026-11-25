#Requires -Version 5.1
function Invoke-Step_workspace {
    param([object]$Ctx)
    $need = @('install.ps1','bootstrap.ps1','installer\install.ps1','installer\requirements.lock','MCP-stanza-german\server.py')
    $missing = @($need | Where-Object { -not (Test-Path -LiteralPath (Join-Path $Ctx.Root $_)) })
    if ($missing.Count -gt 0) {
        return New-StepResult -Id 'workspace' -Status BLOCK -Rc 2 -Detail "missing project files: $($missing -join ', ')" -NextCmd 'clone or unpack the project first'
    }
    # ASCII-only source: 'rule' directory is still Cyrillic until the rename wave.
    $ruleDir = [string]::Concat([char]0x043F,[char]0x0440,[char]0x0430,[char]0x0432,[char]0x0438,[char]0x043B,[char]0x043E)
    $hookSrc = Join-Path $Ctx.Root ($ruleDir + '\git-hooks\pre-commit')
    $gitDir = Join-Path $Ctx.Root '.git'
    if (-not (Test-Path -LiteralPath $gitDir)) {
        if (-not $Ctx.Force) {
            return New-StepResult -Id 'workspace' -Status BLOCK -Rc 2 -Detail 'ZIP copy has no .git; -Force required for git init' -NextCmd 'bootstrap.ps1 -Steps workspace -Force'
        }
        & git init
        & git remote add origin https://github.com/ppogrebnoj/stanza-german-ppl.git
        & git fetch origin
        & git reset --mixed origin/master
        if ($LASTEXITCODE -ne 0) {
            return New-StepResult -Id 'workspace' -Status FAIL -Rc 1 -Detail 'git bootstrap for ZIP copy failed'
        }
    }
    if (Test-Path -LiteralPath $hookSrc) {
        try {
            $hookDst = Join-Path $gitDir 'hooks\pre-commit'
            if (-not (Test-Path -LiteralPath (Split-Path -Parent $hookDst))) { New-Item -ItemType Directory -Force -Path (Split-Path -Parent $hookDst) | Out-Null }
            $text = [IO.File]::ReadAllText($hookSrc) -replace "`r`n", "`n"
            [IO.File]::WriteAllText($hookDst, $text, (New-Object System.Text.UTF8Encoding($false)))
        } catch { }
    }
    return New-StepResult -Id 'workspace' -Status OK -Detail 'project files and git hook ready'
}
