# /// script
# requires-python = ">=3.10"
# dependencies = ["tzdata"]
# ///
"""LinkedIn Autopilot dashboard: a web page that runs ONLY on this computer (127.0.0.1).

Start it with START.bat (Windows) or START.command (Mac). Needs no coding.
Design rules: one bad request, a missing file or a slow Windows call must NEVER take the page down.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
import guard  # noqa: E402  (shares the exact same rules, limits and files as the agent)

WIN = os.name == "nt"
HOME = Path.home()
os.environ["PATH"] = os.pathsep.join([str(HOME / ".local" / "bin"), str(Path(os.environ.get("APPDATA", "")) / "npm"),
                                      "/opt/homebrew/bin", "/usr/local/bin", os.environ.get("PATH", "")])
APP_ID = "linkedin-autopilot-dashboard"
PORT = int(os.environ.get("LA_PORT", "8787"))
ALLOWED_HOSTS: set[str] = set()
JOB = {"proc": None, "task": None, "start": 0.0}
LOCKFILE = guard.DATA / ".runlock"
ALERT = guard.DATA / "ALERT.txt"

guard.DATA.mkdir(parents=True, exist_ok=True)
logging.basicConfig(filename=str(guard.DATA / "ui.log"), level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
log = logging.getLogger("ui")


# ------------------------------------------------------------------ tiny helpers
def safe(fn, default=None, what=""):
    """Run fn; on ANY error log it and return default. The dashboard must keep answering."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        log.warning("%s failed: %r", what or getattr(fn, "__name__", "?"), e)
        return default


_cache: dict[str, tuple[float, object]] = {}


def cached(key: str, ttl: float, fn, default=None):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = safe(fn, default, key)
    _cache[key] = (now, val)
    return val


def tail(path: Path, n=3000) -> str:
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        f.seek(max(0, size - n * 3))
        return f.read().decode("utf-8", errors="replace")[-n:]


# ------------------------------------------------------------------ config writing (keeps comments + layout)
def _comment_start(s: str) -> int:
    in_q = False
    for i, ch in enumerate(s):
        if ch == '"':
            in_q = not in_q
        elif ch == "#" and not in_q and (i == 0 or s[i - 1] in " \t"):
            return i
    return -1


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, list):
        return json.dumps([str(x) for x in v], ensure_ascii=False)
    return json.dumps(str(v).replace("\r", "").replace("\n", " ").strip(), ensure_ascii=False)


def _coerce(section: str, key: str, v, cur):
    ref = cur.get(section, {}).get(key, guard.DEFAULTS.get(section, {}).get(key))
    if isinstance(ref, bool):
        return bool(v) if not isinstance(v, str) else v.lower() in ("1", "true", "yes", "on")
    if isinstance(ref, int):
        try:
            n = int(v)
        except (TypeError, ValueError):
            return ref
        cap = guard.HARD_CAPS.get(key)
        return min(n, cap) if cap else n
    if isinstance(ref, list) or isinstance(v, list):
        if isinstance(v, str):
            v = re.split(r"[,\n]", v)
        return [str(x).strip() for x in v if str(x).strip()]
    return v


def write_config(updates: dict) -> None:
    cur = guard.load_config()
    lines = guard.CONFIG.read_text(encoding="utf-8-sig").splitlines()
    for section, kv in updates.items():
        for key, raw in kv.items():
            val = _fmt(_coerce(section, key, raw, cur))
            sec_idx, done = None, False
            for i, l in enumerate(lines):
                hdr = re.match(r"^([A-Za-z_]+):\s*(#.*)?$", l)  # section header, may carry a comment
                if hdr:
                    if sec_idx is not None:
                        break  # reached the next section without finding the key
                    if hdr.group(1) == section:
                        sec_idx = i
                    continue
                m = re.match(rf"^(\s+){re.escape(key)}:\s*(.*)$", l) if sec_idx is not None else None
                if m:
                    c = _comment_start(m.group(2))
                    comment = m.group(2)[c:] if c >= 0 else ""
                    base = f"{m.group(1)}{key}: {val}"
                    col = l.index(comment) if comment else 0
                    lines[i] = (base.ljust(max(col, len(base) + 2)) + comment) if comment else base
                    done = True
                    break
            if not done and sec_idx is not None:
                lines.insert(sec_idx + 1, f"  {key}: {val}")
    guard._atomic_write(guard.CONFIG, "\n".join(lines) + "\n")
    _cache.clear()


# ------------------------------------------------------------------ state (every piece is independent and fail-safe)
def which(c: str) -> bool:
    return shutil.which(c) is not None


def claude_logged_in() -> bool:
    return bool(json.loads((HOME / ".claude.json").read_text(encoding="utf-8")).get("oauthAccount"))


def schedule_installed() -> bool:
    if WIN:
        r = subprocess.run(["schtasks", "/query", "/tn", "\\LinkedInAutopilot\\Outreach"], capture_output=True, timeout=10)
        return r.returncode == 0
    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=10)
    return "linkedin-autopilot" in r.stdout


def linkedin_logged_in() -> bool:
    p = HOME / ".linkedin-mcp" / "profile"
    return p.exists() and any(p.iterdir())


def lock_info() -> dict | None:
    """A scheduled/manual run holds data/.runlock. Ignore locks older than 2 h (a crash must never block forever)."""
    try:
        d = json.loads(LOCKFILE.read_text(encoding="utf-8-sig"))
        if time.time() - float(d.get("start", 0)) < 7200:
            return d
    except Exception:  # noqa: BLE001
        pass
    return None


def job_state() -> dict:
    p = JOB["proc"]
    mine = bool(p and p.poll() is None)
    lock = lock_info()
    running = mine or bool(lock)
    task = JOB["task"] if mine else (lock or {}).get("task")
    since = int(time.time() - (JOB["start"] if mine else float((lock or {}).get("start", time.time())))) if running else None
    return {"running": running, "task": task, "since": since, "scheduled": bool(lock) and not mine}


def newest_logs(n=6):
    d = guard.DATA / "runs"
    if not d.exists():
        return []
    files = sorted(d.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)[:n]
    return [{"name": f.name, "tail": tail(f)} for f in files]


def read_posts():
    pd = guard.DATA / "posts"
    if not pd.exists():
        return []
    return [{"name": f.name, "text": f.read_text(encoding="utf-8", errors="replace")}
            for f in sorted(pd.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)[:30]]


def state() -> dict:
    cfg = safe(guard.load_config, None, "config") or {k: dict(v) for k, v in guard.DEFAULTS.items()}
    for k, v in guard.DEFAULTS.items():  # a missing section must never crash the page
        cfg.setdefault(k, dict(v))
    cfg.setdefault("profile", {}); cfg.setdefault("offer", {}); cfg.setdefault("targeting", {})
    report = safe(lambda: guard.build_report(cfg, write=False), None, "report") or {
        "date": "", "mode": cfg["outreach"].get("mode", "dry_run"), "warmup": True, "kill_switch": None,
        "today": {k: 0 for k in ("invite", "dm", "followup", "view", "post")}, "pipeline": {}, "warnings": [],
        "reply_rate": "n/a", "acceptance_rate": "n/a", "remaining_today": {"dm": 0, "invite": 0, "view": 0}}
    hot = guard.DATA / "hot_leads.md"
    configured = cfg["profile"].get("name") not in ("", "Your Name", None) and not str(cfg["offer"].get("what", "")).startswith("What you sell")
    return {
        "orders": list(reversed(safe(guard.load_orders, [], "orders")))[:50],
        "cfg": cfg, "report": report, "job": safe(job_state, {"running": False}, "job"),
        "stop": safe(lambda: guard.STOP.read_text(encoding="utf-8-sig").strip() if guard.STOP.exists() else None, None, "stop"),
        "alert": safe(lambda: ALERT.read_text(encoding="utf-8-sig").strip() if ALERT.exists() else None, None, "alert"),
        "hot": safe(lambda: hot.read_text(encoding="utf-8-sig") if hot.exists() else "", "", "hot"),
        "leads": safe(lambda: guard.read_csv(guard.LEADS, guard.LEAD_FIELDS), [], "leads"),
        "log": safe(lambda: list(reversed(guard.read_csv(guard.LOG, guard.LOG_FIELDS)))[:150], [], "log"),
        "posts": safe(read_posts, [], "posts"), "runs": safe(newest_logs, [], "runs"),
        "checks": {"windows": WIN, "uv": which("uv"), "claude": which("claude"),
                   "claude_login": bool(safe(claude_logged_in, False, "claude_login")),
                   "linkedin": bool(safe(linkedin_logged_in, False, "linkedin")), "configured": configured,
                   "schedule": bool(cached("schedule", 20, schedule_installed, False)),
                   "post_api": (guard.DATA / ".secrets" / "linkedin.json").exists()},
    }


# ------------------------------------------------------------------ actions
def console(cmd: str) -> bool:
    if WIN:
        subprocess.Popen(f'start "LinkedIn Autopilot" cmd /k {cmd}', shell=True, cwd=str(ROOT))
        return True
    return False


def install_schedule() -> dict:
    _cache.pop("schedule", None)
    if WIN:
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "setup.ps1"),
                            "-ScheduleOnly"], capture_output=True, text=True, timeout=180, cwd=str(ROOT))
        return {"ok": r.returncode == 0, "message": "Το πρόγραμμα της ημέρας αποθηκεύτηκε." if r.returncode == 0
                else "Αποτυχία προγραμματισμού: " + (r.stderr or r.stdout)[-400:]}
    return {"ok": False, "message": "Σε Mac/Linux τρέξε στο Terminal:  bash scripts/setup.sh"}


def start_job(task: str) -> dict:
    if job_state()["running"]:
        return {"ok": False, "message": "Τρέχει ήδη μια εκτέλεση. Περίμενε να τελειώσει."}
    env = dict(os.environ, LA_FORCE="1")
    if WIN:
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "run.ps1"), "-Task", task, "-Force"]
    else:
        cmd = ["bash", str(ROOT / "scripts" / "run.sh"), task]
    JOB.update(proc=subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL), task=task, start=time.time())
    return {"ok": True, "message": f"Ξεκίνησε η εκτέλεση «{task}». Θέλει 5–20 λεπτά, μπορείς να κλείσεις τη σελίδα."}


PRESETS = {"gentle": dict(dms_per_day=10, invites_per_day=8, invites_per_week=40),
           "normal": dict(dms_per_day=20, invites_per_day=15, invites_per_week=80),
           "max": dict(dms_per_day=30, invites_per_day=20, invites_per_week=100)}


def action(a: dict) -> dict:
    t = a.get("do")
    if t == "mode":
        m = "live" if a.get("value") == "live" else "dry_run"
        write_config({"outreach": {"mode": m}})
        return {"ok": True, "message": "ΖΩΝΤΑΝΗ λειτουργία: στέλνει πραγματικά μηνύματα." if m == "live" else "Δοκιμαστική λειτουργία: δεν στέλνεται τίποτα."}
    if t == "pause":
        guard._atomic_write(guard.STOP, time.strftime("%Y-%m-%d %H:%M") + " Σε παύση από τον χρήστη\n")
        return {"ok": True, "message": "Σε παύση. Τίποτα δεν θα σταλεί μέχρι να πατήσεις «Συνέχεια»."}
    if t == "resume":
        guard.STOP.unlink(missing_ok=True)
        return {"ok": True, "message": "Συνεχίζει κανονικά."}
    if t == "dismiss_alert":
        ALERT.unlink(missing_ok=True)
        return {"ok": True, "message": "Εντάξει."}
    if t == "limits":
        write_config({"limits": PRESETS.get(a.get("value"), PRESETS["normal"])})
        return {"ok": True, "message": "Τα όρια ενημερώθηκαν."}
    if t == "run":
        if a.get("task") not in ("outreach", "inbox", "post", "orders"):
            return {"ok": False, "message": "Άγνωστη εκτέλεση."}
        return start_job(a["task"])
    if t == "order_add":
        text = str(a.get("text") or "").strip()
        if len(text) < 5:
            return {"ok": False, "message": "Γράψε την εντολή με λίγα λόγια (π.χ. έναν σύνδεσμο LinkedIn και τι θέλεις να του γράψει)."}
        guard.add_order(text)
        return {"ok": True, "message": "Η εντολή προστέθηκε. Θα εκτελεστεί στην επόμενη εκτέλεση, ή πάτα «Εκτέλεση τώρα»."}
    if t in ("order_remove", "order_retry"):
        items = guard.load_orders()
        oid = int(a.get("id") or 0)
        if t == "order_remove":
            items = [o for o in items if int(o.get("id", -1)) != oid]
        else:
            for o in items:
                if int(o.get("id", -1)) == oid:
                    o["status"], o["result"] = "pending", ""
        guard.save_orders(items)
        return {"ok": True, "message": "Έγινε."}
    if t == "schedule":
        return install_schedule()
    if t == "linkedin_login":
        ok = console("uvx --python 3.12 mcp-server-linkedin --login")
        return {"ok": ok, "message": "Άνοιξε ένα νέο παράθυρο. Κάνε login στο LinkedIn εκεί." if ok else "Τρέξε στο Terminal: uvx --python 3.12 mcp-server-linkedin --login"}
    if t == "claude_login":
        ok = console("claude auth login")
        return {"ok": ok, "message": "Άνοιξε νέο παράθυρο και ο browser. Πάτα Authorize στη σελίδα του Claude (αν δείξει κωδικό, κόλλησέ τον στο παράθυρο)." if ok else "Τρέξε στο Terminal: claude auth login"}
    if t == "install_claude":
        ok = console('powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://claude.ai/install.ps1 | iex"')
        return {"ok": ok, "message": "Άνοιξε νέο παράθυρο για την εγκατάσταση. Όταν τελειώσει, κλείσε το START και άνοιξέ το ξανά." if ok
                else "Εγκατάσταση: curl -fsSL https://claude.ai/install.sh | bash"}
    if t == "open_folder":
        if WIN:
            os.startfile(str(guard.DATA))  # type: ignore[attr-defined]
        return {"ok": True, "message": "Άνοιξε ο φάκελος."}
    return {"ok": False, "message": "Άγνωστη ενέργεια."}


# ------------------------------------------------------------------ http
class H(BaseHTTPRequestHandler):
    timeout = 60

    def log_message(self, *a):
        pass

    def _send(self, code: int, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"))

    def _host_ok(self) -> bool:
        return (self.headers.get("Host") or "") in ALLOWED_HOSTS  # blocks DNS-rebinding

    def do_GET(self):
        try:
            if not self._host_ok():
                return self._json({"error": "bad host"}, 403)
            path = self.path.split("?")[0]
            if path == "/":
                return self._send(200, (UI / "index.html").read_bytes(), "text/html; charset=utf-8")
            if path == "/api/ping":
                return self._json({"app": APP_ID, "root": str(ROOT)})
            if path == "/api/state":
                return self._json(state())
            self._json({"error": "not found"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            log.exception("GET %s", self.path)
            try:
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)
            except Exception:  # noqa: BLE001
                pass

    def do_POST(self):
        try:
            if not self._host_ok() or self.headers.get("X-LA") != "1":
                return self._json({"error": "forbidden"}, 403)
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/config":
                write_config(body.get("values", {}))
                res = {"ok": True, "message": "Αποθηκεύτηκε."}
                if body.get("reschedule") and cached("schedule", 20, schedule_installed, False):
                    res["message"] = "Αποθηκεύτηκε. " + install_schedule()["message"]
                return self._json(res)
            if self.path == "/api/action":
                return self._json(action(body))
            self._json({"error": "not found"}, 404)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # noqa: BLE001
            log.exception("POST %s", self.path)
            try:
                self._json({"ok": False, "message": f"Σφάλμα: {e}"}, 500)
            except Exception:  # noqa: BLE001
                pass


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = not WIN  # on Windows SO_REUSEADDR lets TWO servers share one port: never use it there
    request_queue_size = 128  # the default (5) drops connections when a browser opens several at once

    def server_bind(self):
        if WIN:
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def is_ours(p: int) -> bool:
    """Is the program on this (already busy) port the dashboard of THIS folder?"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{p}/api/ping", timeout=2) as r:
            d = json.load(r)
            return d.get("app") == APP_ID and d.get("root") == str(ROOT)
    except Exception:  # noqa: BLE001
        return False


def main():
    global PORT
    srv = None
    # Bind FIRST (instant). Only when a port is taken do we look at who owns it: pinging closed ports is slow on Windows (~1 s each).
    for p in range(PORT, PORT + 10):
        try:
            srv = Server(("127.0.0.1", p), H)
            PORT = p
            break
        except OSError:
            if is_ours(p):  # START was opened twice: reuse the running dashboard instead of making a confusing second one
                print(f"\n  Ο πίνακας τρέχει ήδη: http://127.0.0.1:{p}\n  Τον ανοίγω ξανά στον browser.")
                if not os.environ.get("LA_NO_BROWSER"):
                    webbrowser.open(f"http://127.0.0.1:{p}")
                return
    if not srv:
        print("Δεν βρέθηκε ελεύθερη θύρα (8787–8796). Κλείσε άλλα προγράμματα και δοκίμασε ξανά.")
        sys.exit(1)
    ALLOWED_HOSTS.update({f"127.0.0.1:{PORT}", f"localhost:{PORT}"})
    url = f"http://127.0.0.1:{PORT}"
    log.info("dashboard started on %s (root %s)", url, ROOT)
    print(f"\n  LinkedIn Autopilot τρέχει στο {url}\n  Άφησε αυτό το παράθυρο ανοιχτό όσο το χρησιμοποιείς.\n  (Η αυτόματη δουλειά τρέχει και χωρίς αυτό το παράθυρο.)\n")
    if not os.environ.get("LA_NO_BROWSER"):
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        main()
    except Exception:  # noqa: BLE001
        log.exception("fatal")
        raise
