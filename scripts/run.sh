#!/usr/bin/env bash
# Runs one routine headless (macOS/Linux). Called by cron, the dashboard, or by hand:  bash scripts/run.sh outreach
# One run at a time (lock), kill switch respected, failures become a visible ALERT.
set -u
TASK="${1:?usage: run.sh outreach|inbox|post}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="$HOME/.local/bin:/usr/local/bin:/opt/homebrew/bin:$HOME/.npm-global/bin:$PATH"
mkdir -p data/runs
LOG="data/runs/$(date +%Y-%m-%d_%H%M)_${TASK}.log"
LOCK="data/.runlock"; ALERT="data/ALERT.txt"
log() { echo "$(date +%H:%M:%S) $*" >> "$LOG"; }
ls -1t data/runs/*.log 2>/dev/null | tail -n +61 | xargs rm -f 2>/dev/null

if [ -f data/STOP ] && [ "$TASK" != "inbox" ]; then log "STOPPED: $(cat data/STOP)"; exit 0; fi

NOW=$(date +%s)
if [ -f "$LOCK" ]; then
  START=$(sed -n 's/.*"start": *\([0-9]*\).*/\1/p' "$LOCK" | head -1)
  if [ -n "${START:-}" ] && [ $((NOW - START)) -lt 7200 ]; then log "SKIPPED: another run is still active."; exit 0; fi
fi
printf '{"task": "%s", "start": %s}\n' "$TASK" "$NOW" > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

AGENT="${2:-$(cat data/.agent 2>/dev/null || echo claude)}"
if ! command -v "$AGENT" >/dev/null 2>&1; then
  echo "The program '$AGENT' was not found. Run bash scripts/setup.sh" > "$ALERT"; log "agent missing"; exit 1
fi
PROMPT="Run the routine: $TASK. Follow AGENTS.md and prompts/$TASK.md exactly. This is an unattended scheduled run: no human is present, do not ask questions."
log "START $TASK with $AGENT"

if [ "$AGENT" = "claude" ]; then
  claude -p "$PROMPT" --mcp-config "$ROOT/.mcp.json" --permission-mode acceptEdits --max-turns 200 \
    --allowedTools "mcp__linkedin" "Bash(uv run tools/guard.py:*)" "Bash(uv run --quiet tools/guard.py:*)" \
    "Bash(uv run tools/linkedin_post.py publish:*)" "Bash(uv run tools/linkedin_post.py status)" \
    "Read" "Glob" "Grep" "Edit(data/**)" >> "$LOG" 2>&1
else
  codex exec --full-auto --skip-git-repo-check -c 'sandbox_workspace_write.network_access=true' "$PROMPT" >> "$LOG" 2>&1
fi
CODE=$?
log "END exit=$CODE"
if grep -qE 'Failed to authenticate|OAuth (access )?token|Invalid API key|Please run /login|Not logged in|401' "$LOG"; then
  echo "Claude is not logged in or the login expired. Run: claude  then /login" > "$ALERT"
elif grep -qiE 'usage limit|rate limit|limit reached|credit balance|overloaded' "$LOG"; then
  echo "Claude hit a usage limit. The next scheduled run will try again." > "$ALERT"
elif [ "$CODE" -eq 0 ]; then rm -f "$ALERT"; fi
