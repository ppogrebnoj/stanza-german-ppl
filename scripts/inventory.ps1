#Compatibility shim: library moved to installer/lib/inventory.ps1
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)][object[]]$ArgList
)
$moved = Join-Path $PSScriptRoot '..\installer\lib\inventory.ps1'
$dot = ($MyInvocation.InvocationName -eq '.')
$libOnly = [bool]$global:KI_LIB_ONLY
if ($libOnly -or $dot) {
    $global:KI_LIB_ONLY = $true
    . $moved
    $global:KI_LIB_ONLY = $libOnly
} else {
    & $moved @ArgList
    exit $LASTEXITCODE
}
