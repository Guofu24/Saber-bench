#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Bundle, [Parameter(Mandatory)][string]$Backup, [Parameter(Mandatory)][string]$VmRoot, [switch]$OnTarget)
$ErrorActionPreference = 'Stop'
if (-not $OnTarget) { throw 'Use -OnTarget on the isolated Hyper-V host.' }
$bundlePath = (Resolve-Path -LiteralPath $Bundle).Path
$source = (Resolve-Path -LiteralPath $Backup).Path
$destination = [IO.Path]::GetFullPath($VmRoot)
if (Test-Path -LiteralPath $destination) { throw 'Restore requires a new VM directory.' }
$spec = Get-Content -LiteralPath (Join-Path $bundlePath 'lab.json') -Raw | ConvertFrom-Json
$manifest = Get-Content -LiteralPath (Join-Path $source 'windows-manifest.json') -Raw | ConvertFrom-Json
$labHash = (Get-FileHash -LiteralPath (Join-Path $bundlePath 'lab.json') -Algorithm SHA256).Hash.ToLowerInvariant()
if ($manifest.schema_version -ne 1 -or $manifest.lab_sha256 -ne $labHash -or -not $manifest.all_off) { throw 'Invalid or mismatched guest backup.' }
$names = @($spec.windows | ForEach-Object { $spec.name + '-' + $_.name })
if (-not $names.Count -or @(Compare-Object $names @($manifest.vms)).Count) { throw 'Guest backup roster mismatch.' }
Import-Module Hyper-V
foreach ($name in $names) { if (Get-VM -Name $name -ErrorAction SilentlyContinue) { throw 'Restore never overwrites existing VMs.' } }
$sourcePrefix = $source.TrimEnd('\') + '\'
foreach ($entry in $manifest.files.PSObject.Properties) {
    $path = [IO.Path]::GetFullPath((Join-Path $source $entry.Name))
    if (-not $path.StartsWith($sourcePrefix, [StringComparison]::OrdinalIgnoreCase) -or (Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Export path outside backup or reparse point.' }
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.Value) { throw 'Export integrity mismatch.' }
}
$switchName = 'SABER-' + $spec.name
$switch = Get-VMSwitch -Name $switchName -ErrorAction SilentlyContinue
if ($switch -and $switch.SwitchType -ne 'Private') { throw 'Existing lab switch is not private.' }
if (-not $switch) { New-VMSwitch -Name $switchName -SwitchType Private | Out-Null }
New-Item -ItemType Directory -Path $destination | Out-Null
$restored = @()
foreach ($name in $names) {
    $relativeConfig = $manifest.configs.$name
    if (-not $relativeConfig -or -not $manifest.files.PSObject.Properties[$relativeConfig]) { throw 'Unverified VM configuration.' }
    $config = Join-Path $source $relativeConfig
    $vmPath = Join-Path $destination $name
    $diskPath = Join-Path $vmPath 'Disks'
    $snapshotPath = Join-Path $vmPath 'Snapshots'
    New-Item -ItemType Directory -Path $diskPath, $snapshotPath -Force | Out-Null
    $compatibility = Compare-VM -Path $config -Copy -GenerateNewId -VirtualMachinePath $vmPath -VhdDestinationPath $diskPath -SnapshotFilePath $snapshotPath
    foreach ($issue in @($compatibility.Incompatibilities | Where-Object MessageId -eq 33012)) {
        Connect-VMNetworkAdapter -VMNetworkAdapter $issue.Source -SwitchName $switchName
    }
    $compatibility = Compare-VM -CompatibilityReport $compatibility
    if (@($compatibility.Incompatibilities).Count) { throw 'Target Hyper-V incompatibility remains; inspect the compatibility report before importing.' }
    $vm = Import-VM -CompatibilityReport $compatibility
    if ($vm.Name -ne $name -or $vm.State -ne 'Off') { throw 'Unexpected restored VM identity/state; inspect partial restore.' }
    Set-VM -VM $vm -Notes ('SABER managed: ' + $bundlePath) -AutomaticStartAction Nothing -AutomaticCheckpointsEnabled $false
    Get-VMNetworkAdapter -VM $vm | Connect-VMNetworkAdapter -SwitchName $switchName
    $restored += @{ name=$name; id=$vm.Id.ToString() }
}
@{ restored=$restored; runtime_verified=$false; services='left off' } | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $destination 'restore.receipt.json') -Encoding UTF8
Write-Output 'Guests restored and left off. Restore matching Docker volumes before starting the coordinated lab; run live acceptance afterward.'
