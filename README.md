# LinkedIn Autopilot

> **Not technical?** Double-click **`START.bat`** (Mac: `START.command`). A dashboard opens in your browser with a checklist, settings forms, test and go-live buttons, replies and a pause button. No commands needed. The step-by-step guide is `START-HERE-GUIDE.html` (Greek). The `1-4 .bat` files are the older command-line route and still work.

## Install (pick one)

**A. From the unzipped folder, in PowerShell or cmd (Windows):**
```
powershell -ExecutionPolicy Bypass -File install.ps1
```
Mac/Linux: `bash install.sh`. It copies the program to `~/linkedin-autopilot`, installs `uv`, registers the skill for Claude Code / Codex, adds a desktop icon and opens the dashboard. Run it again any time to update: your settings and data are kept.

**B. One line from a download link** (works for anyone, nothing to host):
```
powershell -ExecutionPolicy Bypass -Command "& ([scriptblock]::Create((irm https://raw.githubusercontent.com/ntinosgkiou-code/linkedin-autopilot/main/install.ps1))) -Url https://github.com/ntinosgkiou-code/linkedin-autopilot/archive/refs/heads/main.zip"
```

**C. Let your AI agent install it.** Open any agent (Claude Code, Codex, Cursor, ...) and say:
> Install LinkedIn Autopilot: read `AGENT-INSTALL.md` in this folder and follow it. Stop where it says the user must act.

**D. Just double-click `START.bat`.** The dashboard guides you through the rest.

How it works, what changed and what it cannot promise: see `HOW-IT-WORKS.md` (Greek).

---

An AI agent (Claude Code or Codex) that runs your LinkedIn on autopilot, every work day:

- **Writes and publishes posts** in your voice, on your topics and days.
- **Finds leads** that match your ideal-customer filters and scores each one 1–10.
- **Sends personalized connection requests and DMs.** Each message is based on the person's profile or posts, never a template.
- **Reads replies.** Interested leads go to `data/hot_leads.md`. People who say "no" are blocked forever.
- **Sends follow-ups** and writes a **daily report**.
- **Safety built in.** Daily and weekly limits, a 7-day warm-up, human-like delays, work hours only, and a kill switch that stops everything at the first warning from LinkedIn.

---

## ⚠️ Read this first

DMs and invites are sent by automating **your own logged-in browser** with the open-source
[`mcp-server-linkedin`](https://github.com/stickerdaniel/linkedin-mcp-server).
**LinkedIn's User Agreement does not allow automation tools, and accounts can be restricted.**
The limits in `config.yaml` lower the risk. They do not remove it. You use this at your own risk.
Posts use LinkedIn's **official API**, which is allowed.

You are responsible for your messages. In the EU/UK (GDPR), cold B2B outreach has to be relevant
to the person's job, and you must stop when someone says no. The agent does that automatically.

---

## Setup in 5 steps

**1. Install an AI agent.** Install either one and sign in:
[Claude Code](https://claude.com/claude-code) (`npm install -g @anthropic-ai/claude-code`, then `claude`) or
[Codex](https://developers.openai.com/codex) (`npm install -g @openai/codex`, then `codex`).

**2. Unzip this folder** anywhere you like, e.g. `Documents\linkedin-autopilot`.

**3. Tell it about you.** Open a terminal in the folder, start `claude` (or `codex`), and type:
```
setup
```
It asks you a few questions (your offer, your ideal customer, your post topics and tone), fills in `config.yaml`, and shows you sample DMs and a sample post to approve.
*(If you prefer, you can edit `config.yaml` by hand instead.)*

**4. Run the installer.** It installs `uv`, opens LinkedIn so **you** can log in, and schedules everything.
- Windows: `powershell -ExecutionPolicy Bypass -File scripts\setup.ps1`
- Mac/Linux: `bash scripts/setup.sh`

**5. Test, then go live.**
- Windows: `powershell -ExecutionPolicy Bypass -File scripts\run.ps1 -Task outreach`
- Mac/Linux: `bash scripts/run.sh outreach`

It starts in **dry run**: it finds real leads and writes real messages, but **sends nothing**.
Check `data/activity_log.csv` (what it would send) and `data/leads.csv` (who it found).
When you like what you see, set `mode: "live"` in `config.yaml`. From then on it runs by itself.

---

## Daily schedule (default, editable in `config.yaml`, then re-run step 4)

| Time (Mon–Fri) | Routine | What it does |
|---|---|---|
| 08:30 Tue/Thu | `post` | Writes and publishes one post |
| 09:30 · 11:30 · 14:30 · 16:30 | `outreach` | Finds leads, sends a share of the day's invites and DMs |
| 17:30 | `inbox` | Replies, accepted invites, follow-ups, daily report |

Your computer must be on, and on Windows you must be logged in. Each run takes 5–30 minutes.

## Where to look

| File | What's in it |
|---|---|
| `data/hot_leads.md` | **People who replied.** Check it daily. |
| `data/reports/<date>.md` | Daily numbers, reply rate, acceptance rate, warnings |
| `data/leads.csv` | Every lead with fit score, hook and status |
| `data/activity_log.csv` | Every invite and DM, with the exact text |
| `data/posts/` | Every post written |
| `data/runs/` | Full agent log of each run |

## Controls

- **Pause everything:** create an empty file `data/STOP`. The agent also creates it itself if LinkedIn shows a warning. To resume, delete it.
- **Run something now:** `scripts\run.ps1 -Task outreach|inbox|post` (or `scripts/run.sh <task>`).
- **Ask for status:** open `claude`/`codex` in the folder and type `status`.
- **Uninstall:** `scripts\uninstall.ps1` (Windows), or the command printed at the end of `setup.sh`.

## Safety limits (default)

| | Default | Hard cap (cannot be raised) |
|---|---|---|
| DMs + follow-ups per day | 20 | 40 |
| Connection requests per day | 15 | 25 |
| Connection requests per week | 80 | 100 |
| Profile views per day | 60 | 150 |
| First 7 days | half of the above | |
| Delay between actions | 60–150 s, random | |

The report warns you when the reply rate drops below 5% or the acceptance rate below 25%. Those
numbers hurt your account more than volume does. Fix the targeting or the message before you send more.

## Auto-publishing posts (optional, one time, about 5 minutes)

Without this, posts are saved to `data/posts/` for you to copy and paste.
1. Go to <https://www.linkedin.com/developers/apps> → **Create app**. LinkedIn requires a Company Page.
   Any page you admin works, or create one for free in a minute.
2. **Products** tab → request **"Share on LinkedIn"** and **"Sign In with LinkedIn using OpenID Connect"**. Both are instant.
3. **Auth** tab → under *Authorized redirect URLs* add `http://localhost:8765/callback`.
   Copy the **Client ID** and **Client Secret**.
4. Run `uv run tools/linkedin_post.py auth`, paste them in, and approve in the browser.
   The token lasts 60 days. The agent notes in `hot_leads.md` when it needs renewing.

## Troubleshooting

- **"LinkedIn session expired"** in a report → run `uvx mcp-server-linkedin --login`, then delete `data/STOP`.
- **Windows: `DLL load failed ... _greenlet`** → install the [Microsoft Visual C++ Redistributable](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist).
- **Nothing happens at the scheduled time** → Windows: open Task Scheduler → `LinkedInAutopilot` and check *Last Run Result*. Mac: check `crontab -l`.
- **Codex runs can't reach LinkedIn** → in `scripts/run.ps1` / `run.sh`, replace `--full-auto` with `--dangerously-bypass-approvals-and-sandbox`. Only do this in this folder.
