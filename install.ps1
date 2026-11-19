# LinkedIn Autopilot installer (Windows). Safe to run again: updates the program, keeps your settings and data.
#
#   From the unzipped folder:   powershell -ExecutionPolicy Bypass -File install.ps1
#   From a download link:       powershell -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create((irm <LINK-TO-install.ps1>))) -Url <LINK-TO-ZIP>"
#
# Options: -Dir <folder>  -Url <zip link>  -Agent claude|codex|both|auto  -Yes (no questions)  -NoLaunch  -NoShortcut  -SkipDeps
param(
    [string]$Dir,
    [string]$Url = $env:LA_ZIP_URL,
    [ValidateSet('claude', 'codex', 'both', 'auto')][string]$Agent = 'auto',
    [switch]$Yes, [switch]$NoLaunch, [switch]$NoShortcut, [switch]$SkipDeps
)
$ErrorActionPreference = 'Stop'
$H = if ($env:LA_HOME) { $env:LA_HOME } else { $env:USERPROFILE }   # LA_HOME lets tests run without touching the real profile
if (-not $Dir) { $Dir = Join-Path $H 'linkedin-autopilot' }
$env:Path = "$H\.local\bin;$env:APPDATA\npm;$env:Path"

function Say($m, $c = 'Cyan') { Write-Host "`n== $m" -ForegroundColor $c }
function Ask($q) { if ($Yes) { return $true }; (Read-Host "$q [Y/n]") -notmatch '^(n|no)$' }

# 1. Find the package: next to this script, or download it
Say '1/5 Getting the files'
$src = $null
if ($PSScriptRoot -and (Test-Path (Join-Path $PSScriptRoot 'tools\guard.py'))) { $src = $PSScriptRoot }
elseif ($Url) {
    $tmp = Join-Path ([IO.Path]::GetTempPath()) ("la_" + [guid]::NewGuid().ToString('N').Substring(0, 8))
    New-Item -ItemType Directory $tmp | Out-Null
    Invoke-WebRequest -Uri $Url -OutFile "$tmp\pkg.zip" -UseBasicParsing
    Expand-Archive "$tmp\pkg.zip" -DestinationPath "$tmp\x" -Force
    $hit = Get-ChildItem "$tmp\x" -Recurse -Filter guard.py | Select-Object -First 1
    if (-not $hit) { throw 'The download does not look like LinkedIn Autopilot (tools\guard.py missing).' }
    $src = Split-Path (Split-Path $hit.FullName -Parent) -Parent
} else { throw 'Run this from the unzipped folder, or pass -Url <link to the zip>.' }

$same = (Resolve-Path $src).Path.TrimEnd('\') -ieq ([IO.Path]::GetFullPath($Dir)).TrimEnd('\')
if (-not $same) {
    $update = Test-Path (Join-Path $Dir 'config.yaml')
    New-Item -ItemType Directory -Force $Dir | Out-Null
    if ($update) {   # update: new program files, but keep the user's settings and all data
        robocopy $src $Dir /E /XD data __pycache__ /XF config.yaml /NFL /NDL /NJH /NJS /NP | Out-Null
        Write-Host "Updated $Dir (your config.yaml and data were kept)."
    } else {
        robocopy $src $Dir /E /XD __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
        Write-Host "Installed to $Dir"
    }
    if ($LASTEXITCODE -ge 8) { throw "Copy failed (robocopy code $LASTEXITCODE)" }
    $global:LASTEXITCODE = 0
} else { Write-Host "Using $Dir" }
New-Item -ItemType Directory -Force (Join-Path $Dir 'data') | Out-Null

# 2. uv
Say '2/5 Tools'
if (-not $SkipDeps) {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        if (-not (Ask 'Install "uv" (20 MB, runs the Python parts)?')) { throw 'uv is required.' }
        powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
        $env:Path = "$H\.local\bin;$env:Path"
    }
    uv --version
} else { Write-Host 'Skipped.' }

# 3. Register as a skill for the agents on this machine (a small pointer; the product itself stays in $Dir)
Say '3/5 Agent skill'
$skillText = @"
---
name: linkedin-autopilot
description: Runs the user's LinkedIn on autopilot, locally: finds leads, writes and sends personalized DMs within safe limits, writes posts, reads replies. Use when the user wants to automate LinkedIn outreach/posts, or to install, configure, run, pause or check LinkedIn Autopilot.
---
# LinkedIn Autopilot
Installed at: $Dir
Open that folder, then read `SKILL.md` (what to do for each request) and `AGENTS.md` (the rules). To install or repair, follow `AGENT-INSTALL.md`.
Never enter the user's LinkedIn credentials and never switch outreach to live mode unless the user clearly asks.
"@
$targets = @()
$haveClaude = [bool](Get-Command claude -ErrorAction SilentlyContinue) -or (Test-Path "$H\.claude")
$haveCodex = [bool](Get-Command codex -ErrorAction SilentlyContinue) -or (Test-Path "$H\.codex")
if ($Agent -in 'claude', 'both' -or ($Agent -eq 'auto' -and $haveClaude)) { $targets += "$H\.claude\skills\linkedin-autopilot" }
if ($Agent -in 'codex', 'both' -or ($Agent -eq 'auto' -and $haveCodex)) { $targets += "$H\.codex\skills\linkedin-autopilot" }
foreach ($t in $targets) {
    New-Item -ItemType Directory -Force $t | Out-Null
    [IO.File]::WriteAllText("$t\SKILL.md", $skillText, (New-Object Text.UTF8Encoding $false))
    Write-Host "Registered skill: $t"
}
if (-not $targets) { Write-Host 'No agent CLI found yet. Install Claude Code or Codex later and run this installer again (or just open the folder with your agent).' }
if ($targets -match 'codex') {
    $cfg = "$H\.codex\config.toml"
    if (-not (Test-Path $cfg) -or -not (Select-String -Path $cfg -Pattern '^\[mcp_servers\.linkedin\]' -Quiet)) {
        New-Item -ItemType Directory -Force "$H\.codex" | Out-Null
        # NO BOM: a byte-order mark at the start of a TOML file can stop Codex from reading it
        [IO.File]::AppendAllText($cfg, "`n[mcp_servers.linkedin]`ncommand = `"uvx`"`nargs = [`"mcp-server-linkedin`"]`nenv = { UV_HTTP_TIMEOUT = `"300`" }`nstartup_timeout_sec = 180`ntool_timeout_sec = 300`n", (New-Object Text.UTF8Encoding $false))
        Write-Host 'Added the LinkedIn server to Codex.'
    }
}

# 4. Desktop shortcut
Say '4/5 Shortcut'
if (-not $NoShortcut) {
    try {
        $desk = [Environment]::GetFolderPath('Desktop')
        $lnk = (New-Object -ComObject WScript.Shell).CreateShortcut("$desk\LinkedIn Autopilot.lnk")
        $lnk.TargetPath = "$Dir\START.bat"; $lnk.WorkingDirectory = $Dir; $lnk.Description = 'LinkedIn Autopilot dashboard'; $lnk.Save()
        Write-Host "Desktop shortcut created: LinkedIn Autopilot"
    } catch { Write-Host "Could not create the shortcut ($($_.Exception.Message)). Use $Dir\START.bat instead." }
} else { Write-Host 'Skipped.' }

# 5. Start
Say '5/5 Done' 'Green'
Write-Host @"
Installed in: $Dir
Next: the dashboard opens. Follow its checklist (log in to Claude and LinkedIn, fill the settings, press 'Test').
It starts in TEST mode and sends nothing until you turn it on.
Later, open it with the 'LinkedIn Autopilot' desktop icon or $Dir\START.bat
"@
if (-not $NoLaunch) { Start-Process -FilePath "$Dir\START.bat" -WorkingDirectory $Dir }
