# /// script
# requires-python = ">=3.10"
# dependencies = ["tzdata"]
# ///
"""LinkedIn Autopilot guard: safety limits, kill switch, lead database, activity log.

Every command prints JSON so an AI agent can read it. Run with:  uv run tools/guard.py <command>
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG = ROOT / "config.yaml"
LEADS = DATA / "leads.csv"
LOG = DATA / "activity_log.csv"
BLOCK = DATA / "blocklist.txt"
STOP = DATA / "STOP"
REPORTS = DATA / "reports"

LEAD_FIELDS = ["linkedin_url", "name", "headline", "company", "location", "fit_score", "hook",
               "status", "degree", "added", "last_contact", "followups", "notes"]
LOG_FIELDS = ["timestamp", "action", "target", "mode", "detail"]
STATUSES = ["new", "invited", "connected", "messaged", "followed_up", "replied",
            "interested", "not_interested", "skipped"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

DEFAULTS = {
    "outreach": {"enabled": True, "mode": "dry_run", "followups": 1, "followup_after_days": 4},
    "posts": {"enabled": True, "approval": "draft", "days": ["Tue", "Thu"], "time": "08:30"},
    "limits": {"dms_per_day": 20, "invites_per_day": 15, "invites_per_week": 80,
               "profile_views_per_day": 60, "warmup_days": 7, "min_delay_seconds": 60,
               "max_delay_seconds": 150, "work_hours": "09:00-18:00",
               "work_days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "timezone": "Europe/Athens"},
    "schedule": {"outreach_runs": ["09:30", "11:30", "14:30", "16:30"], "inbox_run": "17:30"},
}
HARD_CAPS = {"dms_per_day": 40, "invites_per_day": 25, "invites_per_week": 100, "profile_views_per_day": 150}


# ---------------------------------------------------------------- config (tiny YAML subset)
def _strip_comment(s: str) -> str:
    in_q = False
    for i, ch in enumerate(s):
        if ch == '"':
            in_q = not in_q
        elif ch == "#" and not in_q and (i == 0 or s[i - 1] in " \t"):
            return s[:i]
    return s


def _value(raw: str):
    raw = raw.strip()
    if raw == "":
        return ""
    if raw[0] in '["':
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw.strip('"')
    low = raw.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    try:
        return int(raw)
    except ValueError:
        return raw


def load_config() -> dict:
    cfg: dict = {k: dict(v) for k, v in DEFAULTS.items()}
    if not CONFIG.exists():
        return cfg
    section = None
    for line in CONFIG.read_text(encoding="utf-8-sig").splitlines():
        line = _strip_comment(line).rstrip()
        if not line.strip() or ":" not in line:
            continue
        indented = line[0] in " \t"
        key, _, val = line.strip().partition(":")
        if not indented:
            if val.strip() == "":
                section = key
                cfg.setdefault(section, {})
            else:
                cfg[key] = _value(val)
                section = None
        elif section:
            cfg[section][key] = _value(val)
    for k, cap in HARD_CAPS.items():
        try:
            cfg["limits"][k] = min(int(cfg["limits"][k]), cap)
        except (KeyError, ValueError, TypeError):
            cfg["limits"][k] = DEFAULTS["limits"].get(k, 0)
    return cfg


def now(cfg) -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(cfg["limits"].get("timezone", "Europe/Athens"))).replace(tzinfo=None)
    except Exception:
        return datetime.now()


def mode(cfg) -> str:
    return "live" if str(cfg["outreach"].get("mode", "dry_run")).lower() == "live" else "dry_run"


# ---------------------------------------------------------------- csv helpers
def norm_url(url: str) -> str:
    u = (url or "").strip().split("?")[0].split("#")[0].rstrip("/")
    if "linkedin.com/" in u:
        u = "https://www.linkedin.com/" + u.split("linkedin.com/", 1)[1]
    return u.lower()


def read_csv(path: Path, fields: list[str]) -> list[dict]:
    for attempt in range(5):
        try:
            if not path.exists():
                return []
            with path.open(encoding="utf-8-sig", newline="") as f:
                return [{k: (r.get(k) or "") for k in fields} for r in csv.DictReader(f)]
        except (PermissionError, OSError):
            time.sleep(0.1 * (attempt + 1))
    return []


def _replace_retry(tmp: Path, path: Path) -> None:
    for i in range(40):
        try:
            tmp.replace(path)
            return
        except PermissionError:  # Windows: another process is reading the file for a moment
            time.sleep(0.05 * (i + 1) if i < 10 else 0.5)
    tmp.replace(path)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    _replace_retry(tmp, path)


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    _replace_retry(tmp, path)


def append_log(action: str, target: str, md: str, detail: str, cfg) -> None:
    rows = read_csv(LOG, LOG_FIELDS)
    rows.append({"timestamp": now(cfg).strftime("%Y-%m-%d %H:%M:%S"), "action": action,
                 "target": target, "mode": md, "detail": detail.replace("\n", " ")[:1000]})
    write_csv(LOG, LOG_FIELDS, rows)


def blocked() -> set[str]:
    if not BLOCK.exists():
        return set()
    return {norm_url(l) for l in BLOCK.read_text(encoding="utf-8").splitlines() if l.strip()}


def out(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1))


# ---------------------------------------------------------------- limits
ACTION_LIMIT = {"dm": "dms_per_day", "followup": "dms_per_day", "invite": "invites_per_day",
                "view": "profile_views_per_day"}


def counts(cfg, md: str, since: datetime, actions: tuple[str, ...]) -> int:
    n = 0
    for r in read_csv(LOG, LOG_FIELDS):
        if r["mode"] != md or r["action"] not in actions:
            continue
        try:
            if datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S") >= since:
                n += 1
        except ValueError:
            pass
    return n


def in_warmup(cfg) -> bool:
    live = [r for r in read_csv(LOG, LOG_FIELDS) if r["mode"] == "live" and r["action"] in ("dm", "invite", "followup")]
    if not live:
        return True
    first = datetime.strptime(live[0]["timestamp"], "%Y-%m-%d %H:%M:%S")
    return (now(cfg) - first).days < int(cfg["limits"].get("warmup_days", 7))


def remaining(cfg, action: str) -> tuple[int, str]:
    lim = cfg["limits"]
    md = mode(cfg)
    t = now(cfg)
    day_start = t.replace(hour=0, minute=0, second=0, microsecond=0)
    if action == "post":
        done = counts(cfg, md, day_start, ("post",))
        return (0, "already posted today") if done else (1, "")
    key = ACTION_LIMIT[action]
    daily = int(lim[key])
    if in_warmup(cfg) and action != "view":
        daily = max(1, daily // 2)
    group = ("dm", "followup") if action in ("dm", "followup") else (action,)
    left = daily - counts(cfg, md, day_start, group)
    reason = f"daily {key} reached" if left <= 0 else ""
    if action == "invite":
        week_left = int(lim["invites_per_week"]) - counts(cfg, md, t - timedelta(days=7), ("invite",))
        if week_left < left:
            left, reason = week_left, ("weekly invite limit reached" if week_left <= 0 else reason)
    return max(0, left), reason


def working_time(cfg) -> tuple[bool, str]:
    if os.environ.get("LA_FORCE") == "1":
        return True, ""
    lim = cfg["limits"]
    t = now(cfg)
    if DAYS[t.weekday()] not in lim.get("work_days", DAYS[:5]):
        return False, f"{DAYS[t.weekday()]} is not a work day"
    try:
        a, b = str(lim.get("work_hours", "09:00-18:00")).split("-")
        start = datetime.strptime(a.strip(), "%H:%M").time()
        end = datetime.strptime(b.strip(), "%H:%M").time()
        if not (start <= t.time() <= end):
            return False, f"outside work hours {a}-{b}"
    except ValueError:
        pass
    return True, ""


def cmd_check(a, cfg):
    if STOP.exists():
        return out({"ok": False, "reason": "KILL SWITCH: " + STOP.read_text(encoding="utf-8-sig").strip()
                    + " (delete data/STOP to resume)"})
    if a.action == "post":
        if not cfg["posts"].get("enabled", True):
            return out({"ok": False, "reason": "posts disabled in config"})
    else:
        if not cfg["outreach"].get("enabled", True):
            return out({"ok": False, "reason": "outreach disabled in config"})
        ok, why = working_time(cfg)
        if not ok:
            return out({"ok": False, "reason": why})
    left, why = remaining(cfg, a.action)
    out({"ok": left > 0, "remaining": left, "mode": mode(cfg), "warmup": in_warmup(cfg), "reason": why})


def cmd_batch(a, cfg):
    left, _ = remaining(cfg, a.action)
    t = now(cfg).strftime("%H:%M")
    later = [r for r in cfg["schedule"].get("outreach_runs", []) if str(r) > t]
    runs_left = 1 + len(later)  # this run + later runs today
    n = math.ceil(left / runs_left) if left > 0 else 0
    out({"action": a.action, "this_run": n, "remaining_today": left, "runs_left_today": runs_left})


def cmd_log(a, cfg):
    append_log(a.action, a.target, mode(cfg), a.detail or "", cfg)
    left, _ = remaining(cfg, a.action) if a.action in ACTION_LIMIT or a.action == "post" else (None, "")
    out({"logged": True, "mode": mode(cfg), "remaining": left})


def cmd_delay(a, cfg):
    lim = cfg["limits"]
    lo, hi = int(lim.get("min_delay_seconds", 60)), int(lim.get("max_delay_seconds", 150))
    s = random.randint(min(lo, hi), max(lo, hi))
    if a.seconds is not None:
        s = a.seconds
    time.sleep(s)
    out({"slept_seconds": s})


def cmd_stop(a, cfg):
    _atomic_write(STOP, f"{now(cfg):%Y-%m-%d %H:%M} {a.reason}\n")
    append_log("stop", "-", mode(cfg), a.reason, cfg)
    out({"stopped": True, "reason": a.reason})


def cmd_resume(a, cfg):
    existed = STOP.exists()
    STOP.unlink(missing_ok=True)
    out({"resumed": True, "was_stopped": existed})


# ---------------------------------------------------------------- leads
def cmd_seen(a, cfg):
    u = norm_url(a.url)
    lead = next((r for r in read_csv(LEADS, LEAD_FIELDS) if norm_url(r["linkedin_url"]) == u), None)
    contacted = any(norm_url(r["target"]) == u and r["action"] in ("dm", "invite", "followup") and r["mode"] == "live"
                    for r in read_csv(LOG, LOG_FIELDS))  # dry_run drafts do not count as contact
    out({"url": u, "blocked": u in blocked(), "contacted": contacted,
         "in_leads": bool(lead), "status": lead["status"] if lead else None})


def cmd_lead_add(a, cfg):
    u = norm_url(a.url)
    if "linkedin.com/in/" not in u:
        return out({"added": False, "reason": "not a linkedin.com/in/ profile url"})
    if u in blocked():
        return out({"added": False, "reason": "blocked"})
    rows = read_csv(LEADS, LEAD_FIELDS)
    if any(norm_url(r["linkedin_url"]) == u for r in rows):
        return out({"added": False, "reason": "duplicate"})
    rows.append({"linkedin_url": u, "name": a.name or "", "headline": a.headline or "", "company": a.company or "",
                 "location": a.location or "", "fit_score": str(a.score or ""), "hook": a.hook or "",
                 "status": "connected" if str(a.degree) == "1" else "new", "degree": str(a.degree or ""),
                 "added": now(cfg).strftime("%Y-%m-%d"), "last_contact": "", "followups": "0", "notes": ""})
    write_csv(LEADS, LEAD_FIELDS, rows)
    out({"added": True, "url": u, "status": rows[-1]["status"], "total_leads": len(rows)})


def cmd_lead_list(a, cfg):
    rows = read_csv(LEADS, LEAD_FIELDS)
    bl = blocked()
    rows = [r for r in rows if norm_url(r["linkedin_url"]) not in bl]
    if a.due_followup:
        max_f = int(cfg["outreach"].get("followups", 1))
        after = int(cfg["outreach"].get("followup_after_days", 4))
        cutoff = now(cfg) - timedelta(days=after)
        due = []
        for r in rows:
            if r["status"] not in ("messaged", "followed_up"):
                continue
            if int(r["followups"] or 0) >= max_f:
                continue
            try:
                if datetime.strptime(r["last_contact"], "%Y-%m-%d %H:%M") <= cutoff:
                    due.append(r)
            except ValueError:
                pass
        rows = due
    elif a.status:
        rows = [r for r in rows if r["status"] == a.status]
    rows.sort(key=lambda r: -int(r["fit_score"] or 0))
    if a.limit is not None:
        rows = rows[: a.limit]
    out({"count": len(rows), "leads": rows})


def cmd_lead_set(a, cfg):
    u = norm_url(a.url)
    rows = read_csv(LEADS, LEAD_FIELDS)
    hit = None
    for r in rows:
        if norm_url(r["linkedin_url"]) == u:
            hit = r
            if a.status and mode(cfg) == "dry_run" and a.status in ("invited", "messaged", "followed_up"):
                # Test mode: nothing was really sent, so the lead must stay untouched for the live run.
                r["notes"] = (r["notes"] + " | " if r["notes"] else "") + f"[dry_run: would be {a.status}]"
                write_csv(LEADS, LEAD_FIELDS, rows)
                return out({"updated": False, "dry_run": True, "reason": "dry_run: status kept so the live run still contacts this lead", "lead": r})
            if a.status:
                if a.status not in STATUSES:
                    return out({"updated": False, "reason": f"status must be one of {STATUSES}"})
                if a.status == "followed_up":
                    r["followups"] = str(int(r["followups"] or 0) + 1)
                r["status"] = a.status
            if a.degree is not None:
                r["degree"] = str(a.degree)
            if a.note:
                r["notes"] = (r["notes"] + " | " if r["notes"] else "") + a.note.replace("\n", " ")
            if a.contacted:
                r["last_contact"] = now(cfg).strftime("%Y-%m-%d %H:%M")
    if not hit:
        return out({"updated": False, "reason": "lead not found; add it with lead-add first"})
    write_csv(LEADS, LEAD_FIELDS, rows)
    out({"updated": True, "lead": hit})


# ---------------------------------------------------------------- orders (the user's own instructions to the agent)
ORDERS = DATA / "orders.json"


def load_orders() -> list[dict]:
    try:
        d = json.loads(ORDERS.read_text(encoding="utf-8-sig"))
        return [o for o in d if isinstance(o, dict) and "id" in o] if isinstance(d, list) else []
    except Exception:
        return []


def save_orders(items: list[dict]) -> None:
    _atomic_write(ORDERS, json.dumps(items[-200:], ensure_ascii=False, indent=1))


def add_order(text: str) -> dict:
    items = load_orders()
    o = {"id": max([int(x.get("id", 0)) for x in items] + [0]) + 1, "text": text.strip()[:2000], "status": "pending",
         "created": time.strftime("%Y-%m-%d %H:%M"), "result": ""}
    items.append(o)
    save_orders(items)
    return o


def cmd_order_add(a, cfg):
    out(add_order(a.text))


def cmd_order_list(a, cfg):
    items = load_orders()
    out({"orders": items if a.all else [o for o in items if o.get("status") == "pending"]})


def cmd_order_done(a, cfg):
    items = load_orders()
    hit = next((o for o in items if int(o.get("id", -1)) == a.id), None)
    if not hit:
        out({"ok": False, "error": "no such order"})
        return
    hit["status"] = a.status
    hit["result"] = (a.result or "")[:1500]
    save_orders(items)
    out({"ok": True, "order": hit})


def cmd_block(a, cfg):
    u = norm_url(a.url)
    bl = blocked()
    if u not in bl:
        with BLOCK.open("a", encoding="utf-8") as f:
            f.write(u + "\n")
    rows = read_csv(LEADS, LEAD_FIELDS)
    for r in rows:
        if norm_url(r["linkedin_url"]) == u:
            r["status"] = "not_interested"
    write_csv(LEADS, LEAD_FIELDS, rows)
    append_log("block", u, mode(cfg), a.reason or "", cfg)
    out({"blocked": True, "url": u})


# ---------------------------------------------------------------- report / schedule
def build_report(cfg, write: bool = True) -> dict:
    """Today's numbers as a dict. write=False for read-only callers (the dashboard polls this)."""
    t = now(cfg)
    day = t.replace(hour=0, minute=0, second=0, microsecond=0)
    md = mode(cfg)
    today = {k: counts(cfg, md, day, (k,)) for k in ("invite", "dm", "followup", "view", "post")}
    leads = read_csv(LEADS, LEAD_FIELDS)
    pipeline = {s: sum(1 for r in leads if r["status"] == s) for s in STATUSES}
    log = [r for r in read_csv(LOG, LOG_FIELDS) if r["mode"] == md]
    dm_urls = {norm_url(r["target"]) for r in log if r["action"] == "dm"}
    inv_urls = {norm_url(r["target"]) for r in log if r["action"] == "invite"}
    by_url = {norm_url(r["linkedin_url"]): r for r in leads}
    contacted = len(dm_urls)
    replied = sum(1 for u in dm_urls if by_url.get(u, {}).get("status") in ("replied", "interested", "not_interested"))
    invited_total = len(inv_urls)
    accepted = sum(1 for u in inv_urls if by_url.get(u, {}).get("degree") == "1")
    rep = {
        "date": t.strftime("%Y-%m-%d"), "mode": md, "warmup": in_warmup(cfg),
        "kill_switch": STOP.read_text(encoding="utf-8-sig").strip() if STOP.exists() else None,
        "today": today, "pipeline": pipeline,
        "reply_rate": f"{(replied / contacted * 100):.0f}%" if contacted else "n/a",
        "acceptance_rate": f"{(accepted / invited_total * 100):.0f}%" if invited_total else "n/a",
        "remaining_today": {k: remaining(cfg, k)[0] for k in ("dm", "invite", "view")},
    }
    warn = []
    if contacted >= 50 and replied / contacted < 0.05:
        warn.append("Reply rate under 5% after 50+ messages: change the message or the targeting.")
    if invited_total >= 50 and accepted / invited_total < 0.25:
        warn.append("Acceptance under 25%: targeting is too broad or the note is weak. LinkedIn penalizes low acceptance.")
    rep["warnings"] = warn
    if not write:
        return rep
    REPORTS.mkdir(parents=True, exist_ok=True)
    lines = [f"# LinkedIn Autopilot report {rep['date']} ({md}{', warm-up' if rep['warmup'] else ''})", ""]
    if rep["kill_switch"]:
        lines += [f"**STOPPED:** {rep['kill_switch']}. Delete `data/STOP` to resume.", ""]
    lines += ["## Today"] + [f"- {k}: {v}" for k, v in today.items()]
    lines += ["", "## Pipeline"] + [f"- {k}: {v}" for k, v in pipeline.items() if v]
    lines += ["", f"Reply rate: {rep['reply_rate']} | Acceptance: {rep['acceptance_rate']}"]
    if warn:
        lines += ["", "## Warnings"] + [f"- {w}" for w in warn]
    _atomic_write(REPORTS / f"{rep['date']}.md", "\n".join(lines) + "\n")
    return rep


def cmd_report(a, cfg):
    out(build_report(cfg, write=True))


def cmd_schedule(a, cfg):
    p, s, lim = cfg["posts"], cfg["schedule"], cfg["limits"]
    out({"outreach_runs": s.get("outreach_runs", []), "inbox_run": s.get("inbox_run", "17:30"),
         "work_days": lim.get("work_days", DAYS[:5]),
         "post_enabled": bool(p.get("enabled")), "post_days": p.get("days", []), "post_time": p.get("time", "08:30")})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("check"); s.add_argument("action", choices=["dm", "invite", "view", "post", "followup"])
    s = sub.add_parser("batch"); s.add_argument("action", choices=["dm", "invite"])
    s = sub.add_parser("log"); s.add_argument("action", choices=["dm", "invite", "view", "post", "followup", "note"])
    s.add_argument("target"); s.add_argument("--detail", default="")
    s = sub.add_parser("delay"); s.add_argument("--seconds", type=int)
    s = sub.add_parser("stop"); s.add_argument("reason")
    sub.add_parser("resume")
    s = sub.add_parser("seen"); s.add_argument("url")
    s = sub.add_parser("lead-add")
    for f in ("url", "name", "headline", "company", "location", "hook"):
        s.add_argument("--" + f, required=(f == "url"))
    s.add_argument("--score", type=int); s.add_argument("--degree", type=int)
    s = sub.add_parser("lead-list"); s.add_argument("--status", choices=STATUSES)
    s.add_argument("--limit", type=int); s.add_argument("--due-followup", action="store_true")
    s = sub.add_parser("lead-set"); s.add_argument("url"); s.add_argument("--status")
    s.add_argument("--note"); s.add_argument("--degree", type=int); s.add_argument("--contacted", action="store_true")
    s = sub.add_parser("block"); s.add_argument("url"); s.add_argument("--reason", default="")
    sub.add_parser("report")
    sub.add_parser("schedule")
    s = sub.add_parser("order-add"); s.add_argument("text")
    s = sub.add_parser("order-list"); s.add_argument("--all", action="store_true")
    s = sub.add_parser("order-done"); s.add_argument("id", type=int)
    s.add_argument("--status", choices=["done", "drafted", "failed", "skipped"], default="done"); s.add_argument("--result", default="")
    a = ap.parse_args()
    cfg = load_config()
    {"check": cmd_check, "batch": cmd_batch, "log": cmd_log, "delay": cmd_delay, "stop": cmd_stop,
     "resume": cmd_resume, "seen": cmd_seen, "lead-add": cmd_lead_add, "lead-list": cmd_lead_list,
     "lead-set": cmd_lead_set, "block": cmd_block, "report": cmd_report, "schedule": cmd_schedule,
     "order-add": cmd_order_add, "order-list": cmd_order_list, "order-done": cmd_order_done}[a.cmd](a, cfg)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
