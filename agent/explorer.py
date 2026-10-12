"""Exploratory testing: the agent drives the live app itself through an HTTP tool, step by step.

With Claude this is a real tool-use loop: Claude decides each request, reads the response, and
records findings. In demo mode a scripted session plays the same role.
"""
import json

import requests

from . import demo_data
from .target import compact_spec

TOOLS = [
    {
        "name": "http_request",
        "description": "Send one HTTP request to the application under test and get the status code and JSON body. "
                       "Paths are relative, e.g. /accounts or /accounts/ACC-0001/deposit.",
        "input_schema": {
            "type": "object",
            "properties": {
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"]},
                "path": {"type": "string"},
                "json_body": {"type": "object", "description": "JSON request body, if any"},
            },
            "required": ["method", "path"],
        },
    },
    {
        "name": "record_finding",
        "description": "Record a behaviour that contradicts the user story. Include the exact request and response as evidence.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "criterion": {"type": "string", "description": "Which acceptance criterion, e.g. AC2"},
                "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
                "evidence": {"type": "string"},
            },
            "required": ["title", "severity", "evidence"],
        },
    },
]

SYSTEM = """You are an autonomous exploratory tester. You test a live REST API as a black box: you can
ONLY interact with it through the http_request tool. Data was just reset.

Goal: check every acceptance criterion of the story, then hunt for bugs around it (boundaries,
negative and zero values, decimals and rounding, state left behind after a refused operation).
Think out loud in one short sentence before each request. Whenever behaviour contradicts the
story, call record_finding with the exact request and response as evidence.
You have a budget of {budget} HTTP requests. Finish with a 3-5 line summary of what you covered
and what you found."""


def _http(base_url, method, path, body):
    if not path.startswith("/"):
        return {"error": "path must start with /"}
    try:
        r = requests.request(method, base_url.rstrip("/") + path, json=body, timeout=10)
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


def explore(llm, story: dict, spec: dict, base_url: str, budget: int = 15, emit=lambda e: None) -> dict:
    requests.post(base_url.rstrip("/") + "/reset", timeout=10)
    events, findings = [], []

    def push(e):
        events.append(e)
        emit(e)

    if llm.demo:
        return _demo_explore(story, base_url, budget, push, findings, events)

    messages = [{"role": "user", "content": f"User story:\n{story['text']}\n\nAPI:\n{compact_spec(spec)}\n\nStart testing."}]
    used = 0
    for _ in range(budget * 2 + 4):
        resp = llm.client.messages.create(model=llm.model, max_tokens=2000, system=SYSTEM.format(budget=budget),
                                          tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        for b in resp.content:
            if b.type == "text" and b.text.strip():
                push({"type": "thought", "text": b.text.strip()})
        if resp.stop_reason != "tool_use":
            break
        results = []
        for b in resp.content:
            if b.type != "tool_use":
                continue
            if b.name == "http_request":
                if used >= budget:
                    out = {"error": "Request budget exhausted. Write your final summary now."}
                else:
                    used += 1
                    out = _http(base_url, b.input["method"], b.input["path"], b.input.get("json_body"))
                    push(_req_event(b.input["method"], b.input["path"], b.input.get("json_body"), out))
            else:
                findings.append(dict(b.input))
                push({"type": "finding", **b.input})
                out = {"recorded": True}
            results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out)[:4000]})
        messages.append({"role": "user", "content": results})
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
