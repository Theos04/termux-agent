# Deploy termux-agent to GitHub + Termux
#
# Usage:
#   .\deploy_to_termux.ps1                    # git push + scp (default)
#   .\deploy_to_termux.ps1 -Mode git          # GitHub only, remote git pull
#   .\deploy_to_termux.ps1 -Mode scp          # SCP only (fast hotfix)
#   .\deploy_to_termux.ps1 -Message "fix x"   # custom commit message
#   .\deploy_to_termux.ps1 -Upgrade -Restart  # run upgrade.sh + restart agent on Termux
#
# Config: deploy.config.json (host, port, remoteDir)

param(
    [ValidateSet("git", "scp", "both")]
    [string]$Mode = "both",

    [string]$Message = "",

    [switch]$SkipCommit,
    [switch]$SkipPush,
    [switch]$Upgrade,
    [switch]$Restart,
    [switch]$DryRun,

    [string]$Host_ = "",
    [int]$Port = 0,
    [string]$RemoteDir = ""
)

$ErrorActionPreference = "Stop"
$LocalDir = $PSScriptRoot

# Load config
$configPath = Join-Path $LocalDir "deploy.config.json"
$config = @{
    host      = "u0_a215@100.93.132.97"
    port      = 8022
    remoteDir = "~/automation/chrome-launcher"
    branch    = "main"
    github    = "https://github.com/Theos04/termux-agent.git"
}
if (Test-Path $configPath) {
    $fileConfig = Get-Content $configPath -Raw | ConvertFrom-Json
    foreach ($key in $fileConfig.PSObject.Properties.Name) {
        $config[$key] = $fileConfig.$key
    }
}

if ($Host_) { $config.host = $Host_ }
if ($Port) { $config.port = $Port }
if ($RemoteDir) { $config.remoteDir = $RemoteDir }

$sshTarget = $config.host
$sshPort = $config.port
$remote = $config.remoteDir
$branch = $config.branch

function Write-Step($text) {
    Write-Host ""
    Write-Host "==> $text" -ForegroundColor Cyan
}

function Invoke-Remote($command) {
    if ($DryRun) {
        Write-Host "[dry-run] ssh -p $sshPort ${sshTarget} `"$command`"" -ForegroundColor DarkGray
        return
    }
    ssh -p $sshPort $sshTarget $command
}

function Deploy-Git {
    Write-Step "Git: push to GitHub ($($config.github))"

    Push-Location $LocalDir
    try {
        $status = git status --porcelain
        if ($status -and -not $SkipCommit) {
            if (-not $Message) {
                $Message = "Deploy update $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
            }
            Write-Host "Committing changes..."
            git add -A
            git commit -m $Message
        }
        elseif ($status -and $SkipCommit) {
            Write-Host "Uncommitted changes (SkipCommit set) — only pushing existing commits" -ForegroundColor Yellow
        }
        else {
            Write-Host "Working tree clean"
        }

        if (-not $SkipPush) {
            if ($DryRun) {
                Write-Host "[dry-run] git push origin $branch" -ForegroundColor DarkGray
            }
            else {
                git push origin $branch
            }
        }

        Write-Step "Git: pull on Termux"
        # upgrade.sh handles SCP/git conflicts cleanly
        if ($Upgrade) {
            Invoke-Remote "cd $remote && bash upgrade.sh"
        }
        else {
            Invoke-Remote "cd $remote && git fetch origin $branch && git reset --hard origin/$branch"
            Invoke-Remote "cd $remote && pip install -q -r requirements.txt 2>/dev/null; pip install -r requirements.txt"
        }
    }
    finally {
        Pop-Location
    }
}

function Deploy-Scp {
    Write-Step "SCP: stream files to ${sshTarget}:${remote}"

    Push-Location $LocalDir
    try {
        $tarArgs = @(
            "-czf", "-",
            "--exclude=__pycache__",
            "--exclude=*.pyc",
            "--exclude=.git",
            "--exclude=venv",
            "--exclude=.env",
            "--exclude=*.db",
            "--exclude=*.db-wal",
            "--exclude=*.db-shm",
            "--exclude=logs",
            "--exclude=.agent.pid",
            "--exclude=deploy.config.json",
            "agent", "handlers", "api",
            "run_agent.py", "requirements.txt",
            "setup_termux.sh", "upgrade.sh",
            "install_termux.sh", "start_agent.sh", "stop_agent.sh",
            "README.md",
            "cdpv116.py", "fetch_page2.py", "session_db.py",
            "api-server-9226.py", "api.py",
            "scripts-library"
        )

        if ($DryRun) {
            Write-Host "[dry-run] tar $($tarArgs -join ' ') | ssh ..." -ForegroundColor DarkGray
            return
        }

        Write-Host "One password prompt for SCP..."
        & tar @tarArgs | ssh -p $sshPort $sshTarget "cd $remote && tar xzf -"
        Write-Host "SCP complete" -ForegroundColor Green

        Invoke-Remote "cd $remote && pip install -q -r requirements.txt 2>/dev/null; chmod +x upgrade.sh start_agent.sh stop_agent.sh install_termux.sh 2>/dev/null; true"
    }
    finally {
        Pop-Location
    }
}

function Restart-Agent {
    Write-Step "Restart agent on Termux"
    $cmd = @"
cd $remote
mkdir -p logs
if [ -f .agent.pid ]; then kill `$(cat .agent.pid) 2>/dev/null; rm -f .agent.pid; fi
pkill -f 'run_agent.py run' 2>/dev/null || true
sleep 1
nohup python run_agent.py run --api --workers 1 > logs/agent.log 2>&1 &
echo `$! > .agent.pid
echo Agent restarted PID `$(cat .agent.pid)
"@
    Invoke-Remote $cmd
}

# --- Main ---

Write-Host "termux-agent deploy" -ForegroundColor Green
Write-Host "  Mode:     $Mode"
Write-Host "  Target:   ${sshTarget}:${remote}"
Write-Host "  Branch:   $branch"

switch ($Mode) {
    "git"  { Deploy-Git }
    "scp"  { Deploy-Scp }
    "both" { Deploy-Git; Deploy-Scp }
}

if ($Restart) {
    Restart-Agent
}

Write-Host ""
Write-Host "Done!" -ForegroundColor Green
Write-Host "  Dashboard: http://$($sshTarget.Split('@')[1]):9227/"
Write-Host "  Termux:    cd $remote && python run_agent.py status"
if (-not $Restart) {
    Write-Host "  Restart:   .\deploy_to_termux.ps1 -Restart"
}
