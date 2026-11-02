#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Bundle, [Parameter(Mandatory)][string]$Out, [switch]$OnTarget)
$ErrorActionPreference = 'Stop'
if (-not $OnTarget) { throw 'Use -OnTarget on the isolated Hyper-V host.' }
$bundlePath = (Resolve-Path -LiteralPath $Bundle).Path
$spec = Get-Content -LiteralPath (Join-Path $bundlePath 'lab.json') -Raw | ConvertFrom-Json
if (-not @($spec.windows).Count) { throw 'This preset has no Windows guests.' }
$destination = [IO.Path]::GetFullPath($Out)
if (Test-Path -LiteralPath $destination) { throw 'Choose a new private export directory.' }
Import-Module Hyper-V
& (Join-Path $PSScriptRoot 'Stop-Lab.ps1') -Bundle $bundlePath -OnTarget
$names = @($spec.windows | ForEach-Object { $spec.name + '-' + $_.name })
foreach ($name in $names) {
    $vm = Get-VM -Name $name
    if ($vm.State -ne 'Off' -or $vm.Notes -ne ('SABER managed: ' + $bundlePath)) { throw 'Every managed VM must be powered off.' }
}
New-Item -ItemType Directory -Path $destination | Out-Null
$acl = Get-Acl -LiteralPath $destination
$acl.SetAccessRuleProtection($true, $false)
foreach ($sid in @([Security.Principal.WindowsIdentity]::GetCurrent().User, [Security.Principal.SecurityIdentifier]::new('S-1-5-18'))) {
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($sid, 'FullControl', 'ContainerInherit,ObjectInherit', 'None', 'Allow'))
}
Set-Acl -LiteralPath $destination -AclObject $acl
$configs = @{}
foreach ($name in $names) {
    Export-VM -Name $name -Path $destination
    $vmConfig = @(Get-ChildItem -LiteralPath (Join-Path $destination ($name + '\Virtual Machines')) -Filter '*.vmcx' -File)
    if ($vmConfig.Count -ne 1) { throw 'Expected exactly one exported VM configuration.' }
    $configs[$name] = $vmConfig[0].FullName.Substring($destination.Length + 1).Replace('\','/')
}
$files = @{}
foreach ($file in Get-ChildItem -LiteralPath $destination -Recurse -File) {
    if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Export contains a reparse point.' }
    $files[$file.FullName.Substring($destination.Length + 1).Replace('\','/')] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
}
@{ schema_version=1; lab_sha256=(Get-FileHash -LiteralPath (Join-Path $bundlePath 'lab.json') -Algorithm SHA256).Hash.ToLowerInvariant(); all_off=$true; vms=$names; configs=$configs; files=$files; created_at=[DateTime]::UtcNow.ToString('o') } |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $destination 'windows-manifest.json') -Encoding UTF8
Write-Output 'All managed guests exported with hashes and left off. Keep them off, stop the relay, then create the coordinated Docker backup.'
