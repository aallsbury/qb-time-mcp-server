[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = 'High')]
param(
    [Parameter(Mandatory = $true)][string]$ConfigPath,
    [ValidateSet('Logon', 'Boot')][string]$Mode = 'Logon',
    [PSCredential]$Credential,
    [string]$TaskName = 'QBTime MCP'
)
$ErrorActionPreference = 'Stop'
$configFile = (Resolve-Path -LiteralPath $ConfigPath).Path
$config = Get-Content -Raw -LiteralPath $configFile | ConvertFrom-Json
$supervisor = Join-Path $config.repoRoot 'deploy\windows\supervisor.py'
& $config.python $supervisor --config $configFile --check
if ($LASTEXITCODE -ne 0) { throw 'Supervisor configuration check failed.' }
if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    throw 'A task with this name already exists; review it instead of overwriting it.'
}
$pythonw = Join-Path (Split-Path -Parent $config.python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw -PathType Leaf)) { throw 'A matching pythonw.exe is required for hidden supervision.' }
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"{0}" --config "{1}"' -f $supervisor, $configFile) -WorkingDirectory $config.repoRoot
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5) -ExecutionTimeLimit ([TimeSpan]::Zero)
if ($Mode -eq 'Logon') {
    $current = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    if ($current -ine $config.account) { throw 'Logon mode must be registered by the configured account.' }
    $principal = New-ScheduledTaskPrincipal -UserId $config.account -LogonType Interactive -RunLevel Limited
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $config.account
    $task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings
    if ($PSCmdlet.ShouldProcess($TaskName, 'Register a limited-user logon task (does not start it)')) {
        Register-ScheduledTask -TaskName $TaskName -InputObject $task | Out-Null
    }
} else {
    if (-not $Credential -or $Credential.UserName -ine $config.account) {
        throw 'Boot mode requires an operator-supplied Get-Credential result for the configured account. Never store its password in files.'
    }
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $principal = New-ScheduledTaskPrincipal -UserId $config.account -LogonType Password -RunLevel Limited
    $task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings $settings
    if ($PSCmdlet.ShouldProcess($TaskName, 'Register a limited-user boot task (does not start it)')) {
        Register-ScheduledTask -TaskName $TaskName -InputObject $task -User $config.account -Password ($Credential.GetNetworkCredential().Password) | Out-Null
    }
}
# No Start-ScheduledTask: installation and production activation are separate steps.
