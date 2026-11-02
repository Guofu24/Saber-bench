#Requires -RunAsAdministrator
param([Parameter(Mandatory)][string]$Bundle, [switch]$RestoreBaseline, [switch]$OnTarget)
$ErrorActionPreference = 'Stop'
if (-not $OnTarget) { throw 'Use -OnTarget on the lab host.' }
$bundlePath = (Resolve-Path -LiteralPath $Bundle).Path
$spec = Get-Content -LiteralPath (Join-Path $bundlePath 'lab.json') -Raw | ConvertFrom-Json
$names = @($spec.windows | ForEach-Object { $spec.name + '-' + $_.name })
foreach ($name in $names) {
    if ((Get-VM -Name $name).Notes -ne ('SABER managed: ' + $bundlePath)) { throw 'VM ownership mismatch; nothing outside this bundle may be changed.' }
    if ($RestoreBaseline -and -not (Get-VMSnapshot -VMName $name -Name 'SABER-baseline' -ErrorAction SilentlyContinue)) { throw 'Every VM needs a baseline before restoring the domain.' }
}
foreach ($name in $names) {
    if ((Get-VM -Name $name).State -eq 'Running') { Stop-VM -Name $name -Confirm:$false }
}
if (@($names | Where-Object { (Get-VM -Name $_).State -ne 'Off' }).Count) { throw 'Wait for guest shutdown before restoring. No forced power-off performed.' }
if ($RestoreBaseline) {
    foreach ($name in $names) { Get-VMSnapshot -VMName $name -Name 'SABER-baseline' | Restore-VMSnapshot -Confirm:$false }
    Write-Output 'All managed guests restored together, left powered off. Old SOC evidence remains historical; start a new bundle/run for a fresh experiment.'
} else { Write-Output 'Managed guests stopped; disks and checkpoints preserved.' }
