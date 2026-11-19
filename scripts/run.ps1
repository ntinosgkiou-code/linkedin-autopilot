# Runs one routine headless. Called by Task Scheduler, the dashboard, or by hand:
#   powershell -ExecutionPolicy Bypass -File scripts\run.ps1 -Task outreach
# Safe by design: one run at a time (lock), kill switch respected, problems become a visible ALERT instead of silent failure.
param(
    [Parameter(Mandatory = $true)][ValidateSet('outreach', 'inbox', 'post')][string]$Task,
    [ValidateSet('claude', 'codex')][string]$Agent,
    [switch]$Force   # manual test: ignore work days/hours (limits still apply)
)
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root
$env:Path = "$env:USERPROFILE\.local\bin;$env:APPDATA\npm;$env:Path"

$data = Join-Path $Root 'data'
$runs = Join-Path $data 'runs'
New-Item -ItemType Directory -Force $runs | Out-Null
$log = Join-Path $runs ("{0}_{1}.log" -f (Get-Date -Format 'yyyy-MM-dd_HHmm'), $Task)
$lock = Join-Path $data '.runlock'
$alert = Join-Path $data 'ALERT.txt'
$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

function Write-Log($m) { "$(Get-Date -Format 'HH:mm:ss') $m" | Out-File $log -Append -Encoding utf8 }

# Keep only the last 60 run logs
Get-ChildItem $runs -Filter *.log -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -Skip 60 | Remove-Item -Force -ErrorAction SilentlyContinue

# Kill switch: do not even start the agent. The inbox routine still runs so the report stays fresh.
if ((Test-Path (Join-Path $data 'STOP')) -and $Task -ne 'inbox') {
    Write-Log "STOPPED: $((Get-Content (Join-Path $data 'STOP') -Raw).Trim())"
    exit 0
}

# One run at a time: LinkedIn is driven through a single browser, two runs would collide. A lock older than 2 h is a crash leftover.
if (Test-Path $lock) {
    $age = 999999
    try { $age = $now - [int64]((Get-Content $lock -Raw | ConvertFrom-Json).start) } catch { }
    if ($age -lt 7200) { Write-Log "SKIPPED: another run ($Task) is still active."; exit 0 }
}
@{ task = $Task; start = $now; pid = $PID } | ConvertTo-Json -Compress | Set-Content $lock -Encoding ascii

try {
    if (-not $Agent) {
        $f = Join-Path $data '.agent'
        $Agent = if (Test-Path $f) { (Get-Content $f -Raw).Trim() } else { 'claude' }
    }
    if (-not (Get-Command $Agent -ErrorAction SilentlyContinue)) {
        $msg = "Το πρόγραμμα '$Agent' δεν βρέθηκε. Άνοιξε το START και ολοκλήρωσε το βήμα «Εγκατάσταση»."
        Write-Log $msg; Set-Content $alert $msg -Encoding utf8; exit 1
    }

    $prompt = "Run the routine: $Task. Follow AGENTS.md and prompts/$Task.md exactly. This is an unattended scheduled run: no human is present, do not ask questions."
    if ($Force) { $env:LA_FORCE = '1' }
    Write-Log "START $Task with $Agent"

    if ($Agent -eq 'claude') {
        # Permissions and the LinkedIn server are passed explicitly, so scheduled runs work even if
        # the folder was never opened interactively ("trusted") in Claude Code.
        $allowed = @('mcp__linkedin', 'Bash(uv run tools/guard.py:*)', 'Bash(uv run --quiet tools/guard.py:*)',
            'Bash(uv run tools/linkedin_post.py publish:*)', 'Bash(uv run tools/linkedin_post.py status)',
            'Read', 'Glob', 'Grep', 'Edit(data/**)')
        & claude -p $prompt --mcp-config "$Root\.mcp.json" --permission-mode acceptEdits --max-turns 200 --allowedTools $allowed *>&1 | Out-File $log -Append -Encoding utf8
    } else {
        & codex exec --full-auto --skip-git-repo-check -c 'sandbox_workspace_write.network_access=true' $prompt *>&1 | Out-File $log -Append -Encoding utf8
    }
    $code = $LASTEXITCODE
    Write-Log "END exit=$code"

    # Turn silent failures into something the user can see in the dashboard
    $text = Get-Content $log -Raw -ErrorAction SilentlyContinue
    if ($text -match 'Failed to authenticate|OAuth (access )?token|Invalid API key|Please run /login|Not logged in|401') {
        Set-Content $alert "Το Claude δεν είναι συνδεδεμένο ή έληξε η σύνδεση. Στον πίνακα πάτα «Σύνδεση» στο βήμα «Σύνδεση στο Claude»." -Encoding utf8
    } elseif ($text -match 'usage limit|rate limit|limit reached|credit balance|overloaded') {
        Set-Content $alert "Το Claude έφτασε προσωρινά το όριο χρήσης. Θα ξαναδοκιμάσει στην επόμενη προγραμματισμένη εκτέλεση. Αν επαναλαμβάνεται, μείωσε τις εκτελέσεις τη μέρα ή πάρε ισχυρότερο πλάνο." -Encoding utf8
    } elseif ($code -eq 0 -and (Test-Path $alert)) {
        Remove-Item $alert -Force -ErrorAction SilentlyContinue   # last run was healthy: clear old alert
    }
} catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    Set-Content $alert "Η εκτέλεση απέτυχε: $($_.Exception.Message)" -Encoding utf8
} finally {
    Remove-Item $lock -Force -ErrorAction SilentlyContinue
}
