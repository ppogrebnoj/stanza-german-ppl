#Requires -Version 5.1
<#
    Compatibility forwarder. The former monolith is replaced by installer/install.ps1.
    This file exists only for old CI/tests and contains no step logic.
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)][object[]]$Rest
)
$ErrorActionPreference = 'Continue'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
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
$b = $parsed.bound
if ($b.Count -gt 0) { & $target @b } else { & $target }
exit $LASTEXITCODE
