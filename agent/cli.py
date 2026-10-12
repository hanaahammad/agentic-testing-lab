"""Command line entry point, used locally and by GitHub Actions.

  python -m agent.cli cycle --story ALL --demo --start-app
  python -m agent.cli cycle --story STORY-003 --tracker github        (needs ANTHROPIC_API_KEY, GITHUB_TOKEN)
  python -m agent.cli explore --story STORY-002 --demo --start-app
"""
import argparse
import json
import os
import sys

from .config import DEFAULT_BASE_URL, DEFAULT_PORT, get_story, load_stories
from .issues import make_tracker
from .llm import make_llm
from .pipeline import full_cycle
from .target import ensure_local_app, fetch_openapi, health


def main(argv=None):
    p = argparse.ArgumentParser(prog="agent")
    p.add_argument("command", choices=["cycle", "explore", "stories"])
    p.add_argument("--story", default="ALL", help="STORY-xxx or ALL")
    p.add_argument("--demo", action="store_true", help="Use the scripted brain (no API key needed)")
    p.add_argument("--model", default="")
    p.add_argument("--base-url", default=DEFAULT_BASE_URL)
    p.add_argument("--start-app", action="store_true", help="Start MiniBank locally first")
    p.add_argument("--fixed", action="store_true", help="With --start-app: run the fixed build")
    p.add_argument("--tracker", choices=["local", "github", "none"], default="local")
    p.add_argument("--budget", type=int, default=15, help="explore: max HTTP requests")
    a = p.parse_args(argv)

    if a.command == "stories":
        for s in load_stories():
            print(f"{s['id']}: {s['title']}")
        return 0

    base_url = ensure_local_app(DEFAULT_PORT, a.fixed) if a.start_app else a.base_url
    h = health(base_url)
    if not h:
        print(f"App not reachable at {base_url}", file=sys.stderr)
        return 2
    print(f"Testing MiniBank at {base_url} (build: {h.get('build')})")

    llm = make_llm(a.demo, os.getenv("ANTHROPIC_API_KEY", ""), a.model)
    stories = load_stories() if a.story.upper() == "ALL" else [get_story(a.story)]

    if a.command == "explore":
        from .explorer import explore

        spec = fetch_openapi(base_url)
        for s in stories:
            res = explore(llm, s, spec, base_url, a.budget, emit=lambda e: print(_fmt(e)))
            print(json.dumps(res["findings"], indent=2))
        return 0

    tracker = None
    if a.tracker != "none":
        repo = os.getenv("GITHUB_REPO") or os.getenv("GITHUB_REPOSITORY", "")
        tracker = make_tracker(a.tracker, repo, os.getenv("GITHUB_TOKEN", ""))
    bugs = 0
    for s in stories:
        res = full_cycle(llm, s, base_url, tracker=tracker, log=print)
        bugs += sum(1 for v in res["verdicts"] if v["verdict"] == "product_bug")
    print(f"\nDone. Product bugs currently failing: {bugs}")
    return 0


def _fmt(e):
    if e["type"] == "thought":
        return f"  think: {e['text']}"
    if e["type"] == "request":
        return (f"  {e['method']} {e['path']} {json.dumps(e['request']) if e.get('request') else ''}"
                f" -> {e.get('status') or e.get('error')} {json.dumps(e.get('response'))}")
    return f"  FINDING [{e.get('criterion', '')}] {e['title']}"


if __name__ == "__main__":
    sys.exit(main())
