# Contract fixture only: shadows OS readers; never reads the host registry/event log.
param([Parameter(Mandatory)][string]$CollectorScript)
$ErrorActionPreference = 'Stop'
function Get-ItemProperty { param($Path) return @{ MachineGuid='fixture-machine-guid' } }
function Get-CimInstance { param($ClassName) return @{ Domain='saber.test'; PartOfDomain=$true; DomainRole=5 } }
function Get-WinEvent {
    param($LogName,$FilterXPath,$MaxEvents,[switch]$Oldest,$ErrorAction)
    $eventId = if ($LogName -eq 'Security') { 4625 } else { 1 }
    $record = [pscustomobject]@{ Id=$eventId; RecordId=42; TimeCreated=[DateTime]::Parse('2026-01-01T00:00:00Z').ToUniversalTime() }
    $record | Add-Member -MemberType ScriptMethod -Name ToXml -Value {
        return '<Event><EventData><Data Name="TargetUserName">saber-red</Data><Data Name="Password">fixture-sensitive</Data><Data Name="CommandLine">cmd /c whoami</Data></EventData></Event>'
    }
    return $record
}
& $CollectorScript -Bookmarks @{} -NodeName soc-dc -Limit 40
