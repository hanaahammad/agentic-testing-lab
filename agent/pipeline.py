"""The QA cycle: discover -> design -> generate -> run -> triage -> (repair -> rerun) -> file/close issues.

Works for any registered target app (agent/config.py TARGETS): API-only apps get API tests,
web apps get a mix of Playwright UI tests and API tests.
"""
import ast
import datetime as dt
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from . import demo_data, demo_nilebank
from .config import REPORTS_DIR, ROOT, TARGETS, tests_dir
from .target import BROWSER_FIX, browser_ready, compact_spec, discover_ui, fetch_openapi

QA_SYSTEM = (
    "You are a senior QA engineer doing BLACK-BOX testing. You only know the user story, the public API "
    "description and (for web apps) the screens you discovered; you never see the source code. The story is the "
    "source of truth: tests must assert what the story says SHOULD happen, not what the app currently does."
)

HELPERS = {
    "minibank": """Available pytest fixture (already defined in tests/minibank/conftest.py, do NOT redefine it):
- `api`: a client on a freshly reset app. Methods:
    api.get(path) -> requests.Response
    api.post(path, json=dict) -> requests.Response
    api.create_account(owner="Test User", initial_deposit=0) -> dict  (asserts 201, returns account JSON)
    api.balance(account_id) -> float  (asserts 200, returns the balance)""",
    "nilebank": """Test toolkit (tests/nilebank/conftest.py and nilebank_helpers.py; do NOT redefine fixtures).
Every test starts on freshly reset demo data (autouse fixture).
Fixtures:
- `bank`: API client, not signed in. bank.get(path, params=...), bank.post(path, json=...) -> requests.Response;
  bank.login(username, password) signs in (stores the Bearer token); bank.balance(account_id) -> float.
- `amira`: the same API client already signed in as amira / Nile@2026.
- `page`: a fresh Playwright sync Page (headless Chromium), base_url set, so page.goto("/transfer") works.
  Default timeout 5 s.
- `signed_in`: a Page already signed in as amira and sitting on /dashboard.
Helpers: `from nilebank_helpers import sign_in, money`
- sign_in(page, username, password) fills and submits the sign-in form.
- money("EGP 1,234.50") -> 1234.5
UI rules: locate elements ONLY with page.get_by_test_id("<data-testid>") using ids from the screen map;
use `from playwright.sync_api import expect` for UI assertions, e.g. expect(locator).to_have_text("...");
for URLs use expect(page).to_have_url(re.compile(r".*/login(\\?.*)?$")).""",
}


# ---------- 0. Discover ----------
def discover(story: dict, base_url: str) -> dict:
    """What a tester does on day one: read the API description and walk through the screens."""
    key = story.get("target", "minibank")
    spec = fetch_openapi(base_url, key)
    ui_map = discover_ui(base_url, key) if TARGETS[key]["kind"] == "web" else ""
    return {"target": key, "spec": spec, "ui_map": ui_map}


def _surface(ctx: dict) -> str:
    text = f"API under test:\n{compact_spec(ctx['spec'])}"
    if ctx.get("ui_map"):
        text += f"\n\nScreens discovered by crawling the web app as a test user (element data-testids):\n{ctx['ui_map']}"
    return text


# ---------- 1. Design ----------
def design_tests(llm, story: dict, ctx: dict) -> list[dict]:
    if llm.demo:
        return demo_nilebank.CASES[story["id"]] if ctx["target"] == "nilebank" else demo_data.cases(story["id"])
    num = story["id"].split("-")[1]
    web = TARGETS[ctx["target"]]["kind"] == "web"
    mix = ("This is a web app with an API: design a MIX of UI tests (through the screens, as a customer) and API "
           "tests (fast checks of rules and security). Prefer UI for what the customer sees, API for rules. "
           if web else "")
    prompt = f"""User story:
{story['text']}

{_surface(ctx)}

Design black-box test cases that cover EVERY acceptance criterion: at least one positive case, plus
negative, boundary and security cases where the criterion invites them. {mix}Keep it to 4-8 cases.

Reply with JSON only:
{{"test_cases": [{{"id": "TC-{num}-01", "title": "...", "type": "positive|negative|boundary|security",
"criterion": "AC1", "interface": "{'UI|API' if web else 'API'}", "steps": ["..."], "expected": "..."}}]}}
Number ids TC-{num}-01, TC-{num}-02, ..."""
    data = llm.complete_json(QA_SYSTEM, prompt)
    return data["test_cases"] if isinstance(data, dict) else data


# ---------- 2. Generate ----------
def generate_script(llm, story: dict, cases: list[dict], ctx: dict) -> str:
    if llm.demo:
        return demo_nilebank.script(story["id"]) if ctx["target"] == "nilebank" else demo_data.SCRIPTS[story["id"]]
    prompt = f"""User story:
{story['text']}

{_surface(ctx)}

{HELPERS[ctx['target']]}

Approved test cases (JSON):
{json.dumps(cases, indent=2)}

Write ONE pytest module implementing exactly these cases.
Rules:
- One test function per case, named test_<id in lowercase with dashes as underscores>_<short_slug>,
  e.g. TC-003-02 -> def test_tc_003_02_transfer_above_balance_refused(...):
- First line of each test is a docstring with the case id.
- Use only the fixtures and helpers listed above.
- Assert status codes AND resulting state (balances, what is shown) as the story requires; put useful context
  in assert messages.
- Assert the story's intended behaviour even if you suspect the app is wrong.
Reply with the python module in a ```python block."""
    return llm.complete_code(QA_SYSTEM, prompt)


def script_path(story: dict) -> Path:
    return tests_dir(story.get("target", "minibank")) / f"test_{story['id'].lower().replace('-', '_')}.py"


def save_script(story: dict, code: str) -> Path:
    path = script_path(story)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code, encoding="utf-8")
    return path


# ---------- 3. Run ----------
def run_tests(path: Path, base_url: str, key: str = "minibank") -> dict:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    junit = REPORTS_DIR / f"junit_{Path(path).stem}.xml"
    junit.unlink(missing_ok=True)
    env = {**os.environ, "BASE_URL": base_url, f"{key.upper()}_URL": base_url}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(path), "-q", "--no-header", f"--junitxml={junit}"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=600,
    )
    cases = parse_junit(junit) if junit.exists() else []
    summary = {k: sum(1 for c in cases if c["status"] == k) for k in ("passed", "failed", "error", "skipped")}
    summary["total"] = len(cases)
    return {"cases": cases, "summary": summary, "returncode": proc.returncode,
            "output": (proc.stdout[-6000:] + "\n" + proc.stderr[-2000:]).strip()}


def parse_junit(path: Path) -> list[dict]:
    out = []
    for tc in ET.parse(path).getroot().iter("testcase"):
        name = tc.get("name") or tc.get("classname") or "collection"
        status, msg, det = "passed", "", ""
        for tag, label in (("failure", "failed"), ("error", "error"), ("skipped", "skipped")):
            el = tc.find(tag)
            if el is not None:
                status, msg, det = label, el.get("message", ""), (el.text or "")
                break
        m = re.search(r"tc_(\d+)_(\d+)", name)
        out.append({"name": name, "tc_id": f"TC-{m.group(1)}-{m.group(2)}" if m else None,
                    "status": status, "message": msg, "details": det[-3000:]})
    return out


def failures(run: dict) -> list[dict]:
    return [c for c in run["cases"] if c["status"] in ("failed", "error")]


# ---------- 4. Triage ----------
def extract_function(code: str, name: str) -> str:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return code[:3000]
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(code, node) or ""
    return ""


def triage(llm, story: dict, cases: list[dict], code: str, run: dict, ctx: dict) -> list[dict]:
    fails = failures(run)
    if not fails:
        return []
    if llm.demo:
        return [demo_data.heuristic_triage(f, cases) for f in fails]
    items = [{"tc_id": f["tc_id"], "test_name": f["name"], "test_source": extract_function(code, f["name"]),
              "failure": (f["message"] + "\n" + f["details"])[-2500:]} for f in fails]
    prompt = f"""User story:
{story['text']}

{_surface(ctx)}

Test cases: {json.dumps(cases)}

Failed tests:
{json.dumps(items, indent=2)}

For EACH failed test decide:
- "product_bug": the app's behaviour contradicts the story (wrong status, wrong amount, wrong text on screen,
  missing rule, security hole).
- "test_bug": the test itself is wrong (Python error, wrong field name, a data-testid that is not in the screen
  map, a wrong expectation vs the story).
- "environment": the app or browser was unreachable or the infrastructure failed.

Reply with JSON only:
{{"verdicts": [{{"tc_id": "...", "test_name": "...", "verdict": "product_bug|test_bug|environment",
"confidence": 0.0-1.0, "severity": "critical|high|medium|low", "criterion": "AC?",
"title": "short bug title", "steps": ["..."], "expected": "...", "actual": "...",
"reasoning": "one or two sentences"}}]}}"""
    data = llm.complete_json(QA_SYSTEM, prompt)
    return data["verdicts"] if isinstance(data, dict) else data


# ---------- 5. Repair (self-healing for test bugs) ----------
def repair_script(llm, story: dict, code: str, verdicts: list[dict], run: dict, ctx: dict) -> str:
    if llm.demo:
        if ctx["target"] == "nilebank":
            return demo_nilebank.repaired(story["id"], code)
        return demo_data.REPAIRED.get(story["id"], code)
    broken = [v for v in verdicts if v["verdict"] == "test_bug"]
    errs = {f["name"]: (f["message"] + "\n" + f["details"])[-2000:] for f in failures(run)}
    prompt = f"""User story:
{story['text']}

{_surface(ctx)}

{HELPERS[ctx['target']]}

Current test module:
```python
{code}
```

These tests were diagnosed as TEST bugs (the test is wrong, not the app):
{json.dumps([{**v, "error": errs.get(v.get("test_name"), "")} for v in broken], indent=2)}

Fix ONLY those tests so they correctly check the story. Do not weaken assertions that check the
story's rules, and leave every other test exactly as it is. Reply with the full module in a ```python block."""
    return llm.complete_code(QA_SYSTEM, prompt)


# ---------- The full cycle ----------
def full_cycle(llm, story: dict, base_url: str, tracker=None, approve=None, log=print, max_repairs: int = 1) -> dict:
    """Runs the whole loop. `approve(cases) -> cases` is the human gate; None = auto-approve."""
    key = story.get("target", "minibank")
    sid = story["id"]
    log(f"[{sid}] Discovering {TARGETS[key]['name']}: reading {base_url}/openapi.json"
        + (" and walking through the screens" if TARGETS[key]["kind"] == "web" else ""))
    ctx = discover(story, base_url)
    if TARGETS[key]["kind"] == "web":
        ok, msg = browser_ready()
        if not ok:
            log(f"[{sid}] ⚠️ The browser for UI tests is not available on this machine ({msg}). "
                f"UI tests will be reported as environment problems, API tests still run. Fix: {BROWSER_FIX}")

    log(f"[{sid}] Designing test cases from the acceptance criteria")
    cases = design_tests(llm, story, ctx)
    if approve:
        cases = approve(cases)
    log(f"[{sid}] {len(cases)} test cases approved")

    log(f"[{sid}] Writing the pytest script" + (" (Playwright UI + API)" if ctx["ui_map"] else ""))
    code = generate_script(llm, story, cases, ctx)
    path = save_script(story, code)

    log(f"[{sid}] Running tests against the app")
    run = run_tests(path, base_url, key)
    log(f"[{sid}] Result: {run['summary']}")
    verdicts = triage(llm, story, cases, code, run, ctx)

    repairs = 0
    while any(v["verdict"] == "test_bug" for v in verdicts) and repairs < max_repairs:
        repairs += 1
        log(f"[{sid}] Triage found a bug in my own test script. Repairing it (attempt {repairs})")
        code = repair_script(llm, story, code, verdicts, run, ctx)
        path = save_script(story, code)
        run = run_tests(path, base_url, key)
        log(f"[{sid}] Re-run result: {run['summary']}")
        verdicts = triage(llm, story, cases, code, run, ctx)

    for v in verdicts:
        log(f"[{sid}] {v.get('tc_id')}: {v['verdict']} - {v.get('title', '')}")

    actions = []
    if tracker is not None:
        from .issues import sync_issues

        actions = sync_issues(tracker, story, run, verdicts)
        for a in actions:
            log(f"[{sid}] Issue {a['action']}: #{a['issue']['number']} {a['issue']['title']}")

    result = {"story": sid, "target": key, "cases": cases, "script": str(path), "run": run,
              "verdicts": verdicts, "repairs": repairs, "actions": actions}
    write_report(story, result)
    record_history(story, result, base_url)
    return result


def write_report(story: dict, result: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    s = result["run"]["summary"]
    lines = [f"## {TARGETS[result['target']]['name']} · {story['id']}: {story['title']}", "",
             f"**{s['passed']} passed, {s['failed']} failed, {s['error']} errors** "
             f"out of {s['total']} (script repairs: {result['repairs']})", "",
             "| Test | Status | Verdict |", "|---|---|---|"]
    verdict_by = {v.get("tc_id"): v["verdict"] for v in result["verdicts"]}
    for c in result["run"]["cases"]:
        lines.append(f"| {c['tc_id'] or c['name']} | {c['status']} | {verdict_by.get(c['tc_id'], '')} |")
    for a in result["actions"]:
        lines.append(f"\n- Issue {a['action']}: [#{a['issue']['number']} {a['issue']['title']}]({a['issue']['url']})")
    md = "\n".join(lines) + "\n"
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = REPORTS_DIR / f"report_{story['id']}_{stamp}.md"
    path.write_text(md, encoding="utf-8")
    summary_file = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_file:
        with open(summary_file, "a", encoding="utf-8") as f:
            f.write(md + "\n")
    return path


HISTORY = REPORTS_DIR / "history.jsonl"


def record_history(story: dict, result: dict, base_url: str) -> None:
    """Append one line per run so the dashboard can show trends over time."""
    from .target import health

    key = result["target"]
    verdict_by = {v.get("tc_id"): v["verdict"] for v in result["verdicts"]}
    case_by = {c["id"]: c for c in result["cases"]}
    entry = {
        "timestamp": dt.datetime.now().isoformat(timespec="seconds"),
        "app": key, "story": story["id"], "title": story["title"],
        "build": (health(base_url, key) or {}).get("build", "unknown"),
        "repairs": result["repairs"],
        "summary": result["run"]["summary"],
        "cases": [{"tc_id": c["tc_id"], "status": c["status"],
                   "verdict": verdict_by.get(c["tc_id"], ""),
                   "title": case_by.get(c["tc_id"], {}).get("title", c["name"]),
                   "criterion": case_by.get(c["tc_id"], {}).get("criterion", ""),
                   "interface": case_by.get(c["tc_id"], {}).get("interface", "API"),
                   "type": case_by.get(c["tc_id"], {}).get("type", "")}
                  for c in result["run"]["cases"]],
    }
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
