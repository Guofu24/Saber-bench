param(
    [Parameter(Mandatory)][string]$JobId,
    [Parameter(Mandatory)][ValidateSet('windows_work','windows_recon','windows_failed_logon','windows_inventory','windows_collect_evidence')][string]$Tool,
    [Parameter(Mandatory)][string]$ExpectedDomain,
    [Parameter(Mandatory)][string]$Node,
    [Parameter(Mandatory)][string]$FileServer
)
$ErrorActionPreference = 'Stop'
if ($JobId -notmatch '^[a-f0-9-]{32,36}$' -or $Node -notmatch '^[a-z][a-z0-9-]{0,14}$' -or $FileServer -notmatch '^[a-z][a-z0-9-]{0,14}$') { throw 'Invalid lab job identity.' }
$system = Get-CimInstance Win32_ComputerSystem
if ($ExpectedDomain -notmatch '^[a-z][a-z0-9-]{0,30}\.test$' -or $system.Domain -ine $ExpectedDomain -or $env:COMPUTERNAME -ine $Node -or -not $system.PartOfDomain) { throw 'Guest identity does not match this lab job.' }
$directory = Join-Path 'C:\SaberLab\jobs' $JobId
New-Item -ItemType Directory -Path $directory -Force | Out-Null
$receiptFile = Join-Path $directory 'receipt.json'
$marker = Join-Path $directory 'started.json'
if (Test-Path -LiteralPath $receiptFile) { Get-Content -LiteralPath $receiptFile -Raw; return }
if (Test-Path -LiteralPath $marker) {
    # Do not repeat an operation that may have finished before its receipt was written.
    @{ id=$JobId; node=$Node; state='INDETERMINATE'; result=@{ reason='started_without_receipt'; retry_allowed=$false } } | ConvertTo-Json -Depth 5 -Compress
    return
}
$claim = [IO.File]::Open($marker, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
try {
    $markerBytes = [Text.Encoding]::UTF8.GetBytes((@{ pid=$PID; tool=$Tool; at=[DateTime]::UtcNow.ToString('o') } | ConvertTo-Json -Compress))
    $claim.Write($markerBytes, 0, $markerBytes.Length); $claim.Flush($true)
} finally { $claim.Dispose() }
$state = 'SUCCEEDED'
try {
    switch ($Tool) {
        'windows_work' {
            & 'C:\SaberLab\Guest-Workload.ps1' -Domain $ExpectedDomain -FileServer $FileServer -Role client
            $file = '\\' + $FileServer + '\SaberWork\' + $env:COMPUTERNAME + '.txt'
            $result = @{ file_sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLower(); bytes=(Get-Item -LiteralPath $file).Length; path=$file; pid=$PID }
        }
        'windows_recon' {
            $records = @(Resolve-DnsName ($FileServer + '.' + $ExpectedDomain) | Select-Object -First 10 Name,Type,IPAddress)
            $files = @(Get-ChildItem ('\\' + $FileServer + '\SaberWork') -File | Select-Object -First 20 Name,Length)
            $result = @{ dns=$records; files=$files; pid=$PID; scope='configured lab share only' }
        }
        'windows_failed_logon' {
            Add-Type -AssemblyName System.DirectoryServices.AccountManagement
            $context = New-Object System.DirectoryServices.AccountManagement.PrincipalContext('Domain', $ExpectedDomain)
            try { $accepted = $context.ValidateCredentials('saber-red', [guid]::NewGuid().ToString()) } finally { $context.Dispose() }
            if ($accepted) { throw 'Expected failed lab authentication was accepted.' }
            $result = @{ account='saber-red'; authentication_succeeded=$accepted; attempts=1; pid=$PID }
        }
        'windows_inventory' {
            $processes = @(Get-Process | Select-Object -First 50 Id,ProcessName)
            $connections = @(Get-NetTCPConnection -State Established -ErrorAction SilentlyContinue | Select-Object -First 50 LocalAddress,LocalPort,RemoteAddress,RemotePort,OwningProcess)
            $result = @{ processes=$processes; connections=$connections; domain=$system.Domain; pid=$PID }
        }
        'windows_collect_evidence' {
            $events = & 'C:\SaberLab\Collect-Events.ps1' -Bookmarks @{} -NodeName $Node -Limit 25
            $artifact = Join-Path $directory 'event-evidence.json'
            [IO.File]::WriteAllText($artifact, $events, [Text.UTF8Encoding]::new($false))
            $result = @{ artifact='event-evidence.json'; sha256=(Get-FileHash -LiteralPath $artifact -Algorithm SHA256).Hash.ToLower(); bytes=(Get-Item -LiteralPath $artifact).Length; records=@($events | ConvertFrom-Json).Count; pid=$PID; scope='bounded Event Log export, not a disk or memory image' }
        }
    }
} catch {
    $state = 'FAILED'
    $result = @{ error_type=$_.Exception.GetType().Name; retry_allowed=$false; pid=$PID }
}
$receipt = @{ id=$JobId; node=$Node; state=$state; result=$result } | ConvertTo-Json -Depth 8 -Compress
$temporary = $receiptFile + '.tmp'
[IO.File]::WriteAllText($temporary, $receipt, [Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $temporary -Destination $receiptFile -Force
$receipt
