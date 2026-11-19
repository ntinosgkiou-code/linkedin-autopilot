# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Publish posts to LinkedIn through the OFFICIAL API (no browser automation, no ban risk).

  uv run tools/linkedin_post.py auth            one-time: connect your LinkedIn developer app
  uv run tools/linkedin_post.py publish FILE    publish the text in FILE as a post
  uv run tools/linkedin_post.py status          token validity

One-time app setup (5 minutes, free) is described in README.md, "Auto-publishing posts".
"""
from __future__ import annotations

import http.server
import json
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRETS = ROOT / "data" / ".secrets" / "linkedin.json"
PORT = 8765
REDIRECT = f"http://localhost:{PORT}/callback"
SCOPES = "openid profile w_member_social"


def out(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False, indent=1))
    sys.exit(code)


def http(method, url, data=None, headers=None, form=False):
    body = None
    headers = dict(headers or {})
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode() or "{}"
            return r.status, dict(r.headers), json.loads(raw) if raw.strip().startswith("{") else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, dict(e.headers), json.loads(raw)
        except json.JSONDecodeError:
            return e.code, dict(e.headers), {"raw": raw[:500]}


# ------------------------------------------------------------------ auth
def cmd_auth():
    print("LinkedIn developer app credentials (see README > Auto-publishing posts).")
    client_id = input("Client ID: ").strip()
    client_secret = input("Client Secret: ").strip()
    state = secrets.token_urlsafe(16)
    result = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>Done. You can close this tab.</h2>".encode())

        def log_message(self, *a):
            pass

    url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT,
        "state": state, "scope": SCOPES})
    srv = http.server.HTTPServer(("127.0.0.1", PORT), H)
    srv.timeout = 300
    print("\nOpening LinkedIn in your browser. Approve the access...")
    webbrowser.open(url)
    print(f"(If it did not open, paste this in your browser:)\n{url}\n")
    while "code" not in result and "error" not in result:
        srv.handle_request()
    if result.get("state") != state or "code" not in result:
        out({"ok": False, "error": result.get("error_description") or result.get("error") or "state mismatch"}, 1)

    st, _, tok = http("POST", "https://www.linkedin.com/oauth/v2/accessToken", {
        "grant_type": "authorization_code", "code": result["code"], "redirect_uri": REDIRECT,
        "client_id": client_id, "client_secret": client_secret}, form=True)
    if st != 200 or "access_token" not in tok:
        out({"ok": False, "status": st, "error": tok}, 1)
    st, _, me = http("GET", "https://api.linkedin.com/v2/userinfo",
                     headers={"Authorization": f"Bearer {tok['access_token']}"})
    if st != 200 or "sub" not in me:
        out({"ok": False, "status": st, "error": me}, 1)
    SECRETS.parent.mkdir(parents=True, exist_ok=True)
    SECRETS.write_text(json.dumps({
        "access_token": tok["access_token"], "expires_at": int(time.time()) + int(tok.get("expires_in", 0)),
        "person_urn": f"urn:li:person:{me['sub']}", "name": me.get("name", "")}, indent=1), encoding="utf-8")
    out({"ok": True, "connected_as": me.get("name"), "valid_days": int(tok.get("expires_in", 0)) // 86400})


def load_token():
    if not SECRETS.exists():
        out({"ok": False, "error": "Not connected. Run: uv run tools/linkedin_post.py auth"}, 1)
    s = json.loads(SECRETS.read_text(encoding="utf-8"))
    days = (s["expires_at"] - time.time()) / 86400
    if days <= 0:
        out({"ok": False, "error": "LinkedIn token expired (they last 60 days). Run: uv run tools/linkedin_post.py auth"}, 1)
    return s, days


def cmd_status():
    s, days = load_token()
    out({"ok": True, "connected_as": s.get("name"), "days_left": int(days),
         "warning": "Re-run auth soon" if days < 7 else None})


# ------------------------------------------------------------------ publish
_RESERVED = re.compile(r"([\\|{}@\[\]()<>*_~])")


def to_little_text(text: str) -> str:
    """LinkedIn 'commentary' uses Little Text Format: escape reserved chars, keep #hashtags clickable."""
    parts = re.split(r"(#\w+)", text)
    res = []
    for p in parts:
        if re.fullmatch(r"#\w+", p):
            res.append("{hashtag|\\#|" + p[1:] + "}")
        else:
            res.append(_RESERVED.sub(r"\\\1", p).replace("#", "\\#"))
    return "".join(res)


def versions():
    d = date.today()
    y, m = d.year, d.month
    for back in range(1, 12):
        mm, yy = m - back, y
        while mm <= 0:
            mm += 12
            yy -= 1
        yield f"{yy}{mm:02d}"


def cmd_publish(path: str):
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        out({"ok": False, "error": "post file is empty"}, 1)
    if len(text) > 3000:
        out({"ok": False, "error": f"post is {len(text)} chars; LinkedIn max is 3000"}, 1)
    s, days = load_token()
    body = {"author": s["person_urn"], "commentary": to_little_text(text), "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [],
                             "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False}
    last = None
    for v in versions():
        st, hdr, resp = http("POST", "https://api.linkedin.com/rest/posts", body, headers={
            "Authorization": f"Bearer {s['access_token']}", "LinkedIn-Version": v,
            "X-Restli-Protocol-Version": "2.0.0"})
        if st in (200, 201):
            urn = hdr.get("x-restli-id") or hdr.get("X-RestLi-Id") or resp.get("id", "")
            out({"ok": True, "post_urn": urn, "url": f"https://www.linkedin.com/feed/update/{urn}/" if urn else None,
                 "token_days_left": int(days)})
        last = (st, resp)
        msg = json.dumps(resp).lower()
        if not (st in (400, 426) and "version" in msg):
            break  # not a version problem: do not retry
    out({"ok": False, "status": last[0], "error": last[1]}, 1)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if not args or args[0] not in ("auth", "publish", "status"):
        print(__doc__)
        sys.exit(1)
    if args[0] == "auth":
        cmd_auth()
    elif args[0] == "status":
        cmd_status()
    else:
        if len(args) < 2:
            out({"ok": False, "error": "usage: publish FILE"}, 1)
        cmd_publish(args[1])
