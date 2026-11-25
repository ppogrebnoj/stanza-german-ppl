#Requires -Version 5.1
<#
    flags.ps1 - the only argument parser for entry/forwarder.
    No installation logic: registry docs/flags.json and key validation only.
#>

function Read-FlagsRegistry {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { throw "no flags registry: $Path" }
    $reg = Get-Content -LiteralPath $Path -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $reg.flags) { throw "registry $Path has no flags[]" }
    return $reg
}

function Convert-InstallerArgs {
    param(
        [object[]]$Rest = @(),
        [Parameter(Mandatory = $true)]$Registry
    )
    $byName = @{}
    foreach ($f in @($Registry.flags)) { $byName["$($f.name)"] = $f }

    $bound = @{}
    $errors = @()
    $i = 0
    while ($Rest -and $i -lt $Rest.Count) {
        $a = "$($Rest[$i])"
        if ($a -like '-*') {
            $name = $a.TrimStart('-')
            if (-not $byName.ContainsKey($name)) {
                $errors += "unknown parameter -$name"
                $i++
                continue
            }
            $kind = "$($byName[$name].kind)"
            if ($kind -eq 'switch') {
                $bound[$name] = $true
                $i++
            } else {
                if ($i + 1 -ge $Rest.Count -or "$($Rest[$i+1])" -like '-*') {
                    $errors += "parameter -$name requires a value"
                    $i++
                } else {
                    $val = $Rest[$i + 1]
                    if ($val -is [array]) { $val = ($val -join ',') }
                    $bound[$name] = "$val"
                    $i += 2
                }
            }
        } else { $i++ }
    }

    $check = "$($bound['Check'])"
    if ($check -and $Registry.checks -notcontains $check) {
        $errors += "unknown check area -Check '$check'"
    }

    return [pscustomobject]@{ bound = $bound; errors = @($errors); registry = $Registry }
}
