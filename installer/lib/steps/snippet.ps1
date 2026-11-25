#Requires -Version 5.1
function Invoke-Step_snippet {
    param([object]$Ctx)
    $py = Join-Path $Ctx.Root '.venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $py)) {
        return New-StepResult -Id 'snippet' -Status BLOCK -Rc 2 -Detail '.venv missing' -NextCmd 'bootstrap.ps1 -Steps venv,deps,snippet'
    }
    $resources = if ($Ctx.ModelsDir) { $Ctx.ModelsDir } else { Join-Path $Ctx.Root '.stanza\models' }
    $entry = [ordered]@{
        command = $py
        args = @((Join-Path $Ctx.Root 'MCP-stanza-german\server.py'))
        env = [ordered]@{ PYTHONUTF8 = '1'; STANZA_RESOURCES_DIR = $resources }
    }
    $body = [pscustomobject]@{ mcpServers = [pscustomobject]@{ 'stanza-german' = $entry } } | ConvertTo-Json -Depth 6
    $path = Save-McpSnippet -ArtifactDir $Ctx.ArtifactDir -Root $Ctx.Root -Json $body
    return New-StepResult -Id 'snippet' -Status OK -Detail "mcp snippet written: $path (human registers it in MCP client)"
}
