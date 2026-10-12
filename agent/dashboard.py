"""QA dashboard built with D3Blocks: interactive D3 charts from the agent's own results.

Reads reports/history.jsonl (one line per agent run) and builds:
  1. Sankey     story -> acceptance criterion -> outcome     (where do tests end up?)
  2. Tree       story -> criterion -> test case -> status     (traceability)
  3. Treemap    test portfolio sized by number of tests        (where is the risk?)
  4. Timeseries passed / failed / product bugs over runs       (is quality improving?)

Each chart is a standalone HTML file; dashboard/index.html puts them on one page.
  python -m agent.dashboard            # build from history
  python -m agent.dashboard --seed     # no history yet? run buggy + fixed demo cycles first
"""
import argparse
import datetime as dt
import html
import json
from pathlib import Path

import pandas as pd

from .config import DEFAULT_TARGET, REPORTS_DIR, ROOT, TARGETS

HISTORY = REPORTS_DIR / "history.jsonl"
OUT_DIR = ROOT / "dashboard"

OUTCOME_COLORS = {"Passed": "#2f8f68", "Product bug": "#c9433a", "Test bug": "#c98a1e",
                  "Environment issue": "#6b7280", "Failed (untriaged)": "#8b5cf6"}
OUTCOME = {"passed": "Passed", "product_bug": "Product bug", "test_bug": "Test bug",
           "environment": "Environment issue"}


# ---------------- data ----------------
def load_history(app: str = DEFAULT_TARGET) -> list[dict]:
    """Runs recorded for one application (older entries without an app are MiniBank runs)."""
    if not HISTORY.exists():
        return []
    rows = [json.loads(line) for line in HISTORY.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [r for r in rows if r.get("app", "minibank") == app]


def app_of(history: list[dict]) -> str:
    return history[0].get("app", "minibank") if history else DEFAULT_TARGET


def latest_per_story(history: list[dict]) -> list[dict]:
    last = {}
    for h in history:
        last[h["story"]] = h
    return [last[k] for k in sorted(last)]


def outcome(case: dict) -> str:
    if case["status"] == "passed":
        return "Passed"
    return OUTCOME.get(case.get("verdict"), "Failed (untriaged)")


def case_rows(runs: list[dict]) -> pd.DataFrame:
    rows = []
    for r in runs:
        for c in r["cases"]:
            rows.append({"app": TARGETS[r.get("app", "minibank")]["name"],
                         "story": r["story"], "title": r["title"], "build": r["build"],
                         "criterion": c.get("criterion") or "?", "tc_id": c["tc_id"] or "?",
                         "case_title": c.get("title", ""), "outcome": outcome(c)})
    return pd.DataFrame(rows)


def kpis(history: list[dict]) -> dict:
    latest = latest_per_story(history)
    df = case_rows(latest)
    if df.empty:
        return {"runs": 0, "tests": 0, "passed": 0, "bugs": 0, "pass_rate": 0, "repairs": 0, "build": "-"}
    return {
        "runs": len(history),
        "tests": len(df),
        "passed": int((df["outcome"] == "Passed").sum()),
        "bugs": int((df["outcome"] == "Product bug").sum()),
        "pass_rate": round(100 * (df["outcome"] == "Passed").mean()),
        "repairs": sum(h["repairs"] for h in history),
        "build": latest[-1]["build"],
    }


# ---------------- charts ----------------
def sankey_df(df: pd.DataFrame) -> pd.DataFrame:
    """story -> 'AC2 · STORY-003' -> outcome, weighted by number of tests."""
    df = df.assign(crit=df["story"] + "-" + df["criterion"])
    a = df.groupby(["story", "crit"]).size().reset_index(name="weight").rename(columns={"story": "source", "crit": "target"})
    b = df.groupby(["crit", "outcome"]).size().reset_index(name="weight").rename(columns={"crit": "source", "outcome": "target"})
    return pd.concat([a, b], ignore_index=True)


def tree_df(df: pd.DataFrame) -> pd.DataFrame:
    """Edge list: app -> story -> criterion -> test case -> status (node names kept unique)."""
    crit = df["story"] + "-" + df["criterion"]
    test = df["tc_id"]
    status = df["outcome"] + ": " + df["case_title"].str.slice(0, 30)
    edges = pd.concat([
        pd.DataFrame({"source": df["app"], "target": df["story"]}),
        pd.DataFrame({"source": df["story"], "target": crit}),
        pd.DataFrame({"source": crit, "target": test}),
        pd.DataFrame({"source": test, "target": status}),
    ]).drop_duplicates()
    return edges.assign(weight=1).reset_index(drop=True)


def treemap_df(df: pd.DataFrame) -> pd.DataFrame:
    """D3Blocks colours a treemap by its second level, so that level is the outcome."""
    return pd.DataFrame({
        "group1": df["app"] + " tests",
        "group2": df["outcome"],
        "group3": df["tc_id"] + ": " + df["case_title"].str.slice(0, 30),
        "weight": 1,
    })


def batches(history: list[dict], gap_s: int = 120) -> list[list[dict]]:
    """Group runs into cycles: a new batch starts when the build changes or after a quiet gap."""
    out = []
    for h in history:
        t = dt.datetime.fromisoformat(h["timestamp"])
        if out:
            prev = out[-1][-1]
            same_build = prev["build"] == h["build"]
            close = (t - dt.datetime.fromisoformat(prev["timestamp"])).total_seconds() <= gap_s
            if same_build and close:
                out[-1].append(h)
                continue
        out.append([h])
    return out


def timeseries_df(history: list[dict]) -> pd.DataFrame:
    """One point per cycle (batch of story runs): passed, failed and product bugs."""
    rows = []
    for b in batches(history):
        rows.append({
            "datetime": dt.datetime.fromisoformat(b[-1]["timestamp"]).strftime("%d-%m-%Y %H:%M:%S"),
            "passed": sum(h["summary"]["passed"] for h in b),
            "failed": sum(h["summary"]["failed"] + h["summary"]["error"] for h in b),
        })
    df = pd.DataFrame(rows)
    # Batches in the same second would collide on the time axis: nudge them apart.
    seen = {}
    for i, v in enumerate(df["datetime"]):
        n = seen.get(v, 0)
        seen[v] = n + 1
        if n:
            t = dt.datetime.strptime(v, "%d-%m-%Y %H:%M:%S") + dt.timedelta(seconds=n)
            df.loc[i, "datetime"] = t.strftime("%d-%m-%Y %H:%M:%S")
    return df


# Embedded charts: no D3Blocks menus, light theme, fixed size scaled down to fit their card.
EMBED = {  # key: (width, height)  -- frame height in the page = height + a small margin
    "sankey": (1100, 520),
    "timeseries": (640, 300),
    "treemap": (1100, 360),
    "tree": (1100, 720),
}

FIT_SHIM = """<style>html,body{{margin:0!important;padding:0!important;background:transparent!important;overflow:hidden}}</style>
<script>(function(){{var W={w};function fit(){{var z=Math.min(1,(window.innerWidth-4)/W);
document.body.style.zoom=z;}}window.addEventListener('resize',fit);document.addEventListener('DOMContentLoaded',fit);fit();}})();</script>"""


def _patch(path: Path, *pairs, head_extra: str = ""):
    text = path.read_text(encoding="utf-8")
    for old, new in pairs:
        text = text.replace(old, new)
    if head_extra:
        text = text.replace("</head>", head_extra + "</head>", 1)
    path.write_text(text, encoding="utf-8")


TREEMAP_COLORS = ("const color = d3.scaleOrdinal().range(d3.schemeCategory20c);",
                  "const OUTCOME_COLORS = " + json.dumps(OUTCOME_COLORS) + ";"
                  " const _fallback = d3.scaleOrdinal().range(d3.schemeCategory20c);"
                  " const color = (n) => OUTCOME_COLORS[n] || _fallback(n);")
# D3Blocks smooths timeseries lines ("basis"), inventing values between runs; test counts are discrete.
STRAIGHT_LINES = ('var currentInterp = "basis";', 'var currentInterp = "linear";')


def _render(key, history, df, path, embed: bool, dark: bool):
    from d3blocks import D3Blocks

    w, h = EMBED[key] if embed else {"sankey": (1100, 620), "timeseries": (780, 400),
                                     "treemap": (1100, 560), "tree": (1060, 800)}[key]
    kw = dict(showfig=False, overwrite=True, dark_mode=dark, filepath=str(path), figsize=[w, h])
    if embed:
        kw.update(show_side_panel=False, show_top_panel=False, save_button=False)
    d3 = D3Blocks(verbose="error", support=False)  # support=False: no ad script in the output
    if key == "sankey":
        d3.sankey(sankey_df(df), title="Story → criterion → outcome", fontsize=11, **kw)
    elif key == "tree":
        d3.tree(tree_df(df), title="Traceability", link_length=185, **kw)
    elif key == "treemap":
        d3.treemap(treemap_df(df), value="weight", title="Test portfolio", **kw)
    elif key == "timeseries":
        ts = timeseries_df(history)
        d3 = D3Blocks(chart="Timeseries", frame=False, verbose="error", support=False)
        d3.set_node_properties(ts.columns.values)
        d3.node_properties.get("passed")["color"] = "#2f8f68"
        d3.node_properties.get("failed")["color"] = "#c9433a"
        d3.set_edge_properties(ts, datetime="datetime", dt_format="%d-%m-%Y %H:%M:%S")
        d3.show(title="Passed and failed per cycle", **kw)
    pairs = [TREEMAP_COLORS] if key == "treemap" else [STRAIGHT_LINES] if key == "timeseries" else []
    _patch(path, *pairs, head_extra=FIT_SHIM.format(w=w) if embed else "")


def out_dir_for(app: str) -> Path:
    return OUT_DIR / app


def build_charts(history: list[dict], out_dir: Path | None = None, dark: bool = False) -> dict[str, Path]:
    """Builds clean embedded charts in dashboard/<app>/ and full-featured ones (filters, export) in .../full/."""
    out_dir = out_dir or out_dir_for(app_of(history))
    (out_dir / "full").mkdir(parents=True, exist_ok=True)
    df = case_rows(latest_per_story(history))
    keys = ["sankey", "treemap", "tree"] + (["timeseries"] if len(batches(history)) >= 2 else [])
    paths = {}
    for key in keys:
        paths[key] = out_dir / f"{key}.html"
        _render(key, history, df, paths[key], embed=True, dark=dark)
        _render(key, history, df, out_dir / "full" / f"{key}.html", embed=False, dark=True)
    return paths


def open_bugs(history: list[dict]) -> list[dict]:
    rows = []
    for r in latest_per_story(history):
        for c in r["cases"]:
            if c["status"] != "passed" and c.get("verdict") == "product_bug":
                rows.append({"story": r["story"], "tc_id": c["tc_id"], "criterion": c.get("criterion", ""),
                             "title": c.get("title", ""), "since": r["timestamp"][:16].replace("T", " ")})
    return rows


# ---------------- one-page dashboard ----------------
CHART_INFO = {
    "sankey": ("Where do the tests end up?",
               "Each band is a group of tests flowing from a story, through the acceptance criterion it checks, "
               "to its outcome. Bands into Product bug show where the app breaks its own rules."),
    "timeseries": ("Is quality improving?",
                   "Passed (green) and failed (red) tests per agent cycle."),
    "tree": ("Traceability", "Story → acceptance criterion → test case → status. Click a node to fold or unfold it."),
    "treemap": ("Test portfolio", "One rectangle per test, grouped by outcome: green passed, red product bug."),
}


def frame_height(key: str) -> int:
    return EMBED[key][1] + 16


def build_index(history: list[dict], paths: dict[str, Path], out_dir: Path | None = None,
                links: bool = True) -> Path:
    """One self-contained HTML file: charts are embedded with srcdoc, so it can be emailed on its own.
    links=False drops the 'Explore full screen' links (used inside Streamlit, where they cannot open)."""
    out_dir = out_dir or out_dir_for(app_of(history))
    k = kpis(history)

    def explore(key):
        return f'<a href="full/{key}.html" target="_blank">Explore full screen ↗</a>' if links else ""

    bugs = open_bugs(history)
    stamp = dt.datetime.now().strftime("%d %b %Y, %H:%M")
    seeded = " · includes seeded demo cycles" if any(h.get("seeded") for h in history) else ""

    def card(key, extra=""):
        if key not in paths:
            return ""
        title, desc = CHART_INFO[key]
        return (f'<section class="card {extra}"><div class="head"><div><h2>{title}</h2><p>{desc}</p></div>'
                f'{explore(key)}</div>'
                f'<iframe srcdoc="{html.escape(paths[key].read_text(encoding="utf-8"), quote=True)}" '
                f'style="height:{frame_height(key)}px" title="{title}"></iframe></section>')

    bug_rows = "".join(
        f'<li><span class="tag">{html.escape(b["tc_id"])}</span><div><b>{html.escape(b["title"])}</b>'
        f'<small>{html.escape(b["story"])} · {html.escape(b["criterion"])} · since {b["since"]}</small></div></li>'
        for b in bugs) or '<li class="none">No open product bugs 🎉</li>'
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>QA Agent Dashboard</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--line:#e4e7ec;--text:#1d2433;--muted:#667085;--ok:#2f8f68;--bad:#c9433a;--acc:#4f46e5}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 "Segoe UI",system-ui,sans-serif}}
main{{max-width:1240px;margin:0 auto;padding:32px 20px 60px}}
header{{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;margin-bottom:22px}}
h1{{font-size:26px;margin:0;font-weight:650;letter-spacing:-.01em}} .sub{{color:var(--muted);margin:4px 0 0;font-size:14px}}
.build{{font-size:13px;padding:5px 12px;border-radius:999px;background:#fdecea;color:var(--bad);font-weight:600}}
.build.fixed{{background:#e7f5ef;color:var(--ok)}}
.kpis{{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin-bottom:18px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px 18px}}
.kpi b{{display:block;font-size:30px;font-weight:650;line-height:1.1}} .kpi span{{color:var(--muted);font-size:13px}}
.kpi.ok b{{color:var(--ok)}} .kpi.bad b{{color:var(--bad)}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 18px 10px;margin-bottom:18px}}
.head{{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:8px}}
h2{{font-size:17px;margin:0;font-weight:650}} .head p{{color:var(--muted);margin:2px 0 0;font-size:13.5px}}
.head a{{color:var(--acc);font-size:13px;text-decoration:none;white-space:nowrap}}
iframe{{width:100%;border:0;display:block}}
.row{{display:grid;grid-template-columns:3fr 2fr;gap:18px}} .row .card{{margin-bottom:18px}}
ul.bugs{{list-style:none;margin:6px 0 8px;padding:0}} ul.bugs li{{display:flex;gap:12px;padding:10px 0;border-top:1px solid var(--line)}}
ul.bugs li:first-child{{border-top:0}} .tag{{background:#fdecea;color:var(--bad);font-size:12px;font-weight:600;padding:3px 8px;border-radius:6px;height:fit-content;white-space:nowrap}}
ul.bugs b{{display:block;font-weight:600;font-size:14px}} ul.bugs small{{color:var(--muted);font-size:12.5px}} .none{{color:var(--ok)}}
@media (max-width:900px){{.kpis{{grid-template-columns:repeat(2,1fr)}} .row{{grid-template-columns:1fr}}}}
</style></head><body><main>
<header><div><h1>QA Agent Dashboard · {TARGETS[app_of(history)]['name']}</h1>
<p class="sub">{k['runs']} agent runs · generated {stamp}{seeded}</p></div>
<span class="build {'fixed' if k['build'] == 'fixed' else ''}">Latest build: {k['build']}</span></header>
<div class="kpis">
<div class="kpi"><b>{k['tests']}</b><span>tests in latest runs</span></div>
<div class="kpi ok"><b>{k['pass_rate']}%</b><span>pass rate</span></div>
<div class="kpi bad"><b>{k['bugs']}</b><span>open product bugs</span></div>
<div class="kpi"><b>{k['repairs']}</b><span>self-repaired test scripts</span></div>
<div class="kpi"><b>{k['runs']}</b><span>agent runs recorded</span></div>
</div>
{card("sankey")}
<div class="row">{card("timeseries")}<section class="card"><div class="head"><div><h2>Open product bugs</h2>
<p>Failing tests the agent triaged as real defects.</p></div></div><ul class="bugs">{bug_rows}</ul></section></div>
{card("treemap")}
{card("tree")}
</main></body></html>"""
    path = out_dir / ("index.html" if links else "index_embedded.html")
    path.write_text(page, encoding="utf-8")
    return path


def page_height(paths: dict[str, Path]) -> int:
    """Approximate height of index.html, so Streamlit can show it without an inner scrollbar."""
    h = 120 + 130  # header + KPI cards
    h += frame_height("sankey") + 110
    h += max(frame_height("timeseries") if "timeseries" in paths else 0, 330) + 110
    h += frame_height("treemap") + 110 + frame_height("tree") + 110
    return h + 60


def build(seed: bool = False, app: str = DEFAULT_TARGET) -> Path:
    history = load_history(app)
    if seed and len(history) < 2:
        seed_history(app)
        history = load_history(app)
    if not history:
        raise SystemExit(f"No agent runs recorded for {app} yet. Run a cycle first, or use --seed.")
    paths = build_charts(history)
    return build_index(history, paths)


def seed_history(app: str = DEFAULT_TARGET):
    """Demo story: buggy build -> developer fix -> a later release reintroduces the bugs (a regression)."""
    from .config import load_stories
    from .issues import LocalTracker
    from .llm import DemoLLM
    from .pipeline import full_cycle
    from .target import ensure_local_app

    lines_before = HISTORY.read_text(encoding="utf-8").splitlines() if HISTORY.exists() else []
    stories = load_stories(app)
    for fixed in (False, True, False):
        url = ensure_local_app(app, fixed)
        for s in stories:
            full_cycle(DemoLLM(), s, url, tracker=LocalTracker(), log=lambda *_: None)
    # Date the three demo cycles as three daily releases (marked "seeded") so the trend is readable.
    lines = HISTORY.read_text(encoding="utf-8").splitlines()
    today = dt.datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)
    start = len(lines_before)
    for i in range(start, len(lines)):
        e = json.loads(lines[i])
        cycle = (i - start) // len(stories)
        e["timestamp"] = (today - dt.timedelta(days=2 - cycle) + dt.timedelta(minutes=(i - start) % len(stories))
                          ).isoformat(timespec="seconds")
        e["seeded"] = True
        lines[i] = json.dumps(e)
    HISTORY.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--app", choices=list(TARGETS), default=DEFAULT_TARGET)
    ap.add_argument("--seed", action="store_true", help="Run demo cycles first if there is no history")
    a = ap.parse_args()
    print(f"Dashboard written to {build(seed=a.seed, app=a.app)}")
