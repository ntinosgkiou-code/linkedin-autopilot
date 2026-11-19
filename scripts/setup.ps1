# LinkedIn Autopilot: Windows setup. Run from the package folder:
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1
# Safe to run again any time (for example after you change the schedule in config.yaml).
param([ValidateSet('claude', 'codex')][string]$Agent, [switch]$ScheduleOnly)

$ErrorActionPreference = 'Stop'
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
$env:Path = "$env:USERPROFILE\.local\bin;$env:APPDATA\npm;$env:Path"

function Write-Step($n, $t) { Write-Host "`n[$n/6] $t" -ForegroundColor Cyan }
function Confirm-Yes($q) { (Read-Host "$q [Y/n]") -notmatch '^(n|no)$' }
function Confirm-No($q) { (Read-Host "$q [y/N]") -match '^(y|yes)$' }

if (-not $ScheduleOnly) {
# 1. uv (runs the LinkedIn server and the Python tools; it brings its own Python)
Write-Step 1 'Checking uv'
if (-not (Get-Command uvx -ErrorAction SilentlyContinue)) {
    if (-not (Confirm-Yes 'uv is not installed. Install it now from astral.sh (~20 MB)?')) { throw 'uv is required.' }
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
uv --version

# 2. Which AI agent runs the routines
Write-Step 2 'Choosing the AI agent'
$hasClaude = [bool](Get-Command claude -ErrorAction SilentlyContinue)
$hasCodex = [bool](Get-Command codex -ErrorAction SilentlyContinue)
if (-not $Agent) {
    if ($hasClaude -and $hasCodex) { $Agent = if ((Read-Host 'Use (1) Claude Code or (2) Codex? [1/2]') -eq '2') { 'codex' } else { 'claude' } }
    elseif ($hasClaude) { $Agent = 'claude' }
    elseif ($hasCodex) { $Agent = 'codex' }
    else {
        Write-Host 'No AI agent found. Claude Code needs a paid Claude plan (Pro or higher).'
        if (-not (Confirm-Yes 'Install Claude Code now?')) { throw 'Install Claude Code or Codex, then run this again.' }
        powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
        if (-not (Get-Command claude -ErrorAction SilentlyContinue)) { throw 'Claude Code did not install. Close this window and run 1-INSTALL.bat again.' }
        $Agent = 'claude'
        Write-Host 'Claude Code installed. You will sign in to it in step 2 (2-MY-SETTINGS.bat).' -ForegroundColor Green
    }
}
New-Item -ItemType Directory -Force (Join-Path $Root 'data') | Out-Null
Set-Content -Path (Join-Path $Root 'data\.agent') -Value $Agent -Encoding ascii
Write-Host "Agent: $Agent"

if ($Agent -eq 'codex') {
    $cfgDir = Join-Path $env:USERPROFILE '.codex'
    $cfg = Join-Path $cfgDir 'config.toml'
    New-Item -ItemType Directory -Force $cfgDir | Out-Null
    if (-not (Test-Path $cfg) -or -not (Select-String -Path $cfg -Pattern '^\[mcp_servers\.linkedin\]' -Quiet)) {
        $block = @'

[mcp_servers.linkedin]
command = "uvx"
args = ["mcp-server-linkedin"]
env = { UV_HTTP_TIMEOUT = "300" }
startup_timeout_sec = 180
tool_timeout_sec = 300
'@
        [IO.File]::AppendAllText($cfg, "`n$block`n", (New-Object Text.UTF8Encoding $false))   # no BOM: it can break TOML parsing
        Write-Host "Added the LinkedIn server to $cfg"
    } else { Write-Host 'Codex already has the LinkedIn server.' }
}

# 3. LinkedIn login (a browser window opens: YOU sign in; nothing is typed for you)
Write-Step 3 'LinkedIn login'
if (Confirm-Yes 'Open the LinkedIn login window now? (needed once; first run downloads a browser, ~2 min)') {
    uvx mcp-server-linkedin --login
}

# 4. Official API for auto-publishing posts (optional)
Write-Step 4 'Post auto-publishing (optional)'
$sched = (uv run --quiet tools/guard.py schedule) | Out-String | ConvertFrom-Json
if ($sched.post_enabled) {
    $tok = Join-Path $Root 'data\.secrets\linkedin.json'
    if (Test-Path $tok) { uv run --quiet tools/linkedin_post.py status }
    elseif (Confirm-No 'ADVANCED: connect the LinkedIn API so posts publish automatically? (needs the developer app from the guide; say N if unsure)') {
        uv run --quiet tools/linkedin_post.py auth
    } else { Write-Host 'Skipped. Posts are saved to data\posts\ for you to copy-paste.' }
} else { Write-Host 'Posts are disabled in config.yaml.' }
}  # end of: if (-not $ScheduleOnly)

# 5. Schedule (Windows Task Scheduler)
Write-Step 5 'Scheduling'
$sched = (uv run --quiet tools/guard.py schedule) | Out-String | ConvertFrom-Json
$dayMap = @{ Mon = 'Monday'; Tue = 'Tuesday'; Wed = 'Wednesday'; Thu = 'Thursday'; Fri = 'Friday'; Sat = 'Saturday'; Sun = 'Sunday' }
$workDays = @($sched.work_days | ForEach-Object { $dayMap[$_] })
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 90) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$runPs1 = Join-Path $Root 'scripts\run.ps1'

function Register-Routine($name, $task, $days, $times) {
    $act = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$runPs1`" -Task $task" -WorkingDirectory $Root
    $trig = @($times | ForEach-Object { New-ScheduledTaskTrigger -Weekly -DaysOfWeek $days -At $_ })
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $name -TaskPath '\LinkedInAutopilot\' -Action $act -Trigger $trig -Settings $settings -Description "LinkedIn Autopilot: $task" | Out-Null
    Write-Host ("  {0,-10} {1} at {2}" -f $task, ($days -join ','), ($times -join ', '))
}
Register-Routine 'Outreach' 'outreach' $workDays @($sched.outreach_runs)
Register-Routine 'Inbox' 'inbox' $workDays @($sched.inbox_run)
if ($sched.post_enabled -and @($sched.post_days).Count -gt 0) {
    Register-Routine 'Post' 'post' @($sched.post_days | ForEach-Object { $dayMap[$_] }) @($sched.post_time)
} else { Unregister-ScheduledTask -TaskName 'Post' -Confirm:$false -ErrorAction SilentlyContinue }

# 6. Done
Write-Step 6 'Done'
uv run --quiet tools/guard.py report | Out-Null
Write-Host @"

LinkedIn Autopilot is scheduled. Your PC must be on, and you must be logged in to Windows.
It starts in TEST mode: nothing is sent until you run 4-GO-LIVE.bat.

  Next:        2-MY-SETTINGS.bat   (tell it about you and your customers)
  Then:        3-TEST.bat          (test run, sends nothing)
  Then:        4-GO-LIVE.bat       (start sending for real)
  Every day:   SEE-RESULTS.bat     (who replied)
  Pause:       PAUSE.bat           Resume: RESUME.bat
"@ -ForegroundColor Green
