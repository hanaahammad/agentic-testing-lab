"""The console pages: a cartoon welcome, one page per testing activity, and the results pages."""
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from agent import artifacts, pipeline
from agent.config import load_stories
from agent.explorer import explore_and_save
from agent.issues import sync_issues
from agent.target import endpoint_table, fetch_openapi

from . import cartoons
from .common import (get_ctx, get_llm, get_tracker, need, pick_story, saved_badge, save_step_version, show_actions,
                     show_run, show_verdicts, ss)

PAGES = {}   # key -> st.Page, filled by build()


def svg_img(svg: str, max_width: str = "100%", border: bool = False) -> None:
    """Show an SVG drawing as an image (st.html strips inline SVG, an <img> data URI survives)."""
    import base64

    data = base64.b64encode(svg.encode("utf-8")).decode()
    style = f"width:100%;max-width:{max_width};display:block;border-radius:10px" + (
        ";border:2px solid #1f2a37" if border else "")
    st.markdown(f'<img src="data:image/svg+xml;base64,{data}" style="{style}" alt="cartoon">', unsafe_allow_html=True)


def L():
    return ss.lab


# ---------------------------------------------------------------- Welcome
def welcome():
    lab = L()
    st.title("🧪 Agentic Testing Lab")
    st.markdown(f"A QA agent that tests **{lab['T']['name']}** the way a tester would: it reads the user story, "
                "designs the tests, writes and runs the scripts, sorts the failures and files the bugs. "
                "**You stay in charge** of what gets automated and what counts as a bug.")
    svg_img(cartoons.hero(), "1000px")
    st.subheader("How you use it, step by step")
    for row in range(3):
        cols = st.columns(3, gap="medium")
        for col, (n, (title, text, fn, key)) in zip(cols, list(enumerate(cartoons.PANELS))[row * 3: row * 3 + 3]):
            with col.container(border=True):
                svg_img(fn(), border=True)
                st.markdown(f"**{n + 1}. {title}**")
                st.caption(text)
                if key and key in PAGES:
                    st.page_link(PAGES[key], label=f"Open {PAGES[key].title}", icon="👉")
                elif not key:
                    st.caption("👈 In the sidebar: *Settings*")
    st.subheader("Who does what")
    st.dataframe(pd.DataFrame([
        ("Choose the app, the brain and the story", "👩 You", ""),
        ("Read the story, the API and the screens", "", "🤖 Agent"),
        ("Propose test cases for every acceptance criterion", "", "🤖 Agent"),
        ("Approve which cases to automate", "👩 You", ""),
        ("Write, check and run the scripts", "", "🤖 Agent"),
        ("Sort failures; repair its own broken tests", "", "🤖 Agent"),
        ("Confirm bugs found by a local model", "👩 You", ""),
        ("Open / close issues, save every run as a version", "", "🤖 Agent"),
        ("Commit the evidence to git and push", "👩 You", ""),
    ], columns=["Activity", "You", "Agent"]), hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    with c1.container(border=True):
        st.markdown("**In a hurry?** One click runs all the steps with auto-approval.")
        st.page_link(PAGES["cycle"], label="Run the full cycle", icon="⚡")
    with c2.container(border=True):
        st.markdown("**Want to see the evidence?** Every run is kept as a numbered version.")
        st.page_link(PAGES["artifacts"], label="Browse artifacts", icon="📦")


# ---------------------------------------------------------------- Stories
def stories_page():
    lab = L()
    st.title("📖 User stories")
    st.markdown(f"The stories the agent tests for **{lab['T']['name']}**: each one has acceptance criteria (AC) "
                "that become test cases. The last column shows the latest saved result.")
    latest = {}
    for m in artifacts.list_versions(lab["app"]):
        if m["kind"] == "cycle" and m["story"] not in latest:
            latest[m["story"]] = m
    rows = []
    for s in load_stories(lab["app"]):
        m = latest.get(s["id"])
        res = "not tested yet"
        if m and m.get("summary"):
            sm = m["summary"]
            res = f"{m['version']} · {sm['passed']}/{sm['total']} passed" + (f" · 🐞 {len(m['product_bugs'])}" if m.get("product_bugs") else "")
        rows.append({"Story": s["id"], "Title": s["title"], "Criteria": len(re.findall(r"\*\*AC\d+\*\*", s["text"])),
                     "Latest result": res})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    story = pick_story(lab, "Work on story")
    c1, c2 = st.columns(2)
    if c1.button("Start step by step: Design →", type="primary", width="stretch"):
        st.switch_page(PAGES["design"])
    if c2.button("Run the full cycle ⚡", width="stretch"):
        st.switch_page(PAGES["cycle"])


# ---------------------------------------------------------------- 1 Design
def design_page():
    lab = L()
    st.title("1 · Design the tests")
    story = pick_story(lab)
    st.markdown("The agent reads the API description (`/openapi.json`)"
                + (" and **walks through the screens** as a test user, noting every field and button"
                   if lab["T"]["kind"] == "web" else "")
                + ", then turns each acceptance criterion into test cases. **You approve** which ones to automate.")
    if st.button("Discover & design tests", type="primary"):
        with st.spinner("Discovering and designing test cases..."):
            ss.ctx = pipeline.discover(story, lab["base_url"])
            ss.cases = pipeline.design_tests(get_llm(lab), story, ss.ctx)
            ss.code = ss.run = ss.verdicts = ss.actions = ss.saved = None
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
        st.page_link(PAGES["scripts"], label="Next: write the scripts", icon="👉")


# ---------------------------------------------------------------- 2 Scripts
def scripts_page():
    lab = L()
    st.title("2 · Write the scripts")
    story = pick_story(lab)
    need(ss.approved, "Design and approve test cases first.", PAGES["design"], "1 · Design")
    st.markdown("The agent writes one pytest test per approved case"
                + (" (Playwright for the screens, HTTP for the API)" if lab["T"]["kind"] == "web" else "")
                + ". Before anything runs it **checks its own script**: syntax, one test per case, no invented "
                  "fixtures, no hard-coded balances. A rejected script goes back to the model with the error.")
    if st.button("Write pytest script from approved cases", type="primary"):
        log = st.status("Writing the script...", expanded=True)
        with log:
            ss.code = pipeline.generate_script(get_llm(lab), story, ss.approved, get_ctx(lab, story), log=st.write)
            pipeline.save_script(story, ss.code)
        log.update(label="Script ready", state="complete", expanded=False)
        ss.run = ss.verdicts = ss.actions = ss.saved = None
    if ss.code:
        problems = pipeline.check_script(ss.code, ss.approved, get_ctx(lab, story))
        if problems:
            st.warning("Checks still failing: " + "; ".join(problems))
        else:
            st.success("All script checks pass.")
        unseen = pipeline.unknown_test_ids(ss.code, get_ctx(lab, story))
        if unseen:
            st.caption("ℹ️ Screen ids not seen while crawling: " + ", ".join(f"`{i}`" for i in unseen)
                       + ". Fine if they only appear after an action (an error or success message); if one is "
                         "wrong, the test times out and triage sends it back for repair.")
        st.caption(f"Saved to `{pipeline.script_path(story).relative_to(pipeline.ROOT)}`. You can edit it here.")
        new = st.text_area("Generated test script", ss.code, height=460)
        if new != ss.code and st.button("Save my edits"):
            ss.code = new
            pipeline.save_script(story, new)
            st.success("Saved.")
        st.page_link(PAGES["run"], label="Next: run the tests", icon="👉")


# ---------------------------------------------------------------- 3 Run
def run_page():
    lab = L()
    st.title("3 · Run the tests")
    story = pick_story(lab)
    need(ss.code, "Write the script first.", PAGES["scripts"], "2 · Scripts")
    if st.button(f"Run tests against {lab['T']['name']} ({lab['build']} build)", type="primary"):
        with st.spinner("Running pytest" + (" with Playwright..." if lab["T"]["kind"] == "web" else "...")):
            ss.run = pipeline.run_tests(pipeline.script_path(story), lab["base_url"], lab["app"])
            ss.verdicts = ss.actions = ss.saved = None
    if ss.run:
        show_run(ss.run)
        c1, c2 = st.columns(2)
        with c1:
            st.page_link(PAGES["triage"], label="Next: triage the failures", icon="👉")
        if c2.button("📦 Save this run as a version"):
            save_step_version(lab, story, "run")
        saved_badge(ss.saved)


# ---------------------------------------------------------------- 4 Triage & issues
def triage_page():
    lab = L()
    st.title("4 · Triage & issues")
    story = pick_story(lab)
    need(ss.run, "Run the tests first.", PAGES["run"], "3 · Run")
    st.markdown("For each failure the agent decides: **product bug** (the app breaks the story), "
                "**test bug** (its own script is wrong, so it repairs it), or **environment** (the app or browser "
                "was not reachable).")
    show_run(ss.run)
    if st.button("Triage failures", type="primary"):
        with st.spinner("Triaging..."):
            ss.verdicts = pipeline.triage(get_llm(lab), story, ss.approved or ss.cases or [], ss.code, ss.run,
                                          get_ctx(lab, story))
    if ss.verdicts is not None:
        show_verdicts(ss.verdicts)
        c1, c2 = st.columns(2)
        if any(v["verdict"] == "test_bug" for v in ss.verdicts) and \
                c1.button("🔧 Let the agent repair its script and re-run"):
            with st.spinner("Repairing and re-running..."):
                llm = get_llm(lab)
                ss.code = pipeline.repair_script(llm, story, ss.code, ss.verdicts, ss.run, get_ctx(lab, story),
                                                 ss.approved or ss.cases or [])
                pipeline.save_script(story, ss.code)
                ss.run = pipeline.run_tests(pipeline.script_path(story), lab["base_url"], lab["app"])
                ss.verdicts = pipeline.triage(llm, story, ss.approved or ss.cases or [], ss.code, ss.run,
                                              get_ctx(lab, story))
                ss.repairs_done = ss.get("repairs_done", 0) + 1
            st.rerun()
        if c2.button("Sync bug tracker and save this run"):
            ss.actions = sync_issues(get_tracker(lab), story, ss.run, ss.verdicts)
            save_step_version(lab, story, "complete")
        if ss.actions is not None:
            show_actions(ss.actions) if ss.actions else st.caption("Nothing to change in the tracker.")
        saved_badge(ss.saved)


# ---------------------------------------------------------------- Full cycle
def cycle_page():
    lab = L()
    st.title("⚡ Full cycle")
    story = pick_story(lab)
    st.markdown("One click runs every step with **auto-approval** and saves the run as a new version. Run it on the "
                "buggy build, then switch on **Developer fix deployed** in the sidebar and run it again: the agent "
                "closes the issues it opened.")
    if lab["T"]["kind"] == "web":
        st.caption("UI tests run in a real headless browser (Playwright), so a NileBank cycle takes a little longer.")
    if st.button("Run full cycle", type="primary"):
        llm, tracker = get_llm(lab), get_tracker(lab)
        with st.status("Agent at work...", expanded=True) as status:
            try:
                ss.cycle = pipeline.full_cycle(llm, story, lab["base_url"], tracker=tracker, log=st.write)
                status.update(label="Cycle complete", state="complete")
            except Exception as e:
                status.update(label="Cycle failed", state="error")
                st.exception(e)
    if ss.cycle:
        saved_badge(ss.cycle.get("artifact"))
        st.subheader("Results")
        show_run(ss.cycle["run"])
        if ss.cycle["repairs"]:
            st.info(f"The agent repaired its own test script {ss.cycle['repairs']} time(s) before filing bugs.")
        st.subheader("Triage")
        show_verdicts(ss.cycle["verdicts"])
        st.subheader("Bug tracker actions")
        show_actions(ss.cycle["actions"]) if ss.cycle["actions"] else st.caption("No changes to the tracker.")


# ---------------------------------------------------------------- Explore
def explore_page():
    lab = L()
    st.title("🤖 Explore live")
    story = pick_story(lab)
    if lab["T"]["kind"] == "web":
        st.markdown("The agent **tests the app itself**, with no script. It drives a **real browser** (opens pages, "
                    "types, clicks, reads the screen) and calls the API, decides what to try next from what it sees, "
                    "and records findings. Every browser step is captured as a screenshot and kept in the artifacts.")
    else:
        st.markdown("The agent **tests the app itself**: no script, it sends HTTP requests one at a time, reads each "
                    "response, decides what to try next, and records findings.")
    st.caption("With Claude or Ollama this is a real tool-use loop; the demo brain replays a scripted session.")
    budget = st.slider("Action budget", 5, 40, 15)
    show_shots = lab["T"]["kind"] == "web" and st.toggle("Show screenshots", value=True)
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
                ss.explore = explore_and_save(get_llm(lab), story, fetch_openapi(lab["base_url"], lab["app"]),
                                              lab["base_url"], budget, emit=emit)
            except Exception as e:
                st.exception(e)
    if ss.explore:
        saved_badge(ss.explore.get("artifact"))
        st.subheader(f"Findings ({len(ss.explore['findings'])}) · {ss.explore['requests_used']} actions used")
        if ss.explore["findings"]:
            st.dataframe(pd.DataFrame(ss.explore["findings"]), hide_index=True, width="stretch")
        st.caption("Exploration finds bugs; scripted tests keep them found. Turn a finding into a permanent test "
                   "by adding it as an acceptance criterion and running the cycle.")


# ---------------------------------------------------------------- Issues
def issues_page():
    lab = L()
    st.title("📋 Issues")
    st.caption("Bugs the agent filed. It closes an issue by itself when the test that found it passes again.")
    try:
        issues = get_tracker(lab).list()
    except Exception as e:
        st.error(f"Could not read the tracker: {e}")
        issues = []
    nums = {s["id"].split("-")[1] for s in load_stories(lab["app"])}
    mine = [i for i in issues if (m := re.match(r"\[TC-(\d+)-", i["title"])) and m.group(1) in nums]
    if not mine:
        st.caption(f"No agent-found {lab['T']['name']} issues yet. Run the full cycle on the buggy build.")
        return
    c1, c2 = st.columns(2)
    c1.metric("Open", sum(1 for i in mine if i["state"] == "open"))
    c2.metric("Closed", sum(1 for i in mine if i["state"] != "open"))
    df = pd.DataFrame([{"#": i["number"], "State": "🟢 open" if i["state"] == "open" else "✅ closed",
                        "Title": i["title"], "Opened": i.get("opened", ""), "Closed": i.get("closed", ""),
                        "Link": i["url"]} for i in mine])
    st.dataframe(df, hide_index=True, width="stretch",
                 column_config={"Link": st.column_config.LinkColumn(display_text="open")})


# ---------------------------------------------------------------- Artifacts
FILE_LABELS = {"test_cases.json": "Test cases", "test_script.py": "Script", "results.json": "Results",
               "triage.json": "Triage", "issues.json": "Issues", "report.md": "Report", "story.md": "Story",
               "findings.json": "Findings", "transcript.json": "Transcript", "junit.xml": "JUnit XML"}


def _summary(m):
    if m["kind"] == "exploration":
        return f"{m.get('findings', 0)} finding(s) · {m.get('actions_used', 0)} actions"
    s = m.get("summary") or {}
    return f"{s.get('passed', 0)}/{s.get('total', 0)} passed" if s else m.get("stage", "")


def artifacts_page():
    lab = L()
    st.title("📦 Artifacts")
    st.markdown("Every run is saved as a **new numbered version**, never overwritten: the story as tested, the "
                "approved cases, the script, raw and parsed results, the triage, the issues and, for explorations, "
                "every screenshot. Each file's fingerprint (sha256) is recorded so you can prove nothing changed, "
                "and the whole `artifacts/` folder can be **committed to git** for full history on GitHub.")
    versions = artifacts.list_versions(lab["app"])
    g = artifacts.git_status()
    pending = set(g.get("pending", []))
    with st.container(border=True):
        c1, c2 = st.columns([3, 1.3])
        if not g["repo"]:
            c1.markdown("**Git:** this folder is not a git repository, so versions are kept as folders only.")
        elif pending:
            c1.markdown(f"**Git:** {len(pending)} version(s) not committed yet on branch `{g.get('branch')}`.")
            if c2.button("Commit artifacts to git", type="primary", width="stretch"):
                ok, msg = artifacts.commit_to_git()
                (st.success if ok else st.error)(msg)
                st.rerun() if ok else None
        else:
            c1.markdown(f"**Git:** every version is committed on branch `{g.get('branch')}`. "
                        "`git push` sends them to GitHub.")
    if not versions:
        st.info("No artifacts yet. Run a full cycle or an exploration and it will appear here.")
        st.page_link(PAGES["cycle"], label="Run the full cycle", icon="⚡")
        return
    stories = sorted({m["story"] for m in versions})
    f1, f2 = st.columns(2)
    pick = f1.selectbox("Story", ["All stories"] + stories)
    kind = f2.selectbox("Kind", ["All", "Test cycles", "Explorations"])
    shown = [m for m in versions if (pick == "All stories" or m["story"] == pick)
             and (kind == "All" or (m["kind"] == "cycle") == (kind == "Test cycles"))]

    def git_of(m):
        rel = f"{m['app']}/{m['story']}/{m['version']}"
        return "—" if not g["repo"] else ("⏳ not committed" if rel in pending else "✅ committed")

    df = pd.DataFrame([{"Story": m["story"], "Version": m["version"], "Kind": m["kind"], "Saved": m["created"].replace("T", " "),
                        "Build": m.get("build_tested"), "Brain": m.get("brain"), "Result": _summary(m),
                        "Bugs": ", ".join(m.get("product_bugs", [])), "Review": "⚠️" if m.get("needs_review") else "",
                        "Git": git_of(m)} for m in shown])
    st.dataframe(df, hide_index=True, width="stretch")

    st.subheader("Open a version")
    labels = {f"{m['story']} · {m['version']} · {m['created'].replace('T', ' ')} · {_summary(m)}": m for m in shown}
    if not labels:
        return
    m = labels[st.selectbox("Version", list(labels))]
    bad = artifacts.verify(m)
    a, b, c = st.columns(3)
    a.metric("Build tested", m.get("build_tested"))
    b.metric("Brain", (m.get("brain") or "").split("·")[-1].strip())
    c.metric("Lab code", m.get("lab_code"))
    rel = Path(m["path"]).relative_to(pipeline.ROOT).as_posix() if Path(m["path"]).is_relative_to(pipeline.ROOT) else m["path"]
    st.caption(f"Parent version: {m.get('parent') or 'none (first)'} · folder `{rel}/`")
    if bad:
        st.error("Integrity check failed: " + ", ".join(bad))
    else:
        st.caption(f"🔒 Integrity check passed for {len(m.get('files', {}))} files.")
    names = [n for n in FILE_LABELS if n in m.get("files", {})]
    tabs = st.tabs([FILE_LABELS[n] for n in names] + (["Screenshots"] if m.get("screenshots") else []) + ["Manifest"])
    for tab, name in zip(tabs, names):
        with tab:
            v = artifacts.read(m, name)
            if name == "report.md" or name == "story.md":
                st.markdown(v)
            elif name == "test_script.py":
                st.code(v, language="python")
            elif name == "junit.xml":
                st.code(v[:20000], language="xml")
            elif name in ("test_cases.json", "findings.json") and isinstance(v, list) and v:
                st.dataframe(pd.DataFrame(v), hide_index=True, width="stretch")
            elif name == "results.json":
                show_run({**v, "output": ""})
            elif name == "triage.json":
                show_verdicts(v)
            else:
                st.json(v, expanded=False)
    if m.get("screenshots"):
        with tabs[len(names)]:
            transcript = artifacts.read(m, "transcript.json") or []
            for e in transcript:
                if e.get("screenshot"):
                    st.caption(f"{e.get('action', '')} → {e.get('result', '')}")
                    st.image(artifacts.read(m, e["screenshot"]), width=560)
    with tabs[-1]:
        st.json({k: v for k, v in m.items() if k != "path"}, expanded=True)
    st.download_button(f"Download {m['version']} (zip)", artifacts.zip_bytes(m),
                       file_name=f"{m['app']}-{m['story']}-{m['version']}.zip", mime="application/zip")

    same = [x for x in versions if x["story"] == m["story"] and x["kind"] == m["kind"] and x["version"] != m["version"]]
    if same:
        st.subheader("Compare with another version")
        other = {f"{x['version']} · {x['created'].replace('T', ' ')} · {_summary(x)}": x for x in same}
        o = other[st.selectbox("Compare with", list(other))]
        old, new = sorted([o, m], key=lambda x: x["version"])
        common_files = [n for n in FILE_LABELS if n in old.get("files", {}) and n in new.get("files", {})]
        if common_files:
            fname = st.selectbox("File", common_files, format_func=lambda n: FILE_LABELS[n])
            d = artifacts.diff(old, new, fname)
            if d:
                st.code(d, language="diff")
            else:
                st.success(f"{FILE_LABELS[fname]} is identical in {old['version']} and {new['version']}.")


# ---------------------------------------------------------------- Dashboard
def dashboard_page():
    lab = L()
    from agent import dashboard as dash

    st.title("📊 Dashboard")
    app = lab["app"]
    history = dash.load_history(app)
    c1, c2, c3 = st.columns([1.2, 1.6, 3])
    build_clicked = c1.button("Build / refresh", type="primary", width="stretch")
    seed_clicked = c2.button("Seed demo history", width="stretch",
                             help="Runs the demo cycle three times (buggy → fix → regression) so the charts have a trend.")
    c3.caption(f"{len(history)} {lab['T']['name']} runs recorded · charts by D3Blocks · also saved as "
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
                    dash.build_index(history, paths)
                    ss.dash_page = dash.build_index(history, paths, links=False)
                    ss.dash_height = dash.page_height(paths)
    except ImportError:
        st.error("D3Blocks is not installed. Run `pip install d3blocks` in your venv, then restart Streamlit.")
    if ss.get("dash_page"):
        page_html = ss.dash_page.read_text(encoding="utf-8")
        st.iframe(page_html, height=ss.dash_height)
        st.download_button("Download dashboard (single HTML file)", ss.dash_page.read_bytes(),
                           file_name=f"qa-dashboard-{app}.html", mime="text/html")
    elif history:
        st.info("Click **Build / refresh** to draw the dashboard.")


# ---------------------------------------------------------------- registry
def build():
    spec = [
        ("Start", [("welcome", welcome, "Welcome", "🏠", True)]),
        ("Test activities", [
            ("stories", stories_page, "Stories", "📖", False),
            ("design", design_page, "1 · Design", "🧩", False),
            ("scripts", scripts_page, "2 · Scripts", "📝", False),
            ("run", run_page, "3 · Run", "▶️", False),
            ("triage", triage_page, "4 · Triage & issues", "🩺", False),
            ("cycle", cycle_page, "Full cycle", "⚡", False),
            ("explore", explore_page, "Explore live", "🤖", False),
        ]),
        ("Results", [
            ("issues", issues_page, "Issues", "📋", False),
            ("artifacts", artifacts_page, "Artifacts", "📦", False),
            ("dashboard", dashboard_page, "Dashboard", "📊", False),
        ]),
    ]
    nav = {}
    for section, items in spec:
        nav[section] = []
        for key, fn, title, icon, default in items:
            PAGES[key] = st.Page(fn, title=title, icon=icon, url_path=key, default=default)
            nav[section].append(PAGES[key])
    return nav
