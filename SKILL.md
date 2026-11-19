---
name: linkedin-autopilot
description: Runs a user's LinkedIn on autopilot, locally. Finds leads that match the user's filters, writes personalized connection notes and DMs, sends them within safe daily limits, writes posts, reads replies and reports. Use when the user asks to automate LinkedIn outreach, posts or lead generation, or to install, configure, run, pause or check "LinkedIn Autopilot".
---

# LinkedIn Autopilot (agent skill)

A local, agent-driven LinkedIn workflow. The folder this file sits in is the whole product: rules, routines, a safety guard and a dashboard.
It works with any agent that can read files and run shell commands (Claude Code, Codex, and others). The rules live in `AGENTS.md` (Claude reads `CLAUDE.md`, which includes it).

## Decide what the user wants

| The user says | You do |
|---|---|
| "install / set up LinkedIn Autopilot" | Follow `AGENT-INSTALL.md` exactly. |
| `setup`, "configure it", "change my target customers" | Run the routine in `prompts/setup.md` (interview the user, fill `config.yaml`). |
| `outreach` / `inbox` / `post` | Run the routine in `prompts/<name>.md`, following `AGENTS.md`. |
| `status`, "how is it going" | `uv run tools/guard.py report` and summarize; also read `data/hot_leads.md`. |
| "pause" / "resume" | Create / delete `data/STOP`. |
| "open the dashboard" | Run `START.bat` (Windows) or `./START.command` (Mac/Linux). |

## Non-negotiable rules (full list in `AGENTS.md`)
1. **Never type the user's LinkedIn password or any credential.** The user logs in themselves (`uvx mcp-server-linkedin --login`).
2. **Never switch `outreach.mode` to `live` on your own.** Only when the user clearly asks, after they saw dry-run results.
3. Every action goes through `tools/guard.py` first (`check`, then `log`). Obey `ok:false` and `data/STOP` immediately.
4. Stop and run `guard.py stop "<reason>"` on any CAPTCHA, security check or restriction warning.
5. Be honest: LinkedIn's terms prohibit automation of messaging. Say so when installing and when going live.

## Layout
`config.yaml` the user's settings · `AGENTS.md` operating manual · `prompts/` the 4 routines · `tools/guard.py` limits, kill switch, lead database · `tools/linkedin_post.py` official-API publishing · `ui/` local dashboard · `scripts/` scheduler and runners · `data/` everything produced (leads, log, posts, reports).
