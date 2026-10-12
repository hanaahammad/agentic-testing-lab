"""Bug trackers: GitHub Issues (instead of Jira), or a local JSON file when no token is set.

The agent opens one issue per failing test case (title starts with "[TC-xxx-yy]"), never duplicates
an open one, and closes it with a comment once the same test passes again.
"""
import datetime as dt
import json

import requests

from .config import REPORTS_DIR

LABEL = "agent-found"


def _now():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")


class LocalTracker:
    kind = "local"

    def __init__(self, path=None):
        self.path = path or (REPORTS_DIR / "issues.json")

    def _load(self):
        return json.loads(self.path.read_text()) if self.path.exists() else []

    def _save(self, items):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(items, indent=2))

    def list(self):
        return self._load()

    def find_open(self, tc_id):
        return next((i for i in self._load() if i["state"] == "open" and i["title"].startswith(f"[{tc_id}]")), None)

    def open(self, title, body, labels):
        items = self._load()
        issue = {"number": len(items) + 1, "title": title, "body": body, "labels": labels,
                 "state": "open", "url": f"local://issues/{len(items) + 1}", "opened": _now(), "comments": []}
        items.append(issue)
        self._save(items)
        return issue

    def close(self, issue, comment):
        items = self._load()
        for i in items:
            if i["number"] == issue["number"]:
                i["state"] = "closed"
                i["closed"] = _now()
                i["comments"].append(comment)
        self._save(items)


class GitHubTracker:
    kind = "github"
    API = "https://api.github.com"

    def __init__(self, repo: str, token: str):
        if not (repo and token):
            raise ValueError("GitHub tracker needs a repo ('owner/name') and a token with issues:write.")
        self.repo = repo
        self.h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                  "X-GitHub-Api-Version": "2022-11-28"}

    def _url(self, suffix=""):
        return f"{self.API}/repos/{self.repo}/issues{suffix}"

    @staticmethod
    def _conv(i):
        return {"number": i["number"], "title": i["title"], "state": i["state"], "url": i["html_url"],
                "labels": [lb["name"] for lb in i.get("labels", [])], "opened": i.get("created_at", ""),
                "closed": i.get("closed_at") or ""}

    def list(self):
        r = requests.get(self._url(), headers=self.h, params={"state": "all", "labels": LABEL, "per_page": 100}, timeout=20)
        r.raise_for_status()
        return [self._conv(i) for i in r.json() if "pull_request" not in i]

    def find_open(self, tc_id):
        r = requests.get(self._url(), headers=self.h, params={"state": "open", "labels": LABEL, "per_page": 100}, timeout=20)
        r.raise_for_status()
        return next((self._conv(i) for i in r.json() if i["title"].startswith(f"[{tc_id}]")), None)

    def open(self, title, body, labels):
        r = requests.post(self._url(), headers=self.h, json={"title": title, "body": body, "labels": labels}, timeout=20)
        r.raise_for_status()
        return self._conv(r.json())

    def close(self, issue, comment):
        n = issue["number"]
        requests.post(self._url(f"/{n}/comments"), headers=self.h, json={"body": comment}, timeout=20).raise_for_status()
        requests.patch(self._url(f"/{n}"), headers=self.h, json={"state": "closed", "state_reason": "completed"},
                       timeout=20).raise_for_status()


def issue_body(v: dict, story: dict) -> str:
    steps = "\n".join(f"{n}. {s}" for n, s in enumerate(v.get("steps") or [], 1)) or "_see test_"
    return f"""**Found by the QA agent** while testing **{story['id']}: {story['title']}** ({v.get('criterion', '')}).

**Severity:** {v.get('severity', 'medium')} · **Confidence:** {v.get('confidence', '')}

### Steps to reproduce
{steps}

### Expected (per the story)
{v.get('expected', '')}

### Actual
```
{v.get('actual', '')}
```

### Agent reasoning
{v.get('reasoning', '')}

_Test: `{v.get('test_name', '')}`. The agent will close this issue automatically when the test passes._"""


def sync_issues(tracker, story: dict, run: dict, verdicts: list[dict]) -> list[dict]:
    actions = []
    for v in verdicts:
        if v.get("verdict") != "product_bug" or not v.get("tc_id"):
            continue
        existing = tracker.find_open(v["tc_id"])
        if existing:
            actions.append({"action": "still open", "issue": existing})
            continue
        issue = tracker.open(f"[{v['tc_id']}] {v.get('title', 'Test failure')}", issue_body(v, story),
                             ["bug", LABEL, story["id"]])
        actions.append({"action": "opened", "issue": issue})
    for c in run["cases"]:
        if c["status"] == "passed" and c["tc_id"]:
            existing = tracker.find_open(c["tc_id"])
            if existing:
                tracker.close(existing, f"Verified fixed by the QA agent on {_now()}: `{c['name']}` now passes.")
                actions.append({"action": "closed", "issue": existing})
    return actions


def make_tracker(kind: str, repo: str = "", token: str = ""):
    return GitHubTracker(repo, token) if kind == "github" else LocalTracker()
