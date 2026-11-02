# Executed through PowerShell Direct; returns normalized events, never logon credentials.
param([hashtable]$Bookmarks, [string]$NodeName, [int]$Limit = 40)
$ErrorActionPreference = 'Stop'
$result = @()
$guid = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Cryptography').MachineGuid
foreach ($channel in @('Microsoft-Windows-Sysmon/Operational','Security')) {
    $after = [long]$Bookmarks[$channel]
    $latest = Get-WinEvent -LogName $channel -MaxEvents 1 -ErrorAction SilentlyContinue
    if ($latest -and $latest.RecordId -lt $after) { $after = 0 }
    $records = @(Get-WinEvent -LogName $channel -FilterXPath "*[System[EventRecordID > $after]]" -Oldest -MaxEvents $Limit -ErrorAction SilentlyContinue)
    foreach ($record in $records) {
        [xml]$xml = $record.ToXml()
        $fields = @{}
        foreach ($field in $xml.Event.EventData.Data) {
            $key = [string]$field.Name
            if (-not $key) { continue }
            $value = [string]$field.'#text'
            if ($key -match '(?i)password|token|secret|keymaterial') { $value = '[REDACTED]' }
            $value = $value -replace 'AIza[\w-]{25,}', '[REDACTED]' -replace '(?i)((?:password|token|api[_-]?key|secret)[\s=:]+)\S+', '$1[REDACTED]'
            $fields[$key] = $value.Substring(0,[Math]::Min(512,$value.Length))
        }
        $ts = $record.TimeCreated.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fff+00:00')
        $identity = "$guid/$channel/$($record.RecordId)/$ts"
        $hash = [Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes($identity))
        $id = ([BitConverter]::ToString($hash) -replace '-','').ToLower().Substring(0,32)
        $result += @{ id=$id; ts=$ts; host=$NodeName; kind='windows.event'; sensor='windows-eventlog-v1'; data=@{ channel=$channel; event_id=$record.Id; record_id=$record.RecordId; fields=$fields } }
    }
}
$system = Get-CimInstance Win32_ComputerSystem
$result += @{ id=[guid]::NewGuid().ToString(); ts=[DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ss.fff+00:00'); host=$NodeName; kind='windows.identity'; sensor='windows-cim-v1'; data=@{ domain=$system.Domain; part_of_domain=[bool]$system.PartOfDomain; domain_role=$system.DomainRole } }
ConvertTo-Json -InputObject @($result) -Depth 8 -Compress
