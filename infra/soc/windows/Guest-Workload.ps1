param([string]$Domain, [string]$FileServer, [ValidateSet('client','red')][string]$Role)
$ErrorActionPreference = 'Stop'
if ($Domain -notmatch '^[a-z][a-z0-9-]{0,30}\.test$' -or $FileServer -notmatch '^soc-[a-z0-9-]+$') { throw 'Only the configured lab domain is supported.' }
$folder = 'C:\SaberWork'
New-Item -ItemType Directory -Path $folder -Force | Out-Null
Resolve-DnsName ($FileServer + '.' + $Domain) -ErrorAction SilentlyContinue | Out-Null
if ($Role -eq 'client') {
    # Runs as a domain-joined machine; the isolated share grants Domain Computers access.
    $content = 'Synthetic work ' + [DateTime]::UtcNow.ToString('o')
    Set-Content -LiteralPath (Join-Path $folder 'daily-note.txt') -Value $content
    $destination = '\\' + $FileServer + '\SaberWork\' + $env:COMPUTERNAME + '.txt'
    Copy-Item -LiteralPath (Join-Path $folder 'daily-note.txt') -Destination $destination -Force
    Get-Content -LiteralPath $destination | Out-Null
} else {
    # One intentionally failed logon to our synthetic account, not password guessing.
    Add-Type -AssemblyName System.DirectoryServices.AccountManagement
    $context = New-Object System.DirectoryServices.AccountManagement.PrincipalContext('Domain', $Domain)
    try { $null = $context.ValidateCredentials('saber-red', [guid]::NewGuid().ToString()) } finally { $context.Dispose() }
    Get-ChildItem ('\\' + $FileServer + '\SaberWork') | Select-Object -First 5 | Out-Null
}
