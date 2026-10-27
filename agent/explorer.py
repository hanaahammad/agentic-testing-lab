"""Exploratory testing: the agent drives the live app itself, one action at a time.

API apps: the agent has an HTTP tool. Web apps: it also gets a real browser (Playwright) with tools to open
pages, type, click, choose options and read the screen, and every browser step is captured as a screenshot.
With Claude this is a real tool-use loop: Claude decides each action, reads the result and records findings.
In demo mode a scripted session plays the same role.
"""
import json

import requests

from . import demo_data, demo_nilebank
from .config import TARGETS
from .target import compact_spec, discover_ui, reset

HTTP_TOOL = {
    "name": "http_request",
    "description": "Send one HTTP request to the application under test and get the status code and JSON body. "
                   "Paths are relative, e.g. /api/accounts. Pass headers such as Authorization when needed.",
    "input_schema": {"type": "object", "properties": {
        "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
        "path": {"type": "string"},
        "json_body": {"type": "object", "description": "JSON request body, if any"},
        "headers": {"type": "object", "description": "Extra headers, e.g. {\"Authorization\": \"Bearer <token>\"}"},
    }, "required": ["method", "path"]},
}
FINDING_TOOL = {
    "name": "record_finding",
    "description": "Record a behaviour that contradicts the user story. Include the exact steps and what you saw as evidence.",
    "input_schema": {"type": "object", "properties": {
        "title": {"type": "string"},
        "criterion": {"type": "string", "description": "Which acceptance criterion, e.g. AC2"},
        "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
        "evidence": {"type": "string"},
    }, "required": ["title", "severity", "evidence"]},
}
BROWSER_TOOLS = [
    {"name": "browser_open", "description": "Open a page of the web app in the browser, e.g. /login or /transfer.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "browser_fill", "description": "Type text into the input with this data-testid (replaces its content).",
     "input_schema": {"type": "object", "properties": {"test_id": {"type": "string"}, "text": {"type": "string"}},
                      "required": ["test_id", "text"]}},
    {"name": "browser_select", "description": "Choose an option (by value) in the select with this data-testid.",
     "input_schema": {"type": "object", "properties": {"test_id": {"type": "string"}, "value": {"type": "string"}},
                      "required": ["test_id", "value"]}},
    {"name": "browser_click", "description": "Click the button or link with this data-testid and wait for the page.",
     "input_schema": {"type": "object", "properties": {"test_id": {"type": "string"}}, "required": ["test_id"]}},
    {"name": "browser_read", "description": "Read the current screen: URL, visible text and every element with a "
                                            "data-testid and its text. Also returns the raw HTML of those elements.",
     "input_schema": {"type": "object", "properties": {}}},
]

SYSTEM = """You are an autonomous exploratory tester. You test a live application as a black box: you can ONLY
interact with it through your tools{browser_note}. Demo data was just reset.

Goal: check every acceptance criterion of the story, then hunt for bugs around it (boundaries, negative and zero
values, decimals and rounding, state left behind after a refused operation, what the customer actually sees,
security: sessions, other customers' data, HTML/script in text fields).
Think out loud in one short sentence before each action. Whenever behaviour contradicts the story, call
record_finding with the exact steps and what you saw as evidence.
You have a budget of {budget} actions. Finish with a 3-5 line summary of what you covered and what you found."""


class Browser:
    """A real headless Chromium the agent can drive. Each action returns what is now on screen + a screenshot."""

    def __init__(self, base_url: str):
        import asyncio
        import sys

        from playwright.sync_api import sync_playwright

        if sys.platform == "win32":
            # Inside Streamlit on Windows the event-loop policy can be the "selector" one, which cannot start
            # subprocesses; Playwright needs the Proactor loop to launch the browser. Affects new loops only.
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        self.base = base_url.rstrip("/")
        self._pw = sync_playwright().start()
        from .target import launch_browser

        self._browser = launch_browser(self._pw, headless=True)
        self.page = self._browser.new_page(viewport={"width": 1180, "height": 760})
        self.page.set_default_timeout(5000)

    def close(self):
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass

    def _state(self) -> dict:
        p = self.page
        items = p.evaluate("""() => [...document.querySelectorAll('[data-testid]')].slice(0, 60).map(e => ({
            id: e.dataset.testid, text: (e.innerText || e.value || '').trim().slice(0, 120),
            html: e.children.length ? e.innerHTML.trim().slice(0, 160) : ''}))""")
        text = p.inner_text("body")[:1500]
        return {"url": p.url.replace(self.base, ""), "title": p.title(), "elements": items, "text": text}

    def shot(self) -> bytes:
        return self.page.screenshot(type="jpeg", quality=70)

    def act(self, tool: str, args: dict) -> dict:
        p = self.page
        try:
            if tool == "browser_open":
                p.goto(self.base + args["path"])
            elif tool == "browser_fill":
                p.get_by_test_id(args["test_id"]).fill(args["text"])
            elif tool == "browser_select":
                p.get_by_test_id(args["test_id"]).select_option(args["value"])
            elif tool == "browser_click":
                p.get_by_test_id(args["test_id"]).click()
                p.wait_for_load_state()
            return self._state()
        except Exception as e:  # report the failure to the agent instead of crashing the session
            return {"error": str(e).splitlines()[0][:300], **self._state()}


def _http(base_url, method, path, body, headers=None):
    if not path.startswith("/"):
        return {"error": "path must start with /"}
    try:
        r = requests.request(method, base_url.rstrip("/") + path, json=body, headers=headers or {}, timeout=10)
        try:
            payload = r.json()
        except ValueError:
            payload = r.text[:2000]
        return {"status": r.status_code, "body": payload}
    except requests.RequestException as e:
        return {"error": str(e)}


def _req_event(method, path, body, out):
    return {"type": "request", "method": method, "path": path, "request": body,
            "status": out.get("status"), "response": out.get("body"), "error": out.get("error")}


def _describe_action(tool, args):
    return {"browser_open": lambda: f"open {args.get('path')}",
            "browser_fill": lambda: f"type {args.get('text')!r} into {args.get('test_id')}",
            "browser_select": lambda: f"choose {args.get('value')!r} in {args.get('test_id')}",
            "browser_click": lambda: f"click {args.get('test_id')}",
            "browser_read": lambda: "read the screen"}[tool]()


def _browser_event(tool, args, state, shot):
    result = state.get("error") or f"now on {state.get('url')}"
    return {"type": "browser", "action": _describe_action(tool, args), "result": result,
            "url": state.get("url"), "screenshot": shot}


def explore(llm, story: dict, spec: dict, base_url: str, budget: int = 15, emit=lambda e: None) -> dict:
    key = story.get("target", "minibank")
    web = TARGETS[key]["kind"] == "web"
    reset(base_url, key)
    events, findings = [], []

    def push(e):
        events.append(e)
        emit(e)

    browser = Browser(base_url) if web else None
    try:
        if llm.demo:
            if key == "nilebank":
                return _demo_scripted(story, base_url, budget, push, findings, events, browser)
            return _demo_explore(story, base_url, budget, push, findings, events)
        return _model_explore(llm, story, spec, base_url, budget, push, findings, events, browser, key)
    finally:
        if browser:
            browser.close()


def _model_explore(llm, story, spec, base_url, budget, push, findings, events, browser, key):
    """Any real brain (Claude or Ollama) drives the tools through the same tool-session interface."""
    surface = f"API:\n{compact_spec(spec)}"
    if browser:
        surface += f"\n\nScreens (data-testids) discovered by crawling the app:\n{discover_ui(base_url, key)}"
        user, pw = TARGETS[key].get("test_user", ("", ""))
        surface += f"\n\nTest user: {user} / {pw}"
    tools = [HTTP_TOOL] + (BROWSER_TOOLS if browser else []) + [FINDING_TOOL]
    system = SYSTEM.format(budget=budget, browser_note=" (an HTTP client and a real web browser)" if browser else "")
    session = llm.tool_session(system, tools, f"User story:\n{story['text']}\n\n{surface}\n\nStart testing.")
    used, nudged = 0, False
    for _ in range(budget * 2 + 4):
        texts, calls = session.step()
        for t in texts:
            push({"type": "thought", "text": t})
        if not calls:
            if used == 0 and not nudged:   # small local models sometimes describe instead of acting
                nudged = True
                session.messages.append({"role": "user", "content": "Do not describe the plan: call the tools now, "
                                         "one action at a time, and record_finding for each deviation."})
                continue
            break
        results = []
        for c in calls:
            name, args = c["name"], c["input"] or {}
            try:
                if name == "record_finding":
                    f = {k: args.get(k, "") for k in ("title", "criterion", "severity", "evidence")}
                    findings.append(f)
                    push({"type": "finding", **f})
                    out = {"recorded": True}
                elif used >= budget:
                    out = {"error": "BUDGET EXHAUSTED: this action was NOT sent to the app (this is not an app response). Record findings only for responses you actually saw, then write your final summary."}
                elif name == "http_request":
                    used += 1
                    out = _http(base_url, args.get("method", "GET"), args.get("path", "/"), args.get("json_body"),
                                args.get("headers"))
                    push(_req_event(args.get("method", "GET"), args.get("path", "/"), args.get("json_body"), out))
                elif browser and name in {t["name"] for t in BROWSER_TOOLS}:
                    used += 1
                    out = browser.act(name, args) if name != "browser_read" else browser._state()
                    push(_browser_event(name, args, out, browser.shot()))
                else:
                    out = {"error": f"Unknown tool {name}. Available: {[t['name'] for t in tools]}"}
            except Exception as e:  # a bad argument must not end the session: tell the model and continue
                out = {"error": f"{type(e).__name__}: {e}"[:500]}
            results.append((c, out))
        session.answer(results)
    return {"events": events, "findings": findings, "requests_used": used}


def _demo_scripted(story, base_url, budget, push, findings, events, browser):
    """Scripted exploratory session for web apps: a mix of browser steps and API calls."""
    ctx, used = {"base": base_url}, 0
    for thought, tool, args_fn, check in demo_nilebank.explore_plan(story["id"])[:budget]:
        if thought:
            push({"type": "thought", "text": thought})
        args = args_fn(ctx) if callable(args_fn) else (args_fn or {})
        used += 1
        if tool == "http":
            out = _http(base_url, args["method"], args["path"], args.get("json"), args.get("headers"))
            push(_req_event(args["method"], args["path"], args.get("json"), out))
        else:
            out = browser.act(tool, args) if tool != "browser_read" else browser._state()
            push(_browser_event(tool, args, out, browser.shot()))
        verdict = check(out, ctx) if check else None
        if verdict:
            title, criterion, severity, evidence = verdict
            f = {"title": title, "criterion": criterion, "severity": severity, "evidence": evidence}
            findings.append(f)
            push({"type": "finding", **f})
    push({"type": "thought", "text": f"Took {used} actions to explore {story['id']}. "
          + (f"Found {len(findings)} deviation(s) from the story." if findings else "Everything I tried matched the story.")})
    return {"events": events, "findings": findings, "requests_used": used}


def _demo_explore(story, base_url, budget, push, findings, events):
    ctx, used = {}, 0
    for thought, method, path, body_fn, check in demo_data.explore_plan(story["id"])[:budget]:
        push({"type": "thought", "text": thought})
        p = path.format(**ctx)
        body = body_fn(ctx) if body_fn else None
        out = _http(base_url, method, p, body)
        used += 1
        push(_req_event(method, p, body, out))
        if "error" in out:
            continue
        verdict = check(out, ctx)
        if verdict:
            title, criterion = verdict
            f = {"title": title, "criterion": criterion, "severity": "high",
                 "evidence": f"{method} {p} {json.dumps(body) if body else ''} -> {out['status']} {json.dumps(out['body'])}"}
            findings.append(f)
            push({"type": "finding", **f})
    summary = (f"Sent {used} requests to probe {story['id']}. "
               + (f"Found {len(findings)} deviation(s) from the story." if findings else "Everything I probed matched the story."))
    push({"type": "thought", "text": summary})
    return {"events": events, "findings": findings, "requests_used": used}
