# Installing LinkedIn Autopilot (instructions for an AI agent)

You are an AI agent (Claude Code, Codex, or similar) asked to install this package for a user. Follow these steps in order. Run commands yourself; only the items marked **USER** must be done by the human.
Package folder = the folder containing this file. Call it `$PKG`.

## 0. Tell the user, before anything else
Say this in one short message and continue unless they object:
> LinkedIn's terms prohibit automated messaging, so the account can be restricted even with the safety limits built in. The tool starts in test mode and sends nothing until you explicitly turn it on.

## 1. Check the machine
- Windows 10/11 (PowerShell 5.1+), macOS, or Linux. Internet access is required.
- Check `uv --version`. If missing: Windows `powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"`; Mac/Linux `curl -LsSf https://astral.sh/uv/install.sh | sh`. Then add `~/.local/bin` to PATH for this session.
- Check that one agent CLI exists: `claude --version` or `codex --version`. If none: Claude Code is `irm https://claude.ai/install.ps1 | iex` (Windows) or `curl -fsSL https://claude.ai/install.sh | bash`. It needs the user's own paid Claude plan. **USER** signs in (`claude`, then `/login`).

## 2. Put the package in its permanent place
Preferred: run the installer, which copies the package to `~/linkedin-autopilot` (keeps `config.yaml` and `data/` on updates), registers the skill for the agents found and creates a desktop shortcut:
- Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File "$PKG\install.ps1" -Yes -NoLaunch`
- Mac/Linux: `bash "$PKG/install.sh" --yes --no-launch`

Add `-Agent claude|codex|both` (`--agent`) to choose which agent to register (default: every agent CLI found).
Other agents: nothing to register. Point them at `SKILL.md` / `AGENTS.md` in the install folder.

## 3. Connect the LinkedIn server (MCP)
`.mcp.json` already declares the server `linkedin` (`uvx --python 3.12 mcp-server-linkedin`). Claude Code reads it. For Codex the installer adds `[mcp_servers.linkedin]` to `~/.codex/config.toml`. For any other MCP-capable agent, add:
`command: uvx`, `args: ["--python", "3.12", "mcp-server-linkedin"]`, `env: {UV_HTTP_TIMEOUT: "300"}`.

## 4. LinkedIn login. **USER**
Ask the user to run (or run it for them and let them act in the window that opens):
`uvx --python 3.12 mcp-server-linkedin --login`
They log in, approve on their phone if asked, and close the window. **Never type their credentials.** Verify later with the dashboard checklist or the `get_session_status` tool.

## 5. Configure
Either open the dashboard (`START.bat` / `./START.command`) and let the user fill the **Settings** forms, or run the `setup` routine in `prompts/setup.md` yourself (interview, then edit `config.yaml`). Keep `outreach.mode: "dry_run"`.

## 6. Schedule
Windows: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\setup.ps1 -ScheduleOnly`. Mac/Linux: `bash scripts/setup.sh` (installs cron entries). This creates the daily runs. They do nothing in dry-run mode.

## 7. Verify (do all, report results honestly)
1. `uv run tools/guard.py check dm` returns JSON with `"ok": true` and `"mode": "dry_run"`.
2. Dry-run: `powershell -File scripts\run.ps1 -Task outreach -Force` (or `bash scripts/run.sh outreach`). When it finishes, `data/leads.csv` has leads and `data/activity_log.csv` has drafts with `mode=dry_run`. Nothing was sent.
3. Show the user 2–3 of the drafted messages and ask if the tone is right. Adjust `outreach.message_style` if not.

## 8. Going live. **USER decides**
Only if the user clearly says to start sending: set `outreach.mode: "live"` in `config.yaml` (or the dashboard button), and remind them that the first 7 days run at half the limits.

## Daily operation
Runs happen by themselves. The user checks `data/hot_leads.md` (people who replied) and answers those personally. `data/STOP` pauses everything. Problems show up in `data/ALERT.txt` and on the dashboard.

## If something fails
`data/ui.log` (dashboard), `data/runs/*.log` (each run), `data/ALERT.txt` (last problem). Never retry past a CAPTCHA or restriction warning: stop and tell the user.
