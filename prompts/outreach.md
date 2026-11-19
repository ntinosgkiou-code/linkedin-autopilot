# Routine: outreach (unattended)

Goal: keep a pipeline of well-fitting leads, and send this run's share of invites and DMs within the limits.

## 0. Pre-flight
1. Read `config.yaml`. If `outreach.enabled` is false, end the run.
2. Run `uv run tools/guard.py check dm` and `uv run tools/guard.py check invite`. If both are `ok:false`, report the reason and end the run.
3. Call `get_session_status` on the `linkedin` server. If it is not logged in, run `guard.py stop "LinkedIn session expired. Run: uvx --python 3.12 mcp-server-linkedin --login"` and end the run.
4. Run `uv run tools/guard.py batch dm` and `uv run tools/guard.py batch invite`. The numbers it returns are this run's maximums. Call them `DM_N` and `INV_N`.

## 1. Make sure the pipeline has leads (do this FIRST)
Count `lead-list --status new` + `lead-list --status connected`. If that is fewer than `2 × (INV_N + DM_N)`, prospect:
1. Build searches from `targeting`: combine `keywords`, `titles` and `locations`, and use
   `industries` / `company_size` where `search_people` accepts them. Rotate the combinations between runs, so they are not identical every time.
2. For each result: skip it if `exclude_keywords` matches, or if `guard.py seen <url>` says contacted or blocked.
3. For promising results, check `guard.py check view`, then run `get_person_profile` and `guard.py log view <url>`.
4. Score the fit from 1 to 10 against `targeting.ideal_customer` (role, company, signals, activity).
   Write a `hook`: one concrete, verifiable detail you would mention (a recent post, a company milestone, a specific service).
5. If the score is at least `targeting.min_fit_score`, run `guard.py lead-add --url .. --name .. --headline .. --company .. --location .. --score N --hook ".." --degree <1|2|3>`.
   If the person is already a 1st-degree connection, use `--degree 1`, then run `lead-set <url> --status connected`.
6. Stop prospecting once you have added `2 × (INV_N + DM_N)` leads, or when `check view` returns not ok.

## 2. Messages to connections (spend DM_N)
This includes 1st-degree leads you found in step 1 this run.
1. `uv run tools/guard.py lead-list --status connected --limit DM_N`.
2. For each lead:
   - `guard.py check dm`. Stop this step if it returns not ok.
   - `get_person_profile` (after `guard.py check view` returns ok, then `guard.py log view <url>`). Also check their recent activity if it is shown.
   - Write the first DM using the rules in AGENTS.md, `offer`, and the lead's `hook`.
   - live: `send_message`. dry_run: do not send.
   - `guard.py log dm <url> --detail "<exact text>"` then `guard.py lead-set <url> --status messaged --contacted`.
   - `guard.py delay`.

## 3. Connection requests (spend INV_N)
1. `guard.py lead-list --status new --limit INV_N` (highest fit first).
2. For each lead:
   - `guard.py check invite`. Stop if not ok.
   - If `outreach.connect_note` is true, write a note of at most 200 characters with no pitch, based on the hook.
   - live: `connect_with_person` with the note. dry_run: do not send.
   - `guard.py log invite <url> --detail "<note>"` then `guard.py lead-set <url> --status invited --contacted`.
   - `guard.py delay`.

## 4. Finish
Follow "End of every run" in AGENTS.md.
