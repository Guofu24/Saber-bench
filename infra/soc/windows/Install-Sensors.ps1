#Requires -RunAsAdministrator
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Bundle, [Parameter(Mandatory)][string]$SysmonExe, [Parameter(Mandatory)][pscredential]$DomainCredential, [switch]$OnTarget)
$ErrorActionPreference = 'Stop'
if (-not $OnTarget) { throw 'Run only on the isolated lab host with -OnTarget.' }
$bundlePath = (Resolve-Path -LiteralPath $Bundle).Path
$spec = Get-Content -LiteralPath (Join-Path $bundlePath 'lab.json') -Raw | ConvertFrom-Json
$signature = Get-AuthenticodeSignature -LiteralPath $SysmonExe
if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'Microsoft Corporation') { throw 'A valid Microsoft-signed Sysmon binary is required.' }
$fileServer = @($spec.windows | Where-Object role -eq 'member-server')[0].name
$firstWorkstation = @($spec.windows | Where-Object role -eq 'workstation')[0].name
foreach ($node in $spec.windows) {
    $name = $spec.name + '-' + $node.name
    if ((Get-VM -Name $name).Notes -ne ('SABER managed: ' + $bundlePath)) { throw 'VM is not owned by this bundle.' }
    $session = New-PSSession -VMName $name -Credential $DomainCredential
    try {
        Invoke-Command -Session $session -ScriptBlock {
            New-Item -ItemType Directory -Path 'C:\SaberLab' -Force | Out-Null
            icacls.exe 'C:\SaberLab' /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
        }
        Copy-Item -LiteralPath $SysmonExe -Destination 'C:\SaberLab\Sysmon64.exe' -ToSession $session
        foreach ($asset in @('sysmon.xml','Guest-Workload.ps1','Respond-Domain.ps1')) {
            Copy-Item -LiteralPath (Join-Path $bundlePath ('windows\' + $asset)) -Destination ('C:\SaberLab\' + $asset) -ToSession $session
        }
        Invoke-Command -Session $session -ArgumentList $node.role,$spec.domain,$fileServer,($node.name -eq $firstWorkstation) -ScriptBlock {
            param($Role,$Domain,$FileServer,$RedWorkstation)
            if (Get-Service Sysmon64 -ErrorAction SilentlyContinue) { & 'C:\SaberLab\Sysmon64.exe' -c 'C:\SaberLab\sysmon.xml' | Out-Null }
            else { & 'C:\SaberLab\Sysmon64.exe' -accepteula -i 'C:\SaberLab\sysmon.xml' | Out-Null }
            if ($LASTEXITCODE -ne 0) { throw 'Sysmon installation/configuration failed.' }
            foreach ($sub in @('{0CCE9215-69AE-11D9-BED3-505054503030}','{0CCE922B-69AE-11D9-BED3-505054503030}')) { auditpol.exe /set /subcategory:$sub /success:enable /failure:enable | Out-Null }
            wevtutil.exe sl Microsoft-Windows-Sysmon/Operational /ms:268435456
            wevtutil.exe sl Security /ms:268435456
            if ($Role -eq 'member-server') {
                New-Item -ItemType Directory -Path 'C:\SaberWork' -Force | Out-Null
                $netbios = $Domain.Split('.')[0].ToUpper()
                icacls.exe 'C:\SaberWork' /grant ($netbios + '\Domain Computers:(OI)(CI)M') | Out-Null
                if (-not (Get-SmbShare -Name SaberWork -ErrorAction SilentlyContinue)) { New-SmbShare -Name SaberWork -Path 'C:\SaberWork' -ChangeAccess ($netbios + '\Domain Computers') | Out-Null }
                if (-not (Get-NetFirewallRule -Name Saber-SMB -ErrorAction SilentlyContinue)) { New-NetFirewallRule -Name Saber-SMB -DisplayName 'SABER isolated SMB' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 445 -RemoteAddress '172.28.80.0/24' | Out-Null }
            }
            if ($Role -eq 'workstation') {
                $workRole = if ($RedWorkstation) { 'red' } else { 'client' }
                $args = '-NoProfile -NonInteractive -File C:\SaberLab\Guest-Workload.ps1 -Domain ' + $Domain + ' -FileServer ' + $FileServer + ' -Role ' + $workRole
                $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $args
                $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
                $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
                Register-ScheduledTask -TaskName SABER-Workload -Action $action -Trigger $trigger -Settings $settings -User SYSTEM -RunLevel Highest -Force | Out-Null
            }
        }
    } finally { Remove-PSSession $session }
}
Write-Output 'Sensors and bounded guest workloads installed. Start Relay-Lab.ps1 to deliver evidence and execute queued domain responses.'
