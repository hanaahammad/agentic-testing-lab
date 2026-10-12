"""Everything about the application under test: starting it, checking it, discovering its API."""
import atexit
import os
import subprocess
import sys
import time

import requests

from .config import ROOT

_state = {"proc": None, "fixed": None, "port": None}


def health(base_url: str) -> dict | None:
    try:
        r = requests.get(base_url.rstrip("/") + "/health", timeout=1.5)
        return r.json() if r.ok else None
    except (requests.RequestException, ValueError):
        return None


def stop_local_app():
    p = _state["proc"]
    if p and p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    _state.update(proc=None, fixed=None, port=None)


atexit.register(stop_local_app)


def ensure_local_app(port: int = 8000, fixed: bool = False) -> str:
    """Start MiniBank as a subprocess (or reuse it) with the requested build. Returns its base URL."""
    url = f"http://127.0.0.1:{port}"
    want = "fixed" if fixed else "buggy"
    h = health(url)
    if h and h.get("build") == want:
        return url
    if h and _state["proc"] is None:
        raise RuntimeError(
            f"Port {port} is already serving a '{h.get('build')}' MiniBank that this session did not start. "
            f"Stop it, or restart it with MINIBANK_FIXED={'1' if fixed else '0'}."
        )
    stop_local_app()
    env = {**os.environ, "MINIBANK_FIXED": "1" if fixed else "0"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app_under_test.minibank:app",
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    _state.update(proc=proc, fixed=fixed, port=port)
    for _ in range(75):
        h = health(url)
        if h and h.get("build") == want:
            return url
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    raise RuntimeError("MiniBank did not start. Is uvicorn installed?")


def fetch_openapi(base_url: str) -> dict:
    r = requests.get(base_url.rstrip("/") + "/openapi.json", timeout=10)
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
    schemas = spec.get("components", {}).get("schemas", {})
    for name, sch in schemas.items():
        if name.startswith(("HTTPValidationError", "ValidationError")):
            continue
        props = ", ".join(f"{k}: {v.get('type', '?')}" for k, v in sch.get("properties", {}).items())
        lines.append(f"schema {name} {{{props}}} required={sch.get('required', [])}")
    return "\n".join(lines)
