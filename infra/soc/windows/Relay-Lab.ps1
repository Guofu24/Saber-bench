#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param([Parameter(Mandatory)][string]$Bundle, [Parameter(Mandatory)][pscredential]$DomainCredential, [string]$Collector='http://127.0.0.1:7789', [switch]$Once, [switch]$OnTarget)
$ErrorActionPreference = 'Stop'
if (-not $OnTarget) { throw 'Use -OnTarget only on the isolated deployment host.' }
$uri = [uri]$Collector
if (-not $uri.IsLoopback -or $uri.Scheme -notin @('http','https') -or $uri.UserInfo) { throw 'Relay must reach the loopback collector. Use an authenticated SSH tunnel for a separate Linux SOC host.' }
$Collector = $Collector.TrimEnd('/')
$bundlePath = (Resolve-Path -LiteralPath $Bundle).Path
$spec = Get-Content -LiteralPath (Join-Path $bundlePath 'lab.json') -Raw | ConvertFrom-Json
$secrets = Get-Content -LiteralPath (Join-Path $bundlePath '.secrets\relay.json') -Raw | ConvertFrom-Json
$stateFile = Join-Path $bundlePath 'relay.receipt.json'
$bookmarks = @{}
if (Test-Path -LiteralPath $stateFile) {
    $saved = Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json
    foreach ($hostProperty in $saved.PSObject.Properties) {
        $bookmarks[$hostProperty.Name] = @{}
        foreach ($property in $hostProperty.Value.PSObject.Properties) { $bookmarks[$hostProperty.Name][$property.Name] = [long]$property.Value }
    }
}
$collect = [scriptblock]::Create((Get-Content -LiteralPath (Join-Path $bundlePath 'windows\Collect-Events.ps1') -Raw))
$relayHeaders = @{ Authorization='Bearer ' + $secrets.relay_token }
function Call-Collector([string]$Path, [hashtable]$Headers, $Body) {
    $args = @{ Uri=($Collector + $Path); Headers=$Headers; TimeoutSec=20; MaximumRedirection=0; ErrorAction='Stop' }
    if ($null -ne $Body) { $args.Method='Post'; $args.ContentType='application/json'; $args.Body=[Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 12 -Compress)) }
    Invoke-RestMethod @args
}
do {
    foreach ($node in $spec.windows) {
        $name = $spec.name + '-' + $node.name
        try {
            if ((Get-VM -Name $name).Notes -ne ('SABER managed: ' + $bundlePath)) { throw 'VM ownership mismatch.' }
            if (-not $bookmarks.ContainsKey($node.name)) { $bookmarks[$node.name] = @{} }
            $raw = Invoke-Command -VMName $name -Credential $DomainCredential -ScriptBlock $collect -ArgumentList $bookmarks[$node.name],$node.name,40
            $events = @($raw | ConvertFrom-Json)
            $headers = @{ Authorization='Bearer ' + $secrets.sources.($node.name) }
            $ack = Call-Collector '/ingest' $headers @{ events=$events }
            if (@($ack.accepted).Count -ne $events.Count -or @($events | Where-Object { $_.id -notin $ack.accepted }).Count) { throw 'Collector did not acknowledge full batch.' }
            foreach ($event in $events | Where-Object kind -eq 'windows.event') { $bookmarks[$node.name][$event.data.channel] = [long]$event.data.record_id }
            $tempState = $stateFile + '.tmp'
            [IO.File]::WriteAllText($tempState, ($bookmarks | ConvertTo-Json -Depth 6), [Text.UTF8Encoding]::new($false))
            Move-Item -LiteralPath $tempState -Destination $stateFile -Force
        } catch { Write-Warning ('Telemetry retry pending for ' + $node.name + '; diagnostics suppressed to protect credentials.') }
    }
    try {
        $jobs = Call-Collector '/guest/actions' $relayHeaders $null
        $dc = @($spec.windows | Where-Object role -eq 'dc')[0]
        $dcName = $spec.name + '-' + $dc.name
        if ((Get-VM -Name $dcName).Notes -ne ('SABER managed: ' + $bundlePath)) { throw 'DC ownership mismatch.' }
        foreach ($job in $jobs.jobs) {
            if ($job.id -notmatch '^[a-f0-9]{32}$' -or $job.action -ne 'contain_domain_user' -or $job.account -ne 'saber-red' -or $job.ttl_seconds -ne 300) { throw 'Unsupported guest action.' }
            $claimed = Call-Collector ('/guest/actions/' + $job.id + '/claim') $relayHeaders @{}
            if ($claimed.state -ne 'DISPATCHED') { continue }
            $receipt = Invoke-Command -VMName $dcName -Credential $DomainCredential -ArgumentList $job.id,$spec.domain -ScriptBlock {
                param($Id,$Domain)
                & 'C:\SaberLab\Respond-Domain.ps1' -JobId $Id -ExpectedDomain $Domain
            }
            $null = Call-Collector '/guest/receipts' $relayHeaders ($receipt | ConvertFrom-Json)
        }
    } catch { Write-Warning 'Domain response remains pending; inspect the guest receipt before retrying.' }
    if (-not $Once) { Start-Sleep -Seconds 5 }
} while (-not $Once)
