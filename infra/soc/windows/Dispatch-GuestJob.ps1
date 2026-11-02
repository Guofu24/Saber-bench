param([string]$JobId, [string]$Tool, [string]$ExpectedDomain, [string]$Node, [string]$FileServer)
$ErrorActionPreference = 'Stop'
if ($JobId -notmatch '^[a-f0-9-]{32,36}$' -or $Tool -notin @('windows_work','windows_recon','windows_failed_logon','windows_inventory','windows_collect_evidence') -or $ExpectedDomain -notmatch '^[a-z][a-z0-9-]{0,30}\.test$' -or $Node -notmatch '^[a-z][a-z0-9-]{0,14}$' -or $FileServer -notmatch '^[a-z][a-z0-9-]{0,14}$') { throw 'Invalid fixed guest job.' }
$receipt = Join-Path (Join-Path 'C:\SaberLab\jobs' $JobId) 'receipt.json'
$name = 'SABER-Job-' + $JobId
if (Test-Path -LiteralPath $receipt) { Get-Content -LiteralPath $receipt -Raw; return }
if (-not (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue)) {
    # SYSTEM uses the domain machine identity for SMB. No credential delegation or
    # passwords in scheduled-task arguments are needed.
    $arguments = '-NoProfile -NonInteractive -File C:\SaberLab\Run-GuestJob.ps1 -JobId ' + $JobId + ' -Tool ' + $Tool + ' -ExpectedDomain ' + $ExpectedDomain + ' -Node ' + $Node + ' -FileServer ' + $FileServer
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $name -Action $action -Settings $settings -User SYSTEM -RunLevel Highest | Out-Null
    Start-ScheduledTask -TaskName $name
}
for ($i=0; $i -lt 65; $i++) {
    if (Test-Path -LiteralPath $receipt) {
        $result = Get-Content -LiteralPath $receipt -Raw
        Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
        $result
        return
    }
    Start-Sleep -Seconds 1
}
@{ id=$JobId; node=$Node; state='INDETERMINATE'; result=@{ reason='no_durable_receipt'; retry_allowed=$false } } | ConvertTo-Json -Depth 5 -Compress
