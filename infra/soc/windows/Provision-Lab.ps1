#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Bundle,
    [Parameter(Mandatory)][string]$VmRoot,
    [Parameter(Mandatory)][string]$ServerVhdx,
    [Parameter(Mandatory)][string]$WorkstationVhdx,
    [Parameter(Mandatory)][pscredential]$BaseCredential,
    [Parameter(Mandatory)][securestring]$DsrmPassword,
    [switch]$OnTarget
)
$ErrorActionPreference = 'Stop'
if (-not $OnTarget) { throw 'Use -OnTarget only on the isolated Hyper-V lab host.' }
Import-Module Hyper-V
$bundlePath = (Resolve-Path -LiteralPath $Bundle).Path
$spec = Get-Content -LiteralPath (Join-Path $bundlePath 'lab.json') -Raw | ConvertFrom-Json
if ($spec.preset -notin @('windows-ad','expanded') -or $spec.domain -notmatch '^[a-z][a-z0-9-]{0,30}\.test$') { throw 'Invalid Windows lab configuration.' }
$root = [IO.Path]::GetFullPath($VmRoot)
if ($root -eq [IO.Path]::GetPathRoot($root)) { throw 'Use a dedicated VM directory, not a drive root.' }
New-Item -ItemType Directory -Path $root -Force | Out-Null
$serverBase = (Resolve-Path -LiteralPath $ServerVhdx).Path
$clientBase = (Resolve-Path -LiteralPath $WorkstationVhdx).Path
$switchName = 'SABER-' + $spec.name
$switch = Get-VMSwitch -Name $switchName -ErrorAction SilentlyContinue
if ($switch -and $switch.SwitchType -ne 'Private') { throw 'Existing switch is not private; refusing to attach.' }
if (-not $switch) { New-VMSwitch -Name $switchName -SwitchType Private | Out-Null }
$domainCredential = [pscredential]::new(($spec.domain + '\Administrator'), $BaseCredential.Password)
$dc = @($spec.windows | Where-Object role -eq 'dc')[0]
$dcVM = $spec.name + '-' + $dc.name
function Open-Guest([string]$Name, [pscredential]$Credential, [pscredential]$Alternate = $null) {
    for ($i = 0; $i -lt 120; $i++) {
        try { return New-PSSession -VMName $Name -Credential $Credential -ErrorAction Stop }
        catch {
            if ($Alternate) { try { return New-PSSession -VMName $Name -Credential $Alternate -ErrorAction Stop } catch { } }
            Start-Sleep -Seconds 5
        }
    }
    throw "PowerShell Direct unavailable: $Name. Check unattended first boot and credentials."
}
function Restart-Guest([string]$Name, [System.Management.Automation.Runspaces.PSSession]$Session) {
    # Let the VM initiate its reboot; the host never force-powers off a running guest.
    Invoke-Command -Session $Session -ScriptBlock { shutdown.exe /r /t 3 | Out-Null }
    Remove-PSSession $Session
    Start-Sleep -Seconds 10
}
foreach ($node in $spec.windows) {
    if ($node.name -notmatch '^[a-z][a-z0-9-]{0,14}$' -or $node.address -notmatch '^172\.28\.80\.[0-9]+$') { throw 'Unsupported guest addressing; use the supplied isolated subnet.' }
    $name = $spec.name + '-' + $node.name
    $disk = Join-Path $root ($name + '.vhdx')
    $vm = Get-VM -Name $name -ErrorAction SilentlyContinue
    if ($vm) {
        if ($vm.Notes -ne ('SABER managed: ' + $bundlePath)) { throw "VM name belongs to another deployment: $name" }
    } else {
        if (Test-Path -LiteralPath $disk) { throw "Unmanaged disk already exists: $disk" }
        $base = if ($node.role -eq 'workstation') { $clientBase } else { $serverBase }
        New-VHD -Path $disk -ParentPath $base -Differencing | Out-Null
        New-VM -Name $name -Generation 2 -MemoryStartupBytes ([long]$node.memory_gb * 1GB) -VHDPath $disk -SwitchName $switchName -Path $root | Out-Null
        Set-VM -Name $name -ProcessorCount $node.cpus -AutomaticCheckpointsEnabled $false -Notes ('SABER managed: ' + $bundlePath)
        Set-VMFirmware -VMName $name -EnableSecureBoot On
    }
    if ((Get-VM -Name $name).State -ne 'Running') { Start-VM -Name $name | Out-Null }
    # On rerun a promoted DC requires the domain credential.
    $credential = if ($node.role -eq 'dc' -and (Test-Path -LiteralPath (Join-Path $root 'domain.receipt.json'))) { $domainCredential } else { $BaseCredential }
    $alternate = if ($node.role -eq 'dc') { $domainCredential } else { $null }
    $session = Open-Guest $name $credential $alternate
    $rename = Invoke-Command -Session $session -ArgumentList $node.name,$node.address,$dc.address -ScriptBlock {
        param($Name,$Address,$Dns)
        $nic = Get-NetAdapter | Where-Object Status -eq Up | Select-Object -First 1
        Set-NetIPInterface -InterfaceIndex $nic.ifIndex -AddressFamily IPv4 -Dhcp Disabled
        $existing = Get-NetIPAddress -InterfaceIndex $nic.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue
        foreach ($ip in $existing) { if ($ip.IPAddress -ne $Address) { Remove-NetIPAddress -InputObject $ip -Confirm:$false } }
        if (-not ($existing | Where-Object IPAddress -eq $Address)) { New-NetIPAddress -InterfaceIndex $nic.ifIndex -IPAddress $Address -PrefixLength 24 | Out-Null }
        Set-DnsClientServerAddress -InterfaceIndex $nic.ifIndex -ServerAddresses $Dns
        if ($env:COMPUTERNAME -ine $Name) { Rename-Computer -NewName $Name -Force; return $true }
        return $false
    }
    if ($rename) { Restart-Guest $name $session } else { Remove-PSSession $session }
}
$session = Open-Guest $dcVM $BaseCredential $domainCredential
$promoted = Invoke-Command -Session $session -ArgumentList $spec.domain,$DsrmPassword -ScriptBlock {
    param($Domain,$Dsrm)
    if ((Get-CimInstance Win32_ComputerSystem).DomainRole -ge 4) { return $false }
    Install-WindowsFeature AD-Domain-Services -IncludeManagementTools | Out-Null
    Install-ADDSForest -DomainName $Domain -SafeModeAdministratorPassword $Dsrm -InstallDns -NoRebootOnCompletion -Force | Out-Null
    return $true
}
if ($promoted) { Restart-Guest $dcVM $session } else { Remove-PSSession $session }
$session = Open-Guest $dcVM $domainCredential
Invoke-Command -Session $session -ScriptBlock {
    Import-Module ActiveDirectory
    for ($i=0; $i -lt 60; $i++) { try { Get-ADDomain -ErrorAction Stop | Out-Null; break } catch { Start-Sleep 5 } }
    $domain = Get-ADDomain
    $ou = 'OU=SABER,' + $domain.DistinguishedName
    if (-not (Get-ADOrganizationalUnit -Filter "Name -eq 'SABER'")) { New-ADOrganizationalUnit -Name SABER -Path $domain.DistinguishedName }
    if (-not (Get-ADGroup -Filter "SamAccountName -eq 'SaberStaff'")) { New-ADGroup -Name SaberStaff -GroupScope Global -Path $ou }
    foreach ($name in @('saber-client','saber-red')) {
        if (-not (Get-ADUser -Filter "SamAccountName -eq '$name'")) {
            $bytes = New-Object byte[] 32
            [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
            $password = ConvertTo-SecureString ('Aa1!' + [Convert]::ToBase64String($bytes)) -AsPlainText -Force
            New-ADUser -Name $name -SamAccountName $name -Path $ou -AccountPassword $password -Enabled $true
        }
        Add-ADGroupMember -Identity SaberStaff -Members $name
    }
    # Domain logon failure events; GUIDs avoid localized audit-policy names.
    auditpol.exe /set /subcategory:'{0CCE9215-69AE-11D9-BED3-505054503030}' /success:enable /failure:enable | Out-Null
}
Remove-PSSession $session
@{ domain=$spec.domain; dc=$dc.name; provisioned_at=[DateTime]::UtcNow.ToString('o'); runtime_verified=$false } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $root 'domain.receipt.json') -Encoding UTF8
foreach ($node in $spec.windows | Where-Object role -ne 'dc') {
    $name = $spec.name + '-' + $node.name
    $session = Open-Guest $name $BaseCredential
    $joined = Invoke-Command -Session $session -ArgumentList $spec.domain,$domainCredential -ScriptBlock {
        param($Domain,$Credential)
        $system = Get-CimInstance Win32_ComputerSystem
        if ($system.PartOfDomain) { if ($system.Domain -ine $Domain) { throw 'Guest already belongs to another domain.' }; return $false }
        Add-Computer -DomainName $Domain -Credential $Credential -Force
        return $true
    }
    if ($joined) { Restart-Guest $name $session } else { Remove-PSSession $session }
}
Write-Output 'VMs and AD domain provisioned. Next: Install-Sensors.ps1, then Relay-Lab.ps1 and saber lab verify. No runtime verification claimed.'
