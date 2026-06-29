# Quick deploy aliases for termux-agent
#
#   .\deploy.ps1              → git push + scp + restart
#   .\deploy.ps1 -Quick       → scp only (fast hotfix)
#   .\deploy.ps1 -GitOnly     → github + remote pull only

param(
    [switch]$Quick,
    [switch]$GitOnly,
    [string]$Message = "",
    [switch]$DryRun
)

$deployArgs = @{}
if ($Quick) { $deployArgs["Mode"] = "scp" }
elseif ($GitOnly) { $deployArgs["Mode"] = "git" }
else {
    $deployArgs["Mode"] = "both"
    $deployArgs["Restart"] = $true
}

if ($Message) { $deployArgs["Message"] = $Message }
if ($DryRun) { $deployArgs["DryRun"] = $true }

& "$PSScriptRoot\deploy_to_termux.ps1" @deployArgs
