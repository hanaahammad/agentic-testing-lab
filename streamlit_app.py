"""Agentic Testing Lab: the console where you drive (or watch) the QA agent test MiniBank.

Run locally:   streamlit run streamlit_app.py
Deploy:        Streamlit Community Cloud, main file = streamlit_app.py
"""
import os

import pandas as pd
import streamlit as st

from agent import pipeline
from agent.config import DEFAULT_MODEL, DEFAULT_PORT, load_stories
from agent.explorer import explore
from agent.issues import make_tracker, sync_issues
from agent.llm import make_llm
from agent.target import endpoint_table, ensure_local_app, fetch_openapi, health

st.set_page_config(page_title="Agentic Testing Lab", page_icon="🧪", layout="wide")


def secret(key, default=""):
    try:
        return st.secrets.get(key, os.getenv(key, default))
    except Exception:
        return os.getenv(key, default)


ss = st.session_state
for k in ("spec", "cases", "approved", "code", "run", "verdicts", "actions", "explore", "story_id", "cycle"):
    ss.setdefault(k, None)

# ---------------- Sidebar: settings ----------------
with st.sidebar:
    st.header("Settings")
    brain = st.radio("Agent brain", ["Demo (no API key)", "Claude API"],
                     help="Demo replays scripted reasoning so you can see the whole cycle for free.")
    api_key, model = "", DEFAULT_MODEL
    if brain == "Claude API":
        api_key = st.text_input("Anthropic API key", value=secret("ANTHROPIC_API_KEY"), type="password")
        model = st.text_input("Model", value=secret("CLAUDE_MODEL", DEFAULT_MODEL))

    st.subheader("Application under test")
    target = st.radio("Target", ["Start MiniBank here", "External URL"])
    if target == "External URL":
        base_url = st.text_input("Base URL", value=secret("BASE_URL", "http://127.0.0.1:8000")).rstrip("/")
    else:
        fixed = st.toggle("Developer fix deployed", value=False,
                          help="Restarts MiniBank with MINIBANK_FIXED=1, simulating a developer shipping the fixes.")
        try:
            with st.spinner("Starting MiniBank..."):
                base_url = ensure_local_app(DEFAULT_PORT, fixed)
        except RuntimeError as e:
            st.error(str(e))
            st.stop()
    h = health(base_url)
    if h:
        st.success(f"MiniBank is up · build: **{h.get('build')}**")
        st.caption(f"{base_url} · [API docs]({base_url}/docs)" if target == "External URL" else base_url)
    else:
        st.error(f"Cannot reach {base_url}")

    st.subheader("Bug tracker")
    tracker_kind = st.radio("Issues go to", ["Local file", "GitHub Issues"])
    repo = token = ""
    if tracker_kind == "GitHub Issues":
        repo = st.text_input("Repository (owner/name)", value=secret("GITHUB_REPO"))
        token = st.text_input("GitHub token (issues: write)", value=secret("GITHUB_TOKEN"), type="password")


def get_llm():
    try:
        return make_llm(brain.startswith("Demo"), api_key, model)
    except Exception as e:
        st.error(f"Agent brain not ready: {e}")
        st.stop()


def get_tracker():
    try:
        return make_tracker("github" if tracker_kind == "GitHub Issues" else "local", repo, token)
    except Exception as e:
        st.error(f"Bug tracker not ready: {e}")
        st.stop()


# ---------------- Header + story ----------------
st.title("🧪 Agentic Testing Lab")
st.caption("A QA agent that reads a user story, designs tests, writes the scripts, runs them against MiniBank, "
           "triages failures, repairs its own broken tests, and files or closes GitHub Issues.")

stories = load_stories()
labels = {f"{s['id']}: {s['title']}": s for s in stories}
story = labels[st.selectbox("User story", list(labels))]
if ss.story_id != story["id"]:
    for k in ("cases", "approved", "code", "run", "verdicts", "actions", "explore", "cycle"):
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
            st.markdown(f"Expected: {v.get('expected', '')}  \nActual: `{v.get('actual', '')}`")


def show_actions(actions):
    for a in actions or []:
        icon = {"opened": "🆕", "closed": "✅", "still open": "⏳"}.get(a["action"], "•")
        st.markdown(f"{icon} **{a['action']}** [#{a['issue']['number']} {a['issue']['title']}]({a['issue']['url']})")


tabs = st.tabs(["⚡ Full cycle", "1 · Design", "2 · Scripts", "3 · Run", "4 · Triage & issues",
                "🤖 Explore live", "📋 Issues board"])

# ---------------- Full cycle ----------------
with tabs[0]:
    st.markdown("One click runs the whole loop with **auto-approval**. Run it on the buggy build, then switch on "
                "**Developer fix deployed** in the sidebar and run it again: the agent closes the issues it opened.")
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
    st.markdown("The agent reads the API description (`/openapi.json`), like a tester reading the docs, "
                "then turns each acceptance criterion into test cases. **You approve** which ones to automate.")
    if st.button("Discover API & design tests"):
        with st.spinner("Designing test cases..."):
            ss.spec = fetch_openapi(base_url)
            ss.cases = pipeline.design_tests(get_llm(), story, ss.spec)
            ss.code = ss.run = ss.verdicts = ss.actions = None
    if ss.spec:
        with st.expander("Endpoints discovered"):
            st.dataframe(pd.DataFrame(endpoint_table(ss.spec)), hide_index=True, width="stretch")
    if ss.cases:
        df = pd.DataFrame([{"Approve": True, "ID": c["id"], "Criterion": c.get("criterion", ""), "Type": c.get("type", ""),
                            "Title": c["title"], "Steps": " → ".join(c.get("steps", [])), "Expected": c.get("expected", "")}
                           for c in ss.cases])
        edited = st.data_editor(df, hide_index=True, width="stretch", disabled=["ID", "Criterion", "Type", "Steps"],
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
                ss.code = pipeline.generate_script(get_llm(), story, ss.approved, ss.spec)
                pipeline.save_script(story["id"], ss.code)
                ss.run = ss.verdicts = ss.actions = None
        if ss.code:
            st.caption(f"Saved to `{pipeline.script_path(story['id']).relative_to(pipeline.ROOT)}`. "
                       "You can edit it here; commit it to GitHub so CI runs it on every push.")
            new = st.text_area("Generated test script", ss.code, height=420)
            if new != ss.code and st.button("Save my edits"):
                ss.code = new
                pipeline.save_script(story["id"], new)
                st.success("Saved.")

# ---------------- 3. Run ----------------
with tabs[3]:
    if not ss.code:
        st.info("Generate a script first (tab 2).")
    else:
        if st.button("Run tests against MiniBank", type="primary"):
            with st.spinner("Running pytest..."):
                ss.run = pipeline.run_tests(pipeline.script_path(story["id"]), base_url)
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
                ss.verdicts = pipeline.triage(get_llm(), story, ss.approved or ss.cases or [], ss.code, ss.run, ss.spec or fetch_openapi(base_url))
        if ss.verdicts is not None:
            show_verdicts(ss.verdicts)
            c1, c2 = st.columns(2)
            if any(v["verdict"] == "test_bug" for v in ss.verdicts) and c1.button("🔧 Let the agent repair its script and re-run"):
                with st.spinner("Repairing and re-running..."):
                    llm = get_llm()
                    ss.code = pipeline.repair_script(llm, story, ss.code, ss.verdicts, ss.run, ss.spec or fetch_openapi(base_url))
                    pipeline.save_script(story["id"], ss.code)
                    ss.run = pipeline.run_tests(pipeline.script_path(story["id"]), base_url)
                    ss.verdicts = pipeline.triage(llm, story, ss.approved or ss.cases or [], ss.code, ss.run, ss.spec or fetch_openapi(base_url))
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
    st.markdown("Here the agent **tests the app itself**: no script, it sends HTTP requests one at a time, "
                "reads each response, decides what to try next, and records findings. "
                "With the Claude brain this is a real tool-use loop.")
    budget = st.slider("Request budget", 5, 40, 15)
    if st.button("Start exploratory session", type="primary"):
        feed = st.container(border=True)

        def emit(e):
            if e["type"] == "thought":
                feed.markdown(f"💭 {e['text']}")
            elif e["type"] == "request":
                req = f" `{e['request']}`" if e.get("request") else ""
                feed.markdown(f"➡️ `{e['method']} {e['path']}`{req} → **{e.get('status') or e.get('error')}** `{e.get('response')}`")
            else:
                feed.error(f"🐞 [{e.get('criterion', '')}] {e['title']}")

        with st.spinner("Exploring..."):
            ss.explore = explore(get_llm(), story, fetch_openapi(base_url), base_url, budget, emit=emit)
    if ss.explore:
        st.subheader(f"Findings ({len(ss.explore['findings'])}) · {ss.explore['requests_used']} requests used")
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
    if not issues:
        st.caption("No agent-found issues yet. Run the full cycle on the buggy build.")
    else:
        df = pd.DataFrame([{"#": i["number"], "State": "🟢 open" if i["state"] == "open" else "✅ closed",
                            "Title": i["title"], "Opened": i.get("opened", ""), "Closed": i.get("closed", ""),
                            "Link": i["url"]} for i in issues])
        st.dataframe(df, hide_index=True, width="stretch",
                     column_config={"Link": st.column_config.LinkColumn(display_text="open")})
