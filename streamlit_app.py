"""Agentic Testing Lab: the console where you drive (or watch) the QA agent test an application.

Two applications under test: MiniBank (a tiny REST API) and NileBank (an online-banking web app,
tested through its screens with Playwright and through its API).

Run locally:   streamlit run streamlit_app.py
Deploy:        Streamlit Community Cloud, main file = streamlit_app.py
"""
import os
import re

import pandas as pd
import streamlit as st

from agent import pipeline
from agent.config import DEFAULT_MODEL, TARGETS, default_url, load_stories
from agent.explorer import explore
from agent.issues import make_tracker, sync_issues
from agent.llm import make_llm, ollama_models
from agent.target import BROWSER_FIX, browser_ready, endpoint_table, ensure_local_app, fetch_openapi, health

st.set_page_config(page_title="Agentic Testing Lab", page_icon="🧪", layout="wide")


def secret(key, default=""):
    try:
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


STEP_KEYS = ("ctx", "cases", "approved", "code", "run", "verdicts", "actions", "explore", "cycle")
ss = st.session_state
for k in STEP_KEYS + ("story_id", "app"):
    ss.setdefault(k, None)

# ---------------- Sidebar: settings ----------------
with st.sidebar:
    st.header("Settings")
    st.subheader("Application under test")
    app = st.selectbox("Application", list(TARGETS), format_func=lambda k: TARGETS[k]["name"],
                       index=list(TARGETS).index("nilebank"))
    T = TARGETS[app]
    st.caption(T["description"])
    if ss.app != app:
        for k in STEP_KEYS + ("story_id", "dash_page"):
            ss[k] = None
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
                st.warning("**No browser for UI tests.** The lab uses Playwright's Chromium, or else the Microsoft "
                           "Edge / Google Chrome installed on this PC. Install one of them, or run "
                           "`python -m playwright install chromium`, then restart Streamlit.")
    else:
        st.error(f"Cannot reach {base_url}")

    st.subheader("Agent brain")
    brain = st.radio("Agent brain", ["Demo (no API key)", "Ollama (local)", "Claude API"],
                     label_visibility="collapsed",
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
            model = st.selectbox("Model", chat, index=chat.index(secret("OLLAMA_MODEL", pref))
                                 if secret("OLLAMA_MODEL", pref) in chat else chat.index(pref),
                                 help="Best here: qwen2.5-coder:7b (writes the tests). The model must support tools "
                                      "for Explore live: qwen2.5 and llama3.1 do; deepseek-r1 and llava don't.")
            st.caption("A 7-8B model on a laptop CPU takes a few minutes per story. Results are real, "
                       "but expect more script repairs than with Claude.")
        else:
            st.error(why)
            model = ""

    st.subheader("Bug tracker")
    tracker_kind = st.radio("Issues go to", ["Local file", "GitHub Issues"], label_visibility="collapsed")
    repo = token = ""
    if tracker_kind == "GitHub Issues":
        repo = st.text_input("Repository (owner/name)", value=secret("GITHUB_REPO"))
        token = st.text_input("GitHub token (issues: write)", value=secret("GITHUB_TOKEN"), type="password")


def get_llm():
    try:
        kind = {"Demo (no API key)": "demo", "Ollama (local)": "ollama", "Claude API": "claude"}[brain]
        return make_llm(brain=kind, api_key=api_key, model=model, ollama_url=ollama_url)
    except Exception as e:
        st.error(f"Agent brain not ready: {e}")
        st.stop()


def get_tracker():
    try:
        return make_tracker("github" if tracker_kind == "GitHub Issues" else "local", repo, token)
    except Exception as e:
        st.error(f"Bug tracker not ready: {e}")
        st.stop()


def get_ctx():
    if ss.ctx is None:
        ss.ctx = pipeline.discover(story, base_url)
    return ss.ctx


# ---------------- Header + story ----------------
st.title("🧪 Agentic Testing Lab")
st.caption(f"A QA agent that reads a user story, designs tests, writes the scripts, runs them against **{T['name']}**"
           + (" (through its screens and its API)" if T["kind"] == "web" else "")
           + ", triages failures, repairs its own broken tests, and files or closes GitHub Issues.")

stories = load_stories(app)
labels = {f"{s['id']}: {s['title']}": s for s in stories}
story = labels[st.selectbox("User story", list(labels))]
if ss.story_id != story["id"]:
    for k in STEP_KEYS:
        if k != "ctx":
            ss[k] = None
    ss.story_id = story["id"]
with st.expander("Read the story", expanded=False):
    st.markdown(story["text"])

STATUS_ICON = {"passed": "✅ passed", "failed": "❌ failed", "error": "⚠️ error", "skipped": "⏭ skipped"}
VERDICT_ICON = {"product_bug": "🐞 product bug", "test_bug": "🔧 test bug", "environment": "🌐 environment"}


def show_run(run):
    s = run["summary"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tests", s["total"])
    c2.metric("Passed", s["passed"])
    c3.metric("Failed", s["failed"])
    c4.metric("Errors", s["error"])
    df = pd.DataFrame([{"Case": c["tc_id"] or "-", "Status": STATUS_ICON[c["status"]],
                        "Message": (c["message"] or "").splitlines()[0][:160] if c["message"] else ""}
                       for c in run["cases"]])
    st.dataframe(df, hide_index=True, width="stretch")
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


tabs = st.tabs(["⚡ Full cycle", "1 · Design", "2 · Scripts", "3 · Run", "4 · Triage & issues",
                "🤖 Explore live", "📋 Issues board", "📊 Dashboard"])

# ---------------- Full cycle ----------------
with tabs[0]:
    st.markdown("One click runs the whole loop with **auto-approval**. Run it on the buggy build, then switch on "
                "**Developer fix deployed** in the sidebar and run it again: the agent closes the issues it opened.")
    if T["kind"] == "web":
        st.caption("UI tests run in a real headless Chrome (Playwright), so a NileBank cycle takes a little longer.")
    if st.button("Run full cycle", type="primary"):
        llm, tracker = get_llm(), get_tracker()
        with st.status("Agent at work...", expanded=True) as status:
            try:
                ss.cycle = pipeline.full_cycle(llm, story, base_url, tracker=tracker, log=st.write)
                status.update(label="Cycle complete", state="complete")
            except Exception as e:
                status.update(label="Cycle failed", state="error")
                st.exception(e)
    if ss.cycle:
        st.subheader("Results")
        show_run(ss.cycle["run"])
        if ss.cycle["repairs"]:
            st.info(f"The agent repaired its own test script {ss.cycle['repairs']} time(s) before filing bugs.")
        st.subheader("Triage")
        show_verdicts(ss.cycle["verdicts"])
        st.subheader("Bug tracker actions")
        if ss.cycle["actions"]:
            show_actions(ss.cycle["actions"])
        else:
            st.caption("No changes to the tracker.")

# ---------------- 1. Design ----------------
with tabs[1]:
    st.markdown("The agent reads the API description (`/openapi.json`)"
                + (" and **walks through the screens** as a test user, noting every field and button"
                   if T["kind"] == "web" else "")
                + ", like a tester on day one, then turns each acceptance criterion into test cases. "
                  "**You approve** which ones to automate.")
    if st.button("Discover & design tests"):
        with st.spinner("Discovering and designing test cases..."):
            ss.ctx = pipeline.discover(story, base_url)
            ss.cases = pipeline.design_tests(get_llm(), story, ss.ctx)
            ss.code = ss.run = ss.verdicts = ss.actions = None
    if ss.ctx:
        c1, c2 = st.columns(2)
        with c1.expander(f"API: {len(endpoint_table(ss.ctx['spec']))} endpoints discovered"):
            st.dataframe(pd.DataFrame(endpoint_table(ss.ctx["spec"])), hide_index=True, width="stretch")
        if ss.ctx.get("ui_map"):
            with c2.expander(f"Screens: {ss.ctx['ui_map'].count('PAGE ')} pages discovered"):
                st.code(ss.ctx["ui_map"], language="text")
    if ss.cases:
        df = pd.DataFrame([{"Approve": True, "ID": c["id"], "Criterion": c.get("criterion", ""),
                            "Via": c.get("interface", "API"), "Type": c.get("type", ""), "Title": c["title"],
                            "Steps": " → ".join(c.get("steps", [])), "Expected": c.get("expected", "")}
                           for c in ss.cases])
        edited = st.data_editor(df, hide_index=True, width="stretch",
                                disabled=["ID", "Criterion", "Via", "Type", "Steps"],
                                column_config={"Approve": st.column_config.CheckboxColumn(help="Human gate")})
        keep = set(edited.loc[edited["Approve"], "ID"])
        ss.approved = [c for c in ss.cases if c["id"] in keep]
        st.caption(f"{len(ss.approved)} of {len(ss.cases)} cases approved for automation.")

# ---------------- 2. Scripts ----------------
with tabs[2]:
    if not ss.approved:
        st.info("Design and approve test cases first (tab 1).")
    else:
        if st.button("Write pytest script from approved cases"):
            with st.spinner("Writing the script..."):
                ss.code = pipeline.generate_script(get_llm(), story, ss.approved, get_ctx())
                pipeline.save_script(story, ss.code)
                ss.run = ss.verdicts = ss.actions = None
        if ss.code:
            st.caption(f"Saved to `{pipeline.script_path(story).relative_to(pipeline.ROOT)}`. "
                       "You can edit it here; commit it to GitHub so CI runs it on every push.")
            new = st.text_area("Generated test script", ss.code, height=460)
            if new != ss.code and st.button("Save my edits"):
                ss.code = new
                pipeline.save_script(story, new)
                st.success("Saved.")

# ---------------- 3. Run ----------------
with tabs[3]:
    if not ss.code:
        st.info("Generate a script first (tab 2).")
    else:
        if st.button(f"Run tests against {T['name']}", type="primary"):
            with st.spinner("Running pytest" + (" with Playwright..." if T["kind"] == "web" else "...")):
                ss.run = pipeline.run_tests(pipeline.script_path(story), base_url, app)
                ss.verdicts = ss.actions = None
        if ss.run:
            show_run(ss.run)

# ---------------- 4. Triage & issues ----------------
with tabs[4]:
    if not ss.run:
        st.info("Run the tests first (tab 3).")
    else:
        st.markdown("For each failure the agent decides: **product bug** (the app breaks the story), "
                    "**test bug** (its own script is wrong), or **environment**.")
        if st.button("Triage failures"):
            with st.spinner("Triaging..."):
                ss.verdicts = pipeline.triage(get_llm(), story, ss.approved or ss.cases or [], ss.code, ss.run, get_ctx())
        if ss.verdicts is not None:
            show_verdicts(ss.verdicts)
            c1, c2 = st.columns(2)
            if any(v["verdict"] == "test_bug" for v in ss.verdicts) and c1.button("🔧 Let the agent repair its script and re-run"):
                with st.spinner("Repairing and re-running..."):
                    llm = get_llm()
                    ss.code = pipeline.repair_script(llm, story, ss.code, ss.verdicts, ss.run, get_ctx(), ss.approved or ss.cases or [])
                    pipeline.save_script(story, ss.code)
                    ss.run = pipeline.run_tests(pipeline.script_path(story), base_url, app)
                    ss.verdicts = pipeline.triage(llm, story, ss.approved or ss.cases or [], ss.code, ss.run, get_ctx())
                st.rerun()
            if c2.button("Sync bug tracker (open new bugs, close fixed ones)"):
                ss.actions = sync_issues(get_tracker(), story, ss.run, ss.verdicts)
            if ss.actions is not None:
                if ss.actions:
                    show_actions(ss.actions)
                else:
                    st.caption("Nothing to change in the tracker.")

# ---------------- Explore live ----------------
with tabs[5]:
    if T["kind"] == "web":
        st.markdown("Here the agent **tests the app itself**, with no script. It drives a **real browser** (opens pages, "
                    "types, clicks, reads the screen) and calls the API, decides what to try next from what it sees, "
                    "and records findings. Every browser step is captured as a screenshot.")
    else:
        st.markdown("Here the agent **tests the app itself**: no script, it sends HTTP requests one at a time, "
                    "reads each response, decides what to try next, and records findings.")
    st.caption("With Claude or Ollama this is a real tool-use loop; the demo brain replays a scripted session.")
    budget = st.slider("Action budget", 5, 40, 15)
    show_shots = T["kind"] == "web" and st.toggle("Show screenshots", value=True)
    if st.button("Start exploratory session", type="primary"):
        feed = st.container(border=True)

        def emit(e):
            if e["type"] == "thought":
                feed.markdown(f"💭 {e['text']}")
            elif e["type"] == "request":
                req = f" `{e['request']}`" if e.get("request") else ""
                feed.markdown(f"➡️ API `{e['method']} {e['path']}`{req} → **{e.get('status') or e.get('error')}** "
                              f"`{str(e.get('response'))[:220]}`")
            elif e["type"] == "browser":
                feed.markdown(f"🖱️ Browser: **{e['action']}** → {e.get('result', '')}")
                if show_shots and e.get("screenshot") and e["action"].startswith(("click", "read", "open")):
                    feed.image(e["screenshot"], width=560)
            else:
                feed.error(f"🐞 [{e.get('criterion', '')}] {e['title']}  \n{e.get('evidence', '')[:300]}")

        with st.spinner("Exploring..."):
            try:
                ss.explore = explore(get_llm(), story, fetch_openapi(base_url, app), base_url, budget, emit=emit)
            except Exception as e:
                st.exception(e)
    if ss.explore:
        st.subheader(f"Findings ({len(ss.explore['findings'])}) · {ss.explore['requests_used']} actions used")
        if ss.explore["findings"]:
            st.dataframe(pd.DataFrame(ss.explore["findings"]), hide_index=True, width="stretch")
        st.caption("Exploration finds bugs; scripted tests keep them found. Turn a finding into a permanent test "
                   "by adding it as an acceptance criterion and running the cycle.")

# ---------------- Issues board ----------------
with tabs[6]:
    try:
        issues = get_tracker().list()
    except Exception as e:
        st.error(f"Could not read the tracker: {e}")
        issues = []
    story_nums = {s["id"].split("-")[1] for s in stories}
    mine = [i for i in issues if (m := re.match(r"\[TC-(\d+)-", i["title"])) and m.group(1) in story_nums]
    if not mine:
        st.caption(f"No agent-found {T['name']} issues yet. Run the full cycle on the buggy build.")
    else:
        df = pd.DataFrame([{"#": i["number"], "State": "🟢 open" if i["state"] == "open" else "✅ closed",
                            "Title": i["title"], "Opened": i.get("opened", ""), "Closed": i.get("closed", ""),
                            "Link": i["url"]} for i in mine])
        st.dataframe(df, hide_index=True, width="stretch",
                     column_config={"Link": st.column_config.LinkColumn(display_text="open")})

# ---------------- Dashboard (D3Blocks) ----------------
with tabs[7]:
    from agent import dashboard as dash

    history = dash.load_history(app)
    c1, c2, c3 = st.columns([1.2, 1.6, 3])
    build_clicked = c1.button("Build / refresh", type="primary", width="stretch")
    seed_clicked = c2.button("Seed demo history", width="stretch",
                             help="Runs the demo cycle three times (buggy → fix → regression) so the charts have a trend.")
    c3.caption(f"{len(history)} {T['name']} runs recorded · charts by D3Blocks · also saved as "
               f"`dashboard/{app}/index.html`, a single file you can open in any browser or attach to an email.")
    try:
        if seed_clicked:
            with st.spinner("Running three demo cycles (this takes a minute for NileBank)..."):
                dash.seed_history(app)
                history = dash.load_history(app)
                build_clicked = True
        if build_clicked:
            if not history:
                st.warning("No runs recorded yet. Run the full cycle first, or seed the demo history.")
            else:
                with st.spinner("Building D3Blocks charts..."):
                    paths = dash.build_charts(history)
                    dash.build_index(history, paths)                            # standalone file, with full-screen links
                    ss.dash_page = dash.build_index(history, paths, links=False)  # embedded copy for this tab
                    ss.dash_height = dash.page_height(paths)
    except ImportError:
        st.error("D3Blocks is not installed. Run `pip install d3blocks` in your venv, then restart Streamlit.")
    if ss.get("dash_page"):
        page_html = ss.dash_page.read_text(encoding="utf-8")
        if hasattr(st, "iframe"):
            st.iframe(page_html, height=ss.dash_height)
        else:  # older Streamlit
            import streamlit.components.v1 as components

            components.html(page_html, height=ss.dash_height, scrolling=True)
        st.download_button("Download dashboard (single HTML file)", ss.dash_page.read_bytes(),
                           file_name=f"qa-dashboard-{app}.html", mime="text/html")
    elif history:
        st.info("Click **Build / refresh** to draw the dashboard.")
