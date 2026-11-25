#Requires -Version 5.1
<#
    install.ps1 - compatibility forwarder. Architecture entry is bootstrap.ps1;
    the real orchestrator is installer/install.ps1. No installation logic here.
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)][object[]]$Rest
)
$ErrorActionPreference = 'Continue'
$root = (Resolve-Path $PSScriptRoot).Path
. (Join-Path $root 'installer\lib\flags.ps1')
$reg = Read-FlagsRegistry -Path (Join-Path $root 'docs\flags.json')
$parsed = Convert-InstallerArgs -Rest $Rest -Registry $reg
$wantsJson = $parsed.bound.ContainsKey('Json')
if ($wantsJson) { try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { } }
if ($parsed.errors.Count) {
    $msg = ($parsed.errors -join '; ')
    if ($wantsJson) {
        [Console]::Out.WriteLine(([pscustomobject][ordered]@{
            code = 4; ok = $false
            failures = @([pscustomobject]@{ id = 'params'; detail = $msg; retryable = $false })
        } | ConvertTo-Json -Depth 5))
    } else { Write-Host "BROKEN: $msg (code 4)" -ForegroundColor Red }
    exit 4
}
$target = Join-Path $root 'installer\install.ps1'
if (-not (Test-Path -LiteralPath $target)) {
    if ($wantsJson) {
        [Console]::Out.WriteLine('{"code":4,"ok":false,"failures":[{"id":"entry","detail":"no installer/install.ps1","retryable":false}]}')
    } else { Write-Host 'BROKEN: no installer/install.ps1' -ForegroundColor Red }
    exit 4
}
$b = $parsed.bound
if ($b.Count -gt 0) { & $target @b } else { & $target }
exit $LASTEXITCODE
