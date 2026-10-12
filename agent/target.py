"""Everything about the application under test: starting it, checking it, discovering its API and screens."""
import atexit
import os
import subprocess
import sys
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

from .config import ROOT, TARGETS

_procs: dict[str, dict] = {}  # target key -> {"proc", "fixed"}


def health(base_url: str, key: str = "minibank") -> dict | None:
    try:
        r = requests.get(base_url.rstrip("/") + TARGETS[key]["health"], timeout=1.5)
        return r.json() if r.ok else None
    except (requests.RequestException, ValueError):
        return None


def stop_local_app(key: str | None = None):
    for k in ([key] if key else list(_procs)):
        p = _procs.pop(k, {}).get("proc")
        if p and p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


atexit.register(stop_local_app)


def ensure_local_app(key: str = "minibank", fixed: bool = False) -> str:
    """Start the target app as a subprocess (or reuse it) with the requested build. Returns its base URL."""
    t = TARGETS[key]
    url = f"http://127.0.0.1:{t['port']}"
    want = "fixed" if fixed else "buggy"
    h = health(url, key)
    if h and h.get("build") == want:
        return url
    if h and key not in _procs:
        raise RuntimeError(
            f"Port {t['port']} is already serving a '{h.get('build')}' {t['name']} that this session did not start. "
            f"Stop it, or restart it with {t['fixed_env']}={'1' if fixed else '0'}.")
    stop_local_app(key)
    env = {**os.environ, t["fixed_env"]: "1" if fixed else "0"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", t["module"], "--host", "127.0.0.1", "--port", str(t["port"]),
         "--log-level", "warning"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    _procs[key] = {"proc": proc, "fixed": fixed}
    for _ in range(100):
        h = health(url, key)
        if h and h.get("build") == want:
            return url
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    raise RuntimeError(f"{t['name']} did not start. Are its requirements installed?")


def reset(base_url: str, key: str):
    requests.post(base_url.rstrip("/") + TARGETS[key]["reset"], timeout=10)


def fetch_openapi(base_url: str, key: str = "minibank") -> dict:
    r = requests.get(base_url.rstrip("/") + TARGETS[key]["openapi"], timeout=10)
    r.raise_for_status()
    return r.json()


def endpoint_table(spec: dict) -> list[dict]:
    rows = []
    for path, ops in spec.get("paths", {}).items():
        for method, op in ops.items():
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {})
            ref = body.get("$ref", "").split("/")[-1]
            rows.append({"method": method.upper(), "path": path, "summary": op.get("summary", ""), "body": ref})
    return rows


def compact_spec(spec: dict) -> str:
    """A short, LLM-friendly view of the API: endpoints plus request schemas."""
    lines = [f"{r['method']} {r['path']} - {r['summary']}" + (f" (body: {r['body']})" if r["body"] else "")
             for r in endpoint_table(spec)]
    for name, sch in spec.get("components", {}).get("schemas", {}).items():
        if name.startswith(("HTTPValidationError", "ValidationError")):
            continue
        props = ", ".join(f"{k}: {v.get('type', v.get('anyOf', '?'))}" for k, v in sch.get("properties", {}).items())
        lines.append(f"schema {name} {{{props}}} required={sch.get('required', [])}")
    return "\n".join(lines)


# ---------------------------------------------------------------- UI discovery (web apps)
class _TestIdParser(HTMLParser):
    """Collects every element with a data-testid, plus links, the way a tester maps a new screen."""

    def __init__(self):
        super().__init__()
        self.items, self.links, self._open, self._select = [], [], None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag == "option" and self._select is not None:
            self._select["options"].append(a.get("value", ""))
        tid = a.get("data-testid")
        if not tid:
            return
        item = {"tag": tag, "testid": tid, "type": a.get("type", ""), "text": "", "options": []}
        self.items.append(item)
        if tag == "select":
            self._select = item
        if tag in ("a", "button", "h1", "b", "span", "td", "label"):
            self._open, self._open_tag = item, tag

    def handle_endtag(self, tag):
        if tag == "select":
            self._select = None
        if self._open is not None and tag == getattr(self, "_open_tag", None):
            self._open = None

    def handle_data(self, data):
        if self._open is not None and data.strip() and len(self._open["text"]) < 60:
            self._open["text"] = (self._open["text"] + " " + data.strip()).strip()[:60]


LAYOUT_IDS = {"brand", "main-nav", "nav-dashboard", "nav-transfer", "nav-beneficiaries", "nav-history",
              "user-name", "logout-link", "build"}


def _describe(path: str, html_text: str, skip: set | None = None) -> tuple[str, list[str]]:
    p = _TestIdParser()
    p.feed(html_text)
    seen, parts = set(skip or ()), []
    for it in p.items:
        tid = it["testid"]
        if tid in seen:
            continue
        seen.add(tid)
        kind = it["tag"] + (f"[{it['type']}]" if it["type"] else "")
        extra = f' "{it["text"]}"' if it["text"] else ""
        if it["options"]:
            extra += " options=" + ",".join(it["options"][:8])
        parts.append(f"  - {kind} data-testid={tid}{extra}")
    return f"PAGE {path}\n" + "\n".join(parts), p.links


def discover_ui(base_url: str, key: str, max_pages: int = 12) -> str:
    """Crawl the web app as a signed-in test user and return a compact map of screens and their test ids."""
    t = TARGETS[key]
    if t["kind"] != "web":
        return ""
    reset(base_url, key)
    s = requests.Session()
    out, queue, done = [], ["/login"], set()
    r = s.get(base_url + "/login", timeout=10)
    desc, _ = _describe("/login", r.text)
    out.append(desc)
    done.add("/login")
    user, pw = t["test_user"]
    r = s.post(base_url + "/login", data={"username": user, "password": pw}, timeout=10)
    queue = [urlparse(r.url).path or "/dashboard"]
    first = True
    while queue and len(done) < max_pages:
        path = queue.pop(0)
        if path in done or path in ("/logout",):
            continue
        r = s.get(base_url + path, timeout=10)
        final = urlparse(r.url).path
        done.add(path)
        if "text/html" not in r.headers.get("content-type", "") or (final != path and final in done):
            continue
        done.add(final)
        # The shared layout (menu, user name, sign-out link) is described once, on the first signed-in page.
        desc, links = _describe(final, r.text, skip=None if first else LAYOUT_IDS)
        first = False
        out.append(desc)
        for href in links:
            u = urlparse(urljoin(base_url + path, href))
            if u.netloc == urlparse(base_url).netloc and u.path not in done and not u.query and u.path not in queue:
                queue.append(u.path)
    out.append("PAGE /logout\n  - (link data-testid=logout-link) signs out and redirects to /login?signed_out=1")
    reset(base_url, key)
    return "\n".join(out)


# ---------------------------------------------------------------- browser (web apps)
BROWSER_CHOICES = ["chromium", "msedge", "chrome"]  # Playwright's own Chromium, then installed Edge / Chrome
BROWSER_NAMES = {"chromium": "Playwright Chromium", "msedge": "Microsoft Edge", "chrome": "Google Chrome"}


def launch_browser(pw, headless=True):
    """Playwright's Chromium if installed, else the Edge or Chrome already on the machine (no download needed)."""
    forced = os.getenv("PLAYWRIGHT_CHANNEL", "").strip()
    errors = []
    for channel in ([forced] if forced else BROWSER_CHOICES):
        try:
            return pw.chromium.launch(headless=headless, **({} if channel == "chromium" else {"channel": channel}))
        except Exception as e:
            errors.append(f"{channel}: {str(e).splitlines()[0][:160]}")
    raise RuntimeError("No browser for UI tests. Tried " + " | ".join(errors))


_browser_status: dict = {}


def browser_ready(refresh: bool = False) -> tuple[bool, str]:
    """Which browser can drive the UI tests here? Checked in a separate process (safe inside Streamlit on Windows)."""
    if _browser_status and not refresh:
        return _browser_status["ok"], _browser_status["msg"]
    code = ("import os, sys\n"
            "from playwright.sync_api import sync_playwright\n"
            "forced = os.getenv('PLAYWRIGHT_CHANNEL', '').strip()\n"
            f"choices = [forced] if forced else {BROWSER_CHOICES!r}\n"
            "p = sync_playwright().start()\n"
            "for ch in choices:\n"
            "    try:\n"
            "        b = p.chromium.launch(**({} if ch == 'chromium' else {'channel': ch})); b.close()\n"
            "        print('OK', ch); break\n"
            "    except Exception as e:\n"
            "        print('FAIL', ch, str(e).splitlines()[0][:160])\n"
            "p.stop()\n")
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
        lines = r.stdout.strip().splitlines()
        ok_line = next((ln for ln in lines if ln.startswith("OK ")), None)
        if ok_line:
            ok, msg = True, f"ready ({BROWSER_NAMES.get(ok_line.split()[1], ok_line.split()[1])})"
        else:
            ok, msg = False, "; ".join(lines) or (r.stderr.strip().splitlines() or ["unknown error"])[-1]
    except subprocess.TimeoutExpired:
        ok, msg = False, "the browser did not start within 120 s"
    _browser_status.update(ok=ok, msg=msg)
    return ok, msg


BROWSER_FIX = "python -m playwright install chromium   (or install Microsoft Edge / Google Chrome)"
