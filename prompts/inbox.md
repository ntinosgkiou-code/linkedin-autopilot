# Routine: inbox (unattended, once a day)

Goal: react to replies, catch accepted invites, send due follow-ups, and write the daily report.

## 1. Pre-flight
Same as outreach step 0.1–0.3 (read config, check that the session is logged in). If `data/STOP` exists, the guard reports it. Then only write the report and end the run.

## 2. Replies
1. `get_inbox` (and `get_conversation` for unread threads).
2. For every thread whose other person is in `data/leads.csv` (match by profile URL or name, using `guard.py seen`):
   - Classify the last message from them:
     - **interested** (asks for details, price, call, says yes):
       `lead-set <url> --status interested --note "<one-line summary>"`. Append to `data/hot_leads.md` a
       dated entry with name, URL, what they said, and a suggested next reply. In live mode, if they asked a
       direct question you can answer from `config.yaml` (`offer.price`, `offer.faq`, `offer.what`), reply once (answer, then propose `offer.cta`) (`reply_to_conversation`, after `guard.py check dm`),
       and you may include `offer.link`. Never invent prices or terms that are not in config.
     - **question / neutral**: `lead-set --status replied`. Add it to `data/hot_leads.md` for the human. Do not auto-reply.
     - **not interested / stop / hostile**: `guard.py block <url>`. Do not reply.
   - Every reply stops the follow-up sequence for that lead.

## 3. Accepted invites
`guard.py lead-list --status invited`. For each lead (cap: 25 profile checks, each with `check view` and `log view` first),
check `get_person_profile`. If they are now 1st-degree, run `lead-set <url> --status connected --degree 1`.
The next outreach run messages them.

## 4. Follow-ups
If `outreach.followups` > 0: `guard.py lead-list --due-followup`. For each lead:
- Re-check the conversation. If they replied, handle it as in step 2 and skip the follow-up.
- `guard.py check dm`. Write a 1–2 line follow-up that adds new value.
- live: `reply_to_conversation` (or `send_message`). dry_run: do not send.
- `guard.py log followup <url> --detail "<text>"` → `lead-set <url> --status followed_up --contacted` → `guard.py delay`.

## 5. Report
`uv run tools/guard.py report` writes `data/reports/<date>.md`. Then follow "End of every run" in AGENTS.md.
