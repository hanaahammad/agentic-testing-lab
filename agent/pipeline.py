"""The QA cycle: design -> generate -> run -> triage -> (repair -> rerun) -> file/close issues."""
import ast
import datetime as dt
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from . import demo_data
from .config import REPORTS_DIR, ROOT, TESTS_DIR
from .target import compact_spec, fetch_openapi

QA_SYSTEM = (
    "You are a senior QA engineer doing BLACK-BOX testing of a REST API. You only know the user story "
    "and the public API description; you never see the source code. The story is the source of truth: "
    "tests must assert what the story says SHOULD happen, not what the app currently does."
)

CONFTEST_HELP = """Available pytest fixture (already defined in tests/conftest.py, do NOT redefine it):
- `api`: a client on a freshly reset app. Methods:
    api.get(path) -> requests.Response
    api.post(path, json=dict) -> requests.Response
    api.create_account(owner="Test User", initial_deposit=0) -> dict  (asserts 201, returns account JSON)
    api.balance(account_id) -> float  (asserts 200, returns the balance)"""


# ---------- 1. Design ----------
def design_tests(llm, story: dict, spec: dict) -> list[dict]:
    if llm.demo:
        return demo_data.cases(story["id"])
    num = story["id"].split("-")[1]
    prompt = f"""User story:
{story['text']}

API under test:
{compact_spec(spec)}

Design black-box test cases that cover EVERY acceptance criterion: at least one positive case, plus
negative and boundary cases where the criterion invites them. Keep it to 4-8 cases.

Reply with JSON only:
{{"test_cases": [{{"id": "TC-{num}-01", "title": "...", "type": "positive|negative|boundary",
"criterion": "AC1", "steps": ["..."], "expected": "..."}}]}}
Number ids TC-{num}-01, TC-{num}-02, ..."""
    data = llm.complete_json(QA_SYSTEM, prompt)
    return data["test_cases"] if isinstance(data, dict) else data


# ---------- 2. Generate ----------
def generate_script(llm, story: dict, cases: list[dict], spec: dict) -> str:
    if llm.demo:
        return demo_data.SCRIPTS[story["id"]]
    prompt = f"""User story:
{story['text']}

API under test:
{compact_spec(spec)}

{CONFTEST_HELP}

Approved test cases (JSON):
{json.dumps(cases, indent=2)}

Write ONE pytest module implementing exactly these cases.
Rules:
- One test function per case, named test_<id in lowercase with dashes as underscores>_<short_slug>,
  e.g. TC-003-02 -> def test_tc_003_02_transfer_above_balance_refused(api):
- First line of each test is a docstring with the case id.
- Use only the `api` fixture; no imports are needed except what you truly use.
- Assert status codes AND resulting state (balances) as the story requires; put r.text in assert messages.
- Assert the story's intended behaviour even if you suspect the app is wrong.
Reply with the python module in a ```python block."""
    return llm.complete_code(QA_SYSTEM, prompt)


def script_path(story_id: str) -> Path:
    return TESTS_DIR / f"test_{story_id.lower().replace('-', '_')}.py"


def save_script(story_id: str, code: str) -> Path:
    TESTS_DIR.mkdir(parents=True, exist_ok=True)
    path = script_path(story_id)
    path.write_text(code, encoding="utf-8")
    return path


# ---------- 3. Run ----------
def run_tests(path: Path, base_url: str) -> dict:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    junit = REPORTS_DIR / f"junit_{Path(path).stem}.xml"
    junit.unlink(missing_ok=True)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(path), "-q", "--no-header", "-p", "no:cacheprovider",
         f"--junitxml={junit}"],
        cwd=ROOT, env={**os.environ, "BASE_URL": base_url}, capture_output=True, text=True, timeout=300,
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


def triage(llm, story: dict, cases: list[dict], code: str, run: dict, spec: dict) -> list[dict]:
    fails = failures(run)
    if not fails:
        return []
    if llm.demo:
        return [demo_data.heuristic_triage(f, cases) for f in fails]
    items = [{"tc_id": f["tc_id"], "test_name": f["name"], "test_source": extract_function(code, f["name"]),
              "failure": (f["message"] + "\n" + f["details"])[-2500:]} for f in fails]
    prompt = f"""User story:
{story['text']}

API under test:
{compact_spec(spec)}

Test cases: {json.dumps(cases)}

Failed tests:
{json.dumps(items, indent=2)}

For EACH failed test decide:
- "product_bug": the app's behaviour contradicts the story (wrong status, wrong balance, missing rule).
- "test_bug": the test itself is wrong (Python error, wrong field name, wrong expectation vs the story).
- "environment": the app was unreachable or the infrastructure failed.

Reply with JSON only:
{{"verdicts": [{{"tc_id": "...", "test_name": "...", "verdict": "product_bug|test_bug|environment",
"confidence": 0.0-1.0, "severity": "critical|high|medium|low", "criterion": "AC?",
"title": "short bug title", "steps": ["..."], "expected": "...", "actual": "...",
"reasoning": "one or two sentences"}}]}}"""
    data = llm.complete_json(QA_SYSTEM, prompt)
    return data["verdicts"] if isinstance(data, dict) else data


# ---------- 5. Repair (self-healing for test bugs) ----------
def repair_script(llm, story: dict, code: str, verdicts: list[dict], run: dict, spec: dict) -> str:
    if llm.demo:
        return demo_data.REPAIRED.get(story["id"], code)
    broken = [v for v in verdicts if v["verdict"] == "test_bug"]
    errs = {f["name"]: (f["message"] + "\n" + f["details"])[-2000:] for f in failures(run)}
    prompt = f"""User story:
{story['text']}

API under test:
{compact_spec(spec)}

{CONFTEST_HELP}

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
    log(f"[{story['id']}] Discovering the API at {base_url}/openapi.json")
    spec = fetch_openapi(base_url)

    log(f"[{story['id']}] Designing test cases from the acceptance criteria")
    cases = design_tests(llm, story, spec)
    if approve:
        cases = approve(cases)
    log(f"[{story['id']}] {len(cases)} test cases approved")

    log(f"[{story['id']}] Writing the pytest script")
    code = generate_script(llm, story, cases, spec)
    path = save_script(story["id"], code)

    log(f"[{story['id']}] Running tests against the app")
    run = run_tests(path, base_url)
    log(f"[{story['id']}] Result: {run['summary']}")
    verdicts = triage(llm, story, cases, code, run, spec)

    repairs = 0
    while any(v["verdict"] == "test_bug" for v in verdicts) and repairs < max_repairs:
        repairs += 1
        log(f"[{story['id']}] Triage found a bug in my own test script. Repairing it (attempt {repairs})")
        code = repair_script(llm, story, code, verdicts, run, spec)
        path = save_script(story["id"], code)
        run = run_tests(path, base_url)
        log(f"[{story['id']}] Re-run result: {run['summary']}")
        verdicts = triage(llm, story, cases, code, run, spec)

    for v in verdicts:
        log(f"[{story['id']}] {v.get('tc_id')}: {v['verdict']} - {v.get('title', '')}")

    actions = []
    if tracker is not None:
        from .issues import sync_issues

        actions = sync_issues(tracker, story, run, verdicts)
        for a in actions:
            log(f"[{story['id']}] Issue {a['action']}: #{a['issue']['number']} {a['issue']['title']}")

    result = {"story": story["id"], "cases": cases, "script": str(path), "run": run,
              "verdicts": verdicts, "repairs": repairs, "actions": actions}
    write_report(story, result)
    return result


def write_report(story: dict, result: dict) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    s = result["run"]["summary"]
    lines = [f"## {story['id']}: {story['title']}", "",
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
