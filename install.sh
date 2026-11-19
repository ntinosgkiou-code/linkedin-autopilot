#!/usr/bin/env bash
# LinkedIn Autopilot installer (macOS / Linux). Safe to run again: updates the program, keeps settings and data.
#   From the unzipped folder:  bash install.sh
#   From a link:               curl -fsSL <LINK-TO-install.sh> | bash -s -- --url <LINK-TO-ZIP>
# Options: --dir <folder> --url <zip> --agent claude|codex|both|auto --yes --no-launch
set -euo pipefail
H="${LA_HOME:-$HOME}"; DIR="$H/linkedin-autopilot"; URL="${LA_ZIP_URL:-}"; AGENT=auto; YES=0; LAUNCH=1
while [ $# -gt 0 ]; do case "$1" in
  --dir) DIR="$2"; shift 2;; --url) URL="$2"; shift 2;; --agent) AGENT="$2"; shift 2;;
  --yes) YES=1; shift;; --no-launch) LAUNCH=0; shift;; *) echo "unknown option $1"; exit 1;; esac; done
export PATH="$H/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
ask() { [ "$YES" = 1 ] && return 0; read -r -p "$1 [Y/n] " a; [[ ! "$a" =~ ^[Nn] ]]; }

echo "== 1/4 Getting the files"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo "")"
if [ -n "$HERE" ] && [ -f "$HERE/tools/guard.py" ]; then SRC="$HERE"
elif [ -n "$URL" ]; then
  TMP="$(mktemp -d)"; curl -fsSL "$URL" -o "$TMP/pkg.zip"; (cd "$TMP" && unzip -q pkg.zip)
  G="$(find "$TMP" -name guard.py -path '*tools*' | head -1)"; [ -n "$G" ] || { echo "Not a LinkedIn Autopilot package"; exit 1; }
  SRC="$(dirname "$(dirname "$G")")"
else echo "Run from the unzipped folder, or pass --url <zip link>"; exit 1; fi

if [ "$(cd "$SRC" && pwd)" != "$(mkdir -p "$DIR" && cd "$DIR" && pwd)" ]; then
  if [ -f "$DIR/config.yaml" ]; then
    (cd "$SRC" && tar cf - --exclude=./data --exclude=./config.yaml --exclude=__pycache__ .) | (cd "$DIR" && tar xf -)
    echo "Updated $DIR (config.yaml and data kept)"
  else (cd "$SRC" && tar cf - --exclude=__pycache__ .) | (cd "$DIR" && tar xf -); echo "Installed to $DIR"; fi
fi
mkdir -p "$DIR/data"; chmod +x "$DIR"/*.sh "$DIR"/*.command "$DIR"/scripts/*.sh 2>/dev/null || true

echo "== 2/4 Tools"
if ! command -v uv >/dev/null; then ask "Install uv (20 MB)?" || exit 1; curl -LsSf https://astral.sh/uv/install.sh | sh; export PATH="$H/.local/bin:$PATH"; fi
uv --version

echo "== 3/4 Agent skill"
SKILL="---
name: linkedin-autopilot
description: Runs the user's LinkedIn on autopilot, locally: finds leads, writes and sends personalized DMs within safe limits, writes posts, reads replies. Use when the user wants to automate LinkedIn outreach/posts, or to install, configure, run, pause or check LinkedIn Autopilot.
---
# LinkedIn Autopilot
Installed at: $DIR
Open that folder, then read SKILL.md (what to do for each request) and AGENTS.md (the rules). To install or repair, follow AGENT-INSTALL.md.
Never enter the user's LinkedIn credentials and never switch outreach to live mode unless the user clearly asks.
"
reg() { mkdir -p "$1"; printf '%s\n' "$SKILL" > "$1/SKILL.md"; echo "Registered skill: $1"; }
{ [ "$AGENT" = claude ] || [ "$AGENT" = both ] || { [ "$AGENT" = auto ] && { command -v claude >/dev/null || [ -d "$H/.claude" ]; }; }; } && reg "$H/.claude/skills/linkedin-autopilot"
if { [ "$AGENT" = codex ] || [ "$AGENT" = both ] || { [ "$AGENT" = auto ] && { command -v codex >/dev/null || [ -d "$H/.codex" ]; }; }; }; then
  reg "$H/.codex/skills/linkedin-autopilot"
  if ! grep -q '^\[mcp_servers\.linkedin\]' "$H/.codex/config.toml" 2>/dev/null; then
    mkdir -p "$H/.codex"; printf '\n[mcp_servers.linkedin]\ncommand = "uvx"\nargs = ["--python", "3.12", "mcp-server-linkedin"]\nenv = { UV_HTTP_TIMEOUT = "300" }\nstartup_timeout_sec = 180\ntool_timeout_sec = 300\n' >> "$H/.codex/config.toml"
  fi
fi

echo "== 4/4 Done"
echo "Installed in: $DIR"
echo "It starts in TEST mode and sends nothing until you turn it on. Open the dashboard any time with:  $DIR/START.command"
[ "$LAUNCH" = 1 ] && exec bash "$DIR/START.command"
