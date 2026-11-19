# Routine: orders (the user's own instructions)

The user types instructions in their own words (in the dashboard tab "Εντολές", or by telling you in chat).
Each is an "order". Orders have priority over automatic prospecting, but they obey **every** hard rule in AGENTS.md and the same daily limits.

## 0. Pre-flight
1. Read `config.yaml`. Run `uv run tools/guard.py order-list`. If there are no pending orders, end the run.
2. `get_session_status` on the `linkedin` server. If not logged in, run `guard.py stop "LinkedIn session expired. Run: uvx --python 3.12 mcp-server-linkedin --login"` and end the run.

## 1. For each pending order, oldest first
Read the text and decide which kind it is. It can be in Greek or English.

**A. Specific people** (LinkedIn links, or a name plus company), with or without a note about what to say.
For each person:
1. `guard.py seen <url>`. If blocked: `order-done ID --status skipped --result "blocked: said no before"`.
   If contacted before: do not write a first message again. Skip with the reason.
   If you only have a name, use `search_people` and pick the clear match. If it is ambiguous, skip with `--result "which one? <candidates>"`. Never guess.
2. `guard.py check view`, then `get_person_profile`, then `guard.py log view <url>`.
3. Add them to the lead list if missing (`lead-add`, score what you see, `hook` = the user's reason or a real detail from the profile).
4. Write the message following the user's note (angle, topic, tone, offer) and the writing style in AGENTS.md.
   If the note and the rules conflict (a fake claim, a link in the first message, sensitive targeting), follow the rules and say so in the result.
5. If already a 1st-degree connection: `guard.py check dm`, then (live) `send_message`, then `log dm` and `lead-set --status messaged --contacted`.
   Otherwise: `guard.py check invite`, then (live) `connect_with_person` with a note of at most 200 characters, then `log invite` and `lead-set --status invited --contacted`.
6. dry_run: send nothing. Write the exact text, log it (the guard marks it dry_run).
7. `guard.py delay` after every real send.

**B. Find leads** ("find 10 dentists in Thessaloniki who ...").
Use the user's words as the search, instead of `targeting` for this order. Follow step 1 of `prompts/outreach.md` (view check, profile, score, `lead-add` with a real `hook`).
Add as many as the user asked for (default 10), at most. Do not message them unless the order says to ("and message them"). If it does, treat each as kind A.

**C. Anything else** about the account (a question, a status, "pause", "stop writing to X").
Do what is safe and possible within the rules. For "stop writing to X" use `guard.py block <url>`. If you cannot, say why in the result.

## 2. Close each order
- Sent / added: `guard.py order-done ID --status done --result "<what you did, one or two lines, with the exact message text>"`.
- dry_run (nothing sent): `--status drafted --result "<the exact text you would send>"`.
- Could not do it: `--status failed --result "<why>"`.
Never leave an order pending after you handled it. If you ran out of today's limit, leave it pending and say so in the run summary.

## 3. Finish
Follow "End of every run" in AGENTS.md.
