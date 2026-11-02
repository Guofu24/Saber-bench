param([Parameter(Mandatory)][string]$JobId, [Parameter(Mandatory)][string]$ExpectedDomain)
$ErrorActionPreference = 'Stop'
if ($JobId -notmatch '^[a-f0-9]{32}$' -or $ExpectedDomain -notmatch '^[a-z][a-z0-9-]{0,30}\.test$') { throw 'Invalid scoped response.' }
Import-Module ActiveDirectory
$domain = Get-ADDomain
if ($domain.DNSRoot -ine $ExpectedDomain -or (Get-CimInstance Win32_ComputerSystem).DomainRole -lt 4) { throw 'Response requires the configured lab domain controller.' }
$folder = 'C:\SaberLab\responses'
New-Item -ItemType Directory -Path $folder -Force | Out-Null
$receipt = Join-Path $folder ($JobId + '.json')
if (Test-Path -LiteralPath $receipt) { Get-Content -LiteralPath $receipt -Raw; return }
$account = Get-ADUser -Identity 'saber-red'
if ($account.DistinguishedName -ine ('CN=saber-red,OU=SABER,' + $domain.DistinguishedName)) { throw 'Only the synthetic user in the SABER OU may be contained.' }
$taskName = 'SABER-Restore-' + $JobId
$marker = Join-Path $folder ($JobId + '.started')
if (-not (Test-Path -LiteralPath $marker)) {
    [DateTime]::UtcNow.ToString('o') | Set-Content -LiteralPath $marker -Encoding ASCII
    # Register rollback before mutation. A crash cannot leave an unbounded disable.
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -NonInteractive -Command "Import-Module ActiveDirectory; Enable-ADAccount -Identity saber-red"'
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5)
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -User SYSTEM -RunLevel Highest -Force | Out-Null
    Disable-ADAccount -Identity $account
}
# A previously started job is observed, never blindly re-executed.
$disabled = -not (Get-ADUser -Identity 'saber-red').Enabled
$rollback = [bool](Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue)
$state = if ($disabled -and $rollback) { 'SUCCEEDED' } else { 'INDETERMINATE' }
$result = @{ id=$JobId; state=$state; disabled_observed=$disabled; restore_task_registered=$rollback } | ConvertTo-Json -Compress
$temporary = $receipt + '.tmp'
[IO.File]::WriteAllText($temporary, $result, [Text.UTF8Encoding]::new($false))
Move-Item -LiteralPath $temporary -Destination $receipt -Force
$result
