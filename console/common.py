"""Shared pieces of the console: sidebar settings, the story picker, and result widgets."""
import os

import pandas as pd
import streamlit as st

from agent import pipeline
from agent.config import DEFAULT_MODEL, TARGETS, default_url, load_stories
from agent.issues import make_tracker
from agent.llm import make_llm, ollama_models
from agent.target import browser_ready, ensure_local_app, health

ss = st.session_state
STEP_KEYS = ("ctx", "cases", "approved", "code", "run", "verdicts", "actions", "explore", "cycle", "saved")
BRAINS = {"Demo (no API key)": "demo", "Ollama (local)": "ollama", "Claude API": "claude"}
STATUS_ICON = {"passed": "✅ passed", "failed": "❌ failed", "error": "⚠️ error", "skipped": "⏭ skipped"}
VERDICT_ICON = {"product_bug": "🐞 product bug", "test_bug": "🔧 test bug", "environment": "🌐 environment"}


def secret(key, default=""):
    try:
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


def init_state():
    for k in STEP_KEYS + ("story_id", "app"):
        ss.setdefault(k, None)


def reset_steps(keep_ctx=False):
    for k in STEP_KEYS:
        if not (keep_ctx and k == "ctx"):
            ss[k] = None


def sidebar() -> dict:
    """All settings live in the sidebar, under the page menu. Returns the lab settings."""
    L = {}
    with st.sidebar:
        st.header("Settings")
        app = st.selectbox("Application under test", list(TARGETS), format_func=lambda k: TARGETS[k]["name"],
                           index=list(TARGETS).index(ss.app) if ss.app in TARGETS else list(TARGETS).index("nilebank"))
        T = TARGETS[app]
        st.caption(T["description"])
        if ss.app != app:
            reset_steps()
            ss.story_id = ss.dash_page = None
            ss.app = app
        where = st.radio("Run it", [f"Start {T['name']} here", "External URL"], label_visibility="collapsed")
        if where == "External URL":
            base_url = st.text_input("Base URL", value=secret(f"{app.upper()}_URL", default_url(app))).rstrip("/")
        else:
            fixed = st.toggle("Developer fix deployed", value=False,
                              help=f"Restarts {T['name']} with {T['fixed_env']}=1, simulating developers shipping the fixes.")
            try:
                with st.spinner(f"Starting {T['name']}..."):
                    base_url = ensure_local_app(app, fixed)
            except RuntimeError as e:
                st.error(str(e))
                st.stop()
        h = health(base_url, app)
        if h:
            st.success(f"{T['name']} is up · build: **{h.get('build')}**")
            links = [f"[API docs]({base_url}/docs)"]
            if T["kind"] == "web":
                links.insert(0, f"[Open the app ↗]({base_url})")
            st.markdown(" · ".join(links))
            if T["kind"] == "web":
                st.caption("Sign in as **amira** / **Nile@2026**")
                ok, msg = browser_ready()
                if ok:
                    st.caption(f"UI tests: {msg}")
                else:
                    st.warning("**No browser for UI tests.** Install Microsoft Edge or Google Chrome, or run "
                               "`python -m playwright install chromium`, then restart Streamlit.")
        else:
            st.error(f"Cannot reach {base_url}")

        st.subheader("Agent brain")
        brain = st.radio("Agent brain", list(BRAINS), label_visibility="collapsed", key="brain_choice",
                         help="Demo replays scripted reasoning. Ollama runs a real model on this PC (nothing leaves "
                              "the machine). Claude API is the strongest brain and needs an API key.")
        api_key, model, ollama_url = "", DEFAULT_MODEL, secret("OLLAMA_URL", "http://localhost:11434")
        if brain == "Claude API":
            api_key = st.text_input("Anthropic API key", value=secret("ANTHROPIC_API_KEY"), type="password")
            model = st.text_input("Model", value=secret("CLAUDE_MODEL", DEFAULT_MODEL))
        elif brain == "Ollama (local)":
            ollama_url = st.text_input("Ollama URL", value=ollama_url)
            names, why = ollama_models(ollama_url)
            if names:
                chat = [n for n in names if not any(k in n for k in ("embed", "bge", "llava"))] or names
                pref = next((n for n in ("qwen2.5-coder:7b", "qwen2.5:7b-instruct", "llama3.1:8b") if n in chat), chat[0])
                want = secret("OLLAMA_MODEL", pref)
                model = st.selectbox("Model", chat, index=chat.index(want) if want in chat else chat.index(pref),
                                     help="Best here: qwen2.5-coder:7b. Explore live needs a model with tools: "
                                          "qwen2.5 and llama3.1 have them; deepseek-r1 and llava don't.")
                st.caption("A 7-8B model on a laptop CPU takes a few minutes per story. Its bug verdicts are "
                           "marked **needs human review**.")
            else:
                st.error(why)
                model = ""

        st.subheader("Bug tracker")
        tracker_kind = st.radio("Issues go to", ["Local file", "GitHub Issues"], label_visibility="collapsed",
                                key="tracker_choice")
        repo = token = ""
        if tracker_kind == "GitHub Issues":
            repo = st.text_input("Repository (owner/name)", value=secret("GITHUB_REPO"))
            token = st.text_input("GitHub token (issues: write)", value=secret("GITHUB_TOKEN"), type="password")
    L.update(app=app, T=T, base_url=base_url, healthy=bool(h), build=(h or {}).get("build", "unknown"),
             brain=BRAINS[brain], brain_label=brain, api_key=api_key, model=model, ollama_url=ollama_url,
             tracker_kind=tracker_kind, repo=repo, token=token)
    ss.lab = L
    return L


def get_llm(L):
    try:
        return make_llm(brain=L["brain"], api_key=L["api_key"], model=L["model"], ollama_url=L["ollama_url"])
    except Exception as e:
        st.error(f"Agent brain not ready: {e}")
        st.stop()


def get_tracker(L):
    try:
        return make_tracker("github" if L["tracker_kind"] == "GitHub Issues" else "local", L["repo"], L["token"])
    except Exception as e:
        st.error(f"Bug tracker not ready: {e}")
        st.stop()


def pick_story(L, label="User story") -> dict:
    """Story picker shared by every activity page (the choice follows you from page to page)."""
    stories = load_stories(L["app"])
    ids = [s["id"] for s in stories]
    by_id = {s["id"]: s for s in stories}
    idx = ids.index(ss.story_id) if ss.story_id in ids else 0
    sid = st.selectbox(label, ids, index=idx, format_func=lambda i: f"{i}: {by_id[i]['title']}")
    if ss.story_id != sid:
        reset_steps()
        ss.story_id = sid
    story = by_id[sid]
    with st.expander("Read the story", expanded=False):
        st.markdown(story["text"])
    return story


def get_ctx(L, story):
    if ss.ctx is None or ss.ctx.get("target") != L["app"]:
        ss.ctx = pipeline.discover(story, L["base_url"])
    return ss.ctx


def header(title, intro, L=None):
    st.title(title)
    if intro:
        st.markdown(intro)


def need(cond, msg, page=None, label=None):
    """Show a friendly 'do this first' message with a link, and stop the page."""
    if cond:
        return
    st.info(msg)
    if page:
        st.page_link(page, label=label or "Go there", icon="👉")
    st.stop()


def show_run(run):
    s = run["summary"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tests", s["total"])
    c2.metric("Passed", s["passed"])
    c3.metric("Failed", s["failed"])
    c4.metric("Errors", s["error"])
    df = pd.DataFrame([{"Case": c["tc_id"] or "-", "Status": STATUS_ICON.get(c["status"], c["status"]),
                        "Message": (c["message"] or "").splitlines()[0][:160] if c["message"] else ""}
                       for c in run["cases"]])
    st.dataframe(df, hide_index=True, width="stretch")
    if run.get("output"):
        with st.expander("Raw pytest output"):
            st.code(run["output"] or "(empty)", language="text")


def show_verdicts(verdicts):
    if not verdicts:
        st.success("No failures to triage.")
        return
    for v in verdicts:
        with st.container(border=True):
            st.markdown(f"**{v.get('tc_id')}** · {VERDICT_ICON.get(v['verdict'], v['verdict'])} · "
                        f"severity *{v.get('severity', '?')}* · confidence {v.get('confidence', '?')}")
            st.markdown(f"**{v.get('title', '')}**")
            st.caption(v.get("reasoning", ""))
            if v.get("needs_review"):
                st.warning("Needs human review: verdict from a local model. Check the test's expected value "
                           "against the story before treating this as an app bug.")
            st.markdown(f"Expected: {v.get('expected', '')}  \nActual: `{v.get('actual', '')}`")


def show_actions(actions):
    for a in actions or []:
        icon = {"opened": "🆕", "closed": "✅", "still open": "⏳"}.get(a["action"], "•")
        st.markdown(f"{icon} **{a['action']}** [#{a['issue']['number']} {a['issue']['title']}]({a['issue']['url']})")


def saved_badge(manifest):
    if manifest:
        st.success(f"📦 Saved as **{manifest['version']}** in `artifacts/{manifest['app']}/{manifest['story']}/"
                   f"{manifest['version']}/` (see the Artifacts page).")


def save_step_version(L, story, stage):
    """Freeze what the step-by-step pages have produced so far as a new artifact version."""
    result = {"target": L["app"], "brain": get_llm(L).label if L["brain"] != "demo" else "Demo (scripted)",
              "cases": ss.approved or ss.cases, "code": ss.code, "run": ss.run, "verdicts": ss.verdicts,
              "actions": ss.actions, "repairs": ss.get("repairs_done", 0)}
    report = None
    if ss.run:
        report = pipeline.write_report(story, {**result, "verdicts": ss.verdicts or [], "actions": ss.actions or [],
                                               "repairs": result["repairs"]})
    ss.saved = pipeline.save_artifacts(story, result, L["base_url"], report, stage=stage)
    return ss.saved
