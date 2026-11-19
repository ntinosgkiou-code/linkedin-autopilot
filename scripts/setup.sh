#!/usr/bin/env bash
# LinkedIn Autopilot: macOS/Linux setup.  Run:  bash scripts/setup.sh [claude|codex]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="$HOME/.local/bin:$PATH"
ask() { read -r -p "$1 [Y/n] " a; [[ ! "$a" =~ ^[Nn] ]]; }

echo "[1/6] uv"
if ! command -v uvx >/dev/null; then
  ask "uv is not installed. Install it from astral.sh (~20 MB)?" || { echo "uv is required"; exit 1; }
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "[2/6] Agent"
AGENT="${1:-}"
if [ -z "$AGENT" ]; then
  if command -v claude >/dev/null && command -v codex >/dev/null; then
    read -r -p "Use (1) Claude Code or (2) Codex? [1/2] " c; [ "$c" = "2" ] && AGENT=codex || AGENT=claude
  elif command -v claude >/dev/null; then AGENT=claude
  elif command -v codex >/dev/null; then AGENT=codex
  else echo "Install Claude Code or Codex first, sign in, then re-run."; exit 1; fi
fi
mkdir -p data && echo "$AGENT" > data/.agent
if [ "$AGENT" = "codex" ]; then
  mkdir -p "$HOME/.codex"; CFG="$HOME/.codex/config.toml"
  if ! grep -q '^\[mcp_servers\.linkedin\]' "$CFG" 2>/dev/null; then
    cat >> "$CFG" <<'EOF'

[mcp_servers.linkedin]
command = "uvx"
args = ["mcp-server-linkedin"]
env = { UV_HTTP_TIMEOUT = "300" }
startup_timeout_sec = 180
tool_timeout_sec = 300
EOF
  fi
fi

echo "[3/6] LinkedIn login"
ask "Open the LinkedIn login window now?" && uvx mcp-server-linkedin --login || true

echo "[4/6] Post auto-publishing"
SCHED="$(uv run --quiet tools/guard.py schedule)"
j() { printf '%s' "$SCHED" | uv run --quiet python -c "import json,sys;d=json.load(sys.stdin);v=d['$1'];print(' '.join(v) if isinstance(v,list) else v)"; }
if [ "$(j post_enabled)" = "True" ] && [ ! -f data/.secrets/linkedin.json ]; then
  read -r -p "ADVANCED: connect the LinkedIn API for auto-posting? (say N if unsure) [y/N] " a; [[ "$a" =~ ^[Yy] ]] && uv run tools/linkedin_post.py auth || true
fi

echo "[5/6] Scheduling (cron)"
dnum() { case "$1" in Sun) echo 0;; Mon) echo 1;; Tue) echo 2;; Wed) echo 3;; Thu) echo 4;; Fri) echo 5;; Sat) echo 6;; esac; }
days() { local out=""; for d in $1; do out="$out,$(dnum "$d")"; done; echo "${out#,}"; }
WD="$(days "$(j work_days)")"
LINES=""
for t in $(j outreach_runs); do LINES="$LINES${t#*:} ${t%%:*} * * $WD bash \"$ROOT/scripts/run.sh\" outreach\n"; done
t="$(j inbox_run)"; LINES="$LINES${t#*:} ${t%%:*} * * $WD bash \"$ROOT/scripts/run.sh\" inbox\n"
if [ "$(j post_enabled)" = "True" ]; then
  t="$(j post_time)"; LINES="$LINES${t#*:} ${t%%:*} * * $(days "$(j post_days)") bash \"$ROOT/scripts/run.sh\" post\n"
fi
TZLINE="CRON_TZ=$(grep -E '^\s*timezone:' config.yaml | sed -E 's/.*"(.*)".*/\1/')"
( crontab -l 2>/dev/null | sed '/# >>> linkedin-autopilot/,/# <<< linkedin-autopilot/d'
  printf '# >>> linkedin-autopilot\n%s\n%b# <<< linkedin-autopilot\n' "$TZLINE" "$LINES" ) | crontab -
crontab -l | sed -n '/# >>> linkedin-autopilot/,/# <<< linkedin-autopilot/p'

echo "[6/6] Done"
uv run --quiet tools/guard.py report >/dev/null
cat <<EOF

Scheduled. Computer must be on.  Mode = config.yaml (default dry_run: nothing is sent).
  Test now:   bash scripts/run.sh outreach
  Results:    data/reports/  data/leads.csv  data/hot_leads.md  data/runs/
  Go live:    mode: "live"  in config.yaml
  Pause:      touch data/STOP
  Uninstall:  crontab -l | sed '/# >>> linkedin-autopilot/,/# <<< linkedin-autopilot/d' | crontab -
EOF
